#!/usr/bin/env bash
# 可选：从自托管 Vaultwarden 取一条密钥。用法: get-secret.sh <条目名>  -> 密码字段（无则 notes）输出到 stdout
# 需要环境变量：BW_SERVER（Vaultwarden 地址）、BW_CLIENTID、BW_CLIENTSECRET、BW_PASSWORD
# 可选：BW_BIN（bw 可执行文件，默认 PATH 中的 bw）、BITWARDENCLI_APPDATA_DIR（数据目录，默认 ./bw-data）
set -euo pipefail
[ $# -ge 1 ] || { echo "usage: $0 <item name>" >&2; exit 2; }
export BITWARDENCLI_APPDATA_DIR="${BITWARDENCLI_APPDATA_DIR:-$PWD/bw-data}"
mkdir -p "$BITWARDENCLI_APPDATA_DIR"
BW="${BW_BIN:-$(command -v bw || true)}"
[ -x "$BW" ] || { echo "bw not found; set BW_BIN or npm install -g @bitwarden/cli" >&2; exit 1; }
: "${BW_CLIENTID:?BW_CLIENTID missing}" "${BW_CLIENTSECRET:?missing}" "${BW_PASSWORD:?missing}"
st=$("$BW" status 2>/dev/null | python3 -c 'import json,sys;print(json.load(sys.stdin)["status"])')
if [ "$st" = unauthenticated ]; then
  : "${BW_SERVER:?BW_SERVER missing}"
  "$BW" config server "$BW_SERVER" >/dev/null 2>&1 || true
  "$BW" login --apikey >/dev/null 2>&1
fi
BW_SESSION=$("$BW" unlock --passwordenv BW_PASSWORD --raw 2>/dev/null); export BW_SESSION
"$BW" sync >/dev/null 2>&1 || true
"$BW" list items --search "$1" 2>/dev/null | NAME="$1" python3 -c '
import json,os,sys
its=[i for i in json.load(sys.stdin) if i.get("name")==os.environ["NAME"]]
if not its: sys.exit("item not found")
i=its[0]; v=(i.get("login") or {}).get("password") or i.get("notes")
if not v: sys.exit("no secret field")
sys.stdout.write(v)'
