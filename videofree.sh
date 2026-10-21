#!/usr/bin/env bash
# VideoFree Studio Linux launcher. It mirrors videofree.bat where the platforms overlap:
# 读取 .env、填充缺省值、检查运行环境，然后前台启动网关（Ctrl+C 优雅停止）。
# Usage: ./videofree.sh [--check]
#   --check  只做安装自检，不启动网关。
# 依赖：Python 3.10+（建议 3.12）及 requirements.txt 中的包。
#   安装：python3 -m pip install -r requirements.txt
set -u
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "[ERROR] 找不到 $PYTHON。请先安装 Python 3.10+，或用 PYTHON=/path/to/python3 指定。" >&2
    exit 1
fi

if ! "$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
    echo "[ERROR] Python 版本过低：需要 3.10 或更高（建议 3.12）。" >&2
    "$PYTHON" -V >&2
    exit 1
fi

if [[ "${1:-}" == "--check" ]]; then
    "$PYTHON" -B -s -c 'from backend.main import app; from backend.bootstrap import check_installation; check_installation(); print("Runtime check OK:", app.title, app.version)'
    exit $?
fi

if ! "$PYTHON" -B -s -c 'import fastapi, uvicorn, multipart, PIL, jsonschema' 2>/dev/null; then
    echo "[ERROR] Python 依赖缺失。请先执行：$PYTHON -m pip install -r requirements.txt" >&2
    exit 1
fi

# 与 cmd 版一致：逐行解析 .env（KEY=VALUE，跳过注释），导出为环境变量。
if [[ -f .env ]]; then
    while IFS= read -r line || [[ -n "$line" ]]; do
        line="${line%$'\r'}"
        [[ "$line" =~ ^[[:space:]]*(#|$) ]] && continue
        [[ "$line" != *=* ]] && continue
        key="${line%%=*}"
        value="${line#*=}"
        key="${key//[[:space:]]/}"
        [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
        export "$key=$value"
    done < .env
fi

export PYTHONUTF8=1
export PYTHONDONTWRITEBYTECODE=1
: "${COMFYUI_URL:=http://127.0.0.1:8189}"
: "${MEDIA_GATEWAY_HOST:=0.0.0.0}"
: "${MEDIA_GATEWAY_PORT:=8765}"
export COMFYUI_URL MEDIA_GATEWAY_HOST MEDIA_GATEWAY_PORT

echo "VideoFree Studio is starting..."
echo "ComfyUI: $COMFYUI_URL"
echo "Web UI:  http://127.0.0.1:$MEDIA_GATEWAY_PORT"
if [[ "$MEDIA_GATEWAY_HOST" != "127.0.0.1" ]]; then
    echo "LAN API: http://$(hostname -I 2>/dev/null | awk '{print $1}'):$MEDIA_GATEWAY_PORT"
    echo "注意：默认监听 0.0.0.0，公网/局域网暴露时请在设置页配置访问令牌。"
fi
echo "Press Ctrl+C to stop."
echo

exec "$PYTHON" -B -s -m backend.launcher
