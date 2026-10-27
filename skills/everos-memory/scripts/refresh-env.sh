#!/usr/bin/env bash
# 可选：从 Vaultwarden 重建 everos.env（运行时缓存，600 权限）。
# EVEROS_ENV_FILE 默认 ./everos.env；EVEROS_BW_ITEM 默认 "EverOS Cloud API Key"
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ENV="${EVEROS_ENV_FILE:-$PWD/everos.env}"
umask 077
KEY=$("$HERE/get-secret.sh" "${EVEROS_BW_ITEM:-EverOS Cloud API Key}")
[ -n "$KEY" ] || { echo "empty key" >&2; exit 1; }
TMP=$(mktemp "$ENV.XXXX")
printf 'export EVEROS_API_KEY="%s"\n' "$KEY" > "$TMP"
chmod 600 "$TMP"; mv "$TMP" "$ENV"
echo "everos.env refreshed: $ENV"
