#!/usr/bin/env python3
"""把工作台现有经验同步进 grokbot-agent-exp。
来源：--skills-dir / EXP_SKILLS_DIR 下的 */SKILL.md；--scan-root / EXP_SCAN_ROOTS（冒号分隔）下成功的 REPORT/变更清单/验收 记录。
两者都没指定就不扫描对应来源。状态文件放 EXP_STATE_DIR（默认脚本同目录）的 state.json， 记每个来源的 hash 与 session；--full 全量重写，默认增量（只同步新增/改过的；改过的先删旧 session 再写）。
用法: sync_all.py [--skills-dir D] [--scan-root R ...] [--full] [--dry-run] [--limit N]"""
import os, re, json, glob, argparse, time
from common import *
from exp_write import write
STATE_DIR = os.environ.get("EXP_STATE_DIR") or HERE; STATE = os.path.join(STATE_DIR, "state.json")
SKIP = re.compile(r"(/node_modules/|/venv/|/\.git/|\.bak|/agentmem-test/|draft|/tests/|prompt-|/repo/|/src/|/logs/|标准)", re.I)
BOT = {"ops": "运维", "ceo": "ceo", "docs": "文档专员", "app": "开发", "pm": "产品经理", "qa": "质量工程师", "bid": "标书专员", "memory": "记忆管家", "mem": "记忆管家"}
PIT = re.compile(r"(坑|注意|教训|踩|失败后|根因|原因|修复|纠正|不要|避免|必须|切勿|gotcha|pitfall|warning|⚠)", re.I)
FAIL = re.compile(r"(未通过|失败|❌|未完成|blocked|未解决|放弃)")
OK = re.compile(r"(成功|通过|完成|已修复|✅|正常|OK\b|PASS)", re.I)

def sources(skills_dir, roots):
    out = []
    if skills_dir:
        for p in sorted(glob.glob(os.path.join(skills_dir, "*", "SKILL.md"))):
            out.append((p, "skill/" + os.path.basename(os.path.dirname(p)), "skill"))
    for top in roots:
      top = os.path.abspath(top)
      for root, dirs, files in os.walk(top):
        dirs[:] = [d for d in dirs if d not in ("node_modules", "venv", ".git", ".venv", "__pycache__")]
        for f in files:
            p = os.path.join(root, f)
            if not f.lower().endswith(".md") or SKIP.search(p): continue
            if re.search(r"(REPORT|变更清单|验收)", f, re.I):
                rel = os.path.relpath(p, top).split(os.sep)
                d0 = rel[0] if len(rel) > 1 else os.path.basename(top)
                out.append((p, BOT.get(d0, d0), "report"))
    return out

def succeeded(text):
    head = text[:3000]
    return len(OK.findall(head)) > len(FAIL.findall(head))

