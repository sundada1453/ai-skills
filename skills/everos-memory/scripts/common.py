"""EverOS 经验区公共库：配置、HTTP、脱敏。密钥绝不打印。
配置（环境变量，均有默认值）：
  EVEROS_API_KEY     密钥（优先）；没有则从 EVEROS_ENV_FILE 读
  EVEROS_ENV_FILE    env 文件，默认 ./everos.env（当前目录），其次脚本同目录 everos.env
  EVEROS_BASE        默认 https://api.evermind.ai
  EVEROS_USER_ID     默认 sundada
  EVEROS_SHARED_APP  偏好共享区，默认 muse-grok-shared
  EVEROS_EXP_APP     经验区，默认 grokbot-agent-exp
  EVEROS_AGENT_ID    默认 assistant-fleet
  EVEROS_SRC         来源标签默认值（轨迹 JSON 没写 src 时用）
"""
import os, json, re, time, urllib.request, urllib.error, hashlib
HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.environ.get("EVEROS_BASE", "https://api.evermind.ai")
USER = os.environ.get("EVEROS_USER_ID", "sundada")
SHARED_APP = os.environ.get("EVEROS_SHARED_APP", "muse-grok-shared")
EXP_APP = os.environ.get("EVEROS_EXP_APP", "grokbot-agent-exp")
AGENT = os.environ.get("EVEROS_AGENT_ID", "assistant-fleet")
SRC = os.environ.get("EVEROS_SRC", "unknown")
SCOPE = {"app_id": EXP_APP, "project_id": EXP_APP}

def _key():
    k = os.environ.get("EVEROS_API_KEY", "").strip()
    if k: return k
    cands = [os.environ["EVEROS_ENV_FILE"]] if os.environ.get("EVEROS_ENV_FILE") else ["./everos.env", os.path.join(HERE, "everos.env")]
    for env in cands:
        if not os.path.exists(env): continue
        for l in open(env):
            l = l.strip().removeprefix("export ").strip()
            if l.startswith("EVEROS_API_KEY="):
                return l.split("=", 1)[1].strip().strip("\"'")
    raise SystemExit("EVEROS_API_KEY 未设置：请设环境变量 EVEROS_API_KEY 或 EVEROS_ENV_FILE")

def post(path, body, timeout=120):
    req = urllib.request.Request(BASE + path, data=json.dumps({**SCOPE, **body}, ensure_ascii=False).encode(),
        headers={"Authorization": "Bearer " + _key(), "Content-Type": "application/json"})
    for i in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429 and i < 2: time.sleep(10 * (i + 1)); continue
            return e.code, {"error": e.read().decode()[:300]}
        except Exception as e:
            if i < 2: time.sleep(5); continue
            return 0, {"error": str(e)[:300]}

# ---------- 密钥 / IP 过滤 ----------
SECRET = [
    r"\bsk-(?=[A-Za-z0-9_-]*\d)[A-Za-z0-9_-]{16,}", r"\b[sr]k_(?:live|test)_[A-Za-z0-9]{16,}",
    r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b", r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})",
    r"\bxox[bpoas]-[A-Za-z0-9-]{10,}", r"\bAIza[0-9A-Za-z_-]{35}\b", r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----",
    r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b", r"\bBearer\s+[A-Za-z0-9._~+/=-]{20,}",
    r"(?i)\b[a-z0-9_]*(?:password|passwd|secret|(?:api|access|secret|private)_?key|token)[\"']?\s*[:=]\s*[\"']?(?=[^\s\"'$]*\d)(?=[^\s\"'$]*[A-Za-z])[^\s\"'${}<>]{8,}",
    r"(?i)(?:密码|口令|密钥|令牌)\s*[:：=]\s*\S+",
    r"\b[A-Za-z0-9]{32,}\b",  # 长随机串
]
URLPW = r"\b([a-z][a-z0-9+.-]*://)[^/?#\s:@]{1,64}:[^/?#@\s]{1,256}@"
PII = {
    "IP": r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?\b",
    "IPv6": r"\b(?:[0-9a-fA-F]{1,4}:){4,7}[0-9a-fA-F]{1,4}\b",
    "主机名": r"\b[\w-]+\.(?:ts\.net|local|lan|internal|home)\b",
}

def sanitize(text, stats):
    """返回脱敏文本；stats 计数各类被过滤项。"""
    t = str(text)
    def sub(name, pat, rep, s):
        n = len(re.findall(pat, s))
        if n: stats[name] = stats.get(name, 0) + n
        return re.sub(pat, rep, s)
    t = sub("URL密码", URLPW, r"\1<redacted>@", t)
    for p in SECRET: t = sub("密钥", p, "<已过滤:密钥>", t)
    for k, p in PII.items(): t = sub(k, p, f"<已过滤:{k}>", t)
    return t

def sha(s): return hashlib.sha256(s.encode() if isinstance(s, str) else s).hexdigest()
