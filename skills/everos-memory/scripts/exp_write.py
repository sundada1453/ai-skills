#!/usr/bin/env python3
"""写一条经验轨迹到经验区（EVEROS_EXP_APP / EVEROS_AGENT_ID）。
用法: exp_write.py traj.json [--session ID] [--dry-run]
JSON: {"src":"ceo|标书专员|muse|dsh|...","task":"任务描述",
       "steps":[{"action":"动作/工具名","args":{...}或"说明","result":"结果"} ...5-15步],
       "pitfalls":["踩坑与纠正", ...], "summary":"最终结论", "accepted": true}
accepted 必须为 true（验收通过）才写。"""
import sys, json, time, argparse
from common import *

def build(t, stats):
    src = sanitize(t.get("src") or SRC, stats).strip()
    tag = f"[src:{src}]"
    steps = t["steps"][:15]
    ts = int(time.time() * 1000)
    msgs = [{"sender_id": USER, "sender_name": "User", "role": "user", "timestamp": ts,
             "content": f"{tag} {sanitize(t['task'], stats)}"}]
    for i, s in enumerate(steps):
        cid = f"c{i+1}"
        name = re.sub(r"[^\w-]", "_", sanitize(s.get("action", f"step{i+1}"), stats))[:60] or f"step{i+1}"
        args = s.get("args", {})
        args = sanitize(json.dumps(args, ensure_ascii=False) if not isinstance(args, str) else json.dumps({"note": args}, ensure_ascii=False), stats)
        msgs.append({"sender_id": AGENT, "sender_name": "Assistant", "role": "assistant", "timestamp": ts + 2*i + 1,
                     "content": f"{tag} 第{i+1}步：{sanitize(s.get('action',''), stats)}",
                     "tool_calls": [{"id": cid, "type": "function", "function": {"name": name, "arguments": args}}]})
        msgs.append({"sender_id": AGENT, "role": "tool", "tool_call_id": cid, "timestamp": ts + 2*i + 2,
                     "content": sanitize(s.get("result", ""), stats)[:2000] or "完成"})
    pits = "\n".join(f"- {sanitize(p, stats)}" for p in t.get("pitfalls", []))
    msgs.append({"sender_id": AGENT, "sender_name": "Assistant", "role": "assistant", "timestamp": ts + 999,
                 "content": f"{tag} 结论：{sanitize(t.get('summary','已完成并验收通过'), stats)}\n踩坑与纠正：\n{pits or '- 无'}"})
    return msgs

def write(t, session=None, dry=False):
    stats = {}
    if not t.get("accepted"): return {"ok": False, "error": "未验收(accepted!=true)，不写"}
    if len(t.get("steps", [])) < 4: return {"ok": False, "error": "步骤少于4步，不会生成Case，跳过"}
    msgs = build(t, stats)
    sid = session or "exp-" + sha(json.dumps(t, ensure_ascii=False))[:20]
    if dry: return {"ok": True, "dry": True, "session_id": sid, "filtered": stats, "messages": msgs}
    s, d = post("/api/v2/memory/add", {"session_id": sid, "messages": msgs, "async_mode": False})
    if s != 200: return {"ok": False, "error": f"add {s} {d}", "filtered": stats}
    post("/api/v2/memory/flush", {"session_id": sid})
    return {"ok": True, "session_id": sid, "filtered": stats, "status": d["data"].get("status")}

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("file"); ap.add_argument("--session"); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    print(json.dumps(write(json.load(open(a.file)), a.session, a.dry_run), ensure_ascii=False, indent=1))