def parse(path, src, kind):
    raw = open(path, encoding="utf-8", errors="ignore").read()
    body = re.sub(r"^---\n[\s\S]*?\n---\n", "", raw)
    m = re.search(r"^---\n[\s\S]*?description:\s*(.+)", raw)
    title = (re.search(r"^#\s+(.+)", body, re.M) or [None, os.path.basename(os.path.dirname(path))])[1]
    task = f"{'技能流程' if kind=='skill' else '已完成任务'}：{title}" + (f"。{m.group(1)[:300]}" if m else "")
    secs = re.split(r"^#{2,3}\s+", body, flags=re.M)[1:]
    steps = []
    for s in secs:
        head, _, rest = s.partition("\n")
        txt = re.sub(r"```[\s\S]*?```", "[代码略]", rest).strip()
        txt = re.sub(r"\n{2,}", "\n", txt)
        if not txt: continue
        steps.append({"action": head.strip()[:60], "args": {"section": head.strip()[:60]}, "result": txt[:900]})
    if len(steps) > 15:  # 合并成 15 步
        n = -(-len(steps) // 15)
        steps = [{"action": " / ".join(x["action"] for x in steps[i:i+n])[:60], "args": {"sections": [x["action"] for x in steps[i:i+n]]},
                  "result": "\n".join(x["result"] for x in steps[i:i+n])[:1500]} for i in range(0, len(steps), n)]
    if len(steps) < 5:  # 段落太少时按列表项切
        items = [l.strip() for l in body.splitlines() if re.match(r"\s*(?:\d+[.)、]|[-*])\s+\S", l)]
        if len(items) >= 5:
            k = -(-len(items) // 10)
            steps = [{"action": f"步骤{j+1}", "args": {}, "result": "\n".join(items[i:i+k])[:900]} for j, i in enumerate(range(0, len(items), k))]
    pits = [l.strip(" -*") for l in body.splitlines() if PIT.search(l) and 6 < len(l.strip()) < 300][:12]
    concl = ""
    mm = re.search(r"^#{1,3}\s*(结论|总结|结果|Summary|Result)[^\n]*\n([\s\S]{0,600})", body, re.M | re.I)
    if mm: concl = mm.group(2).strip()
    return {"src": src, "task": task, "steps": steps, "pitfalls": pits, "summary": concl or "按上述流程完成并验收通过", "accepted": True}

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--full", action="store_true"); ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--skills-dir", default=os.environ.get("EXP_SKILLS_DIR", "")); ap.add_argument("--scan-root", action="append", default=None)
    a = ap.parse_args()
    state = json.load(open(STATE)) if os.path.exists(STATE) else {}
    rep = {"time": time.strftime("%F %T"), "scanned": 0, "written": 0, "unchanged": 0, "skipped_fail": 0, "skipped_short": 0, "rewritten": 0, "errors": [], "filtered": {}}
    roots = a.scan_root if a.scan_root else [r for r in os.environ.get("EXP_SCAN_ROOTS", "").split(":") if r]
    if not roots and not a.skills_dir: raise SystemExit("请用 --scan-root/--skills-dir 或 EXP_SCAN_ROOTS/EXP_SKILLS_DIR 指定扫描来源")
    os.makedirs(STATE_DIR, exist_ok=True)
    srcs = sources(a.skills_dir, roots); seen = set()
    for path, src, kind in srcs:
        rep["scanned"] += 1; seen.add(path)
        text = open(path, encoding="utf-8", errors="ignore").read(); h = sha(text)
        old = state.get(path)
        if old and old["hash"] == h and not a.full: rep["unchanged"] += 1; continue
        if kind == "report" and not succeeded(text): rep["skipped_fail"] += 1; continue
        t = parse(path, src, kind)
        if len(t["steps"]) < 4: rep["skipped_short"] += 1; continue
        if a.dry_run: print(path, src, len(t["steps"])); continue
        if old and old.get("session"):  # 源改了：删旧再写
            post("/api/v2/memory/delete", {"session_id": old["session"]}); rep["rewritten"] += 1
        r = write(t, session="exp-" + sha(path)[:12] + "-" + h[:8])
        for k, v in r.get("filtered", {}).items(): rep["filtered"][k] = rep["filtered"].get(k, 0) + v
        if r["ok"]:
            state[path] = {"hash": h, "session": r["session_id"], "src": src, "at": rep["time"]}; rep["written"] += 1
            json.dump(state, open(STATE, "w"), ensure_ascii=False, indent=1)
        else: rep["errors"].append(f"{path}: {r['error'][:200]}")
        if a.limit and rep["written"] >= a.limit: break
    gone = [p for p in state if p not in seen]
    rep["source_removed"] = gone  # 源文件被删：只报告，不自动删云端
    if not a.dry_run:
        json.dump(state, open(STATE, "w"), ensure_ascii=False, indent=1)
        json.dump(rep, open(os.path.join(STATE_DIR, "last_sync.json"), "w"), ensure_ascii=False, indent=1)
    print(json.dumps(rep, ensure_ascii=False, indent=1))

if __name__ == "__main__": main()
