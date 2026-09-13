#!/bin/sh
# Build and install the MCP addon, then launch a background Blender for demos.
#
# Usage: PORT=9988 make demo-blender
# Environment:
#   BLENDER_BIN  Blender binary (default: blender)
#   PORT         Add-on port (default: 9988)
#   DEMO_HOME    Isolated resources dir (default: <repo>/.demo-blender-home)
#
# The launcher prints the Blender PID; stop it with: kill <pid>
set -e

PORT="${PORT:-9988}"
BLENDER_BIN="${BLENDER_BIN:-blender}"
REPO_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
DEMO_HOME="${DEMO_HOME:-$REPO_DIR/.demo-blender-home}"

mkdir -p "$DEMO_HOME"
BUILD_DIR=$(mktemp -d)
trap 'rm -rf "$BUILD_DIR"' EXIT

echo "== building addon zip =="
"$BLENDER_BIN" --command extension build \
    --source-dir="$REPO_DIR/addon/blender_mcp_addon" \
    --output-dir="$BUILD_DIR" >/dev/null

ZIP=$(ls "$BUILD_DIR"/mcp-*.zip 2>/dev/null | head -n 1)
[ -n "$ZIP" ] || { echo "ERROR: extension build produced no zip" >&2; exit 1; }

echo "== installing addon into $DEMO_HOME =="
BLENDER_USER_RESOURCES="$DEMO_HOME" "$BLENDER_BIN" --online-mode --background --factory-startup \
    --command extension install-file "$ZIP" --repo user_default --enable >/dev/null

echo "== launching background Blender on port $PORT =="
BLENDER_USER_RESOURCES="$DEMO_HOME" "$BLENDER_BIN" --online-mode --background \
    --command blender_mcp --port "$PORT" &
BLENDER_PID=$!

printf 'blender_pid=%s\nport=%s\n' "$BLENDER_PID" "$PORT"

i=0
while [ "$i" -lt 100 ]; do
    if python3 - <<PYEOF
import socket, sys
try:
    with socket.socket() as sock:
        sock.settimeout(1)
        sock.connect(("localhost", $PORT))
except OSError:
    sys.exit(1)
PYEOF
    then
        echo "addon is reachable on localhost:$PORT"
        echo "server: BLENDER_MCP_PORT=$PORT uv run --project $REPO_DIR/mcp super-blender-mcp --profile core"
        wait "$BLENDER_PID"
        exit 0
    fi
    if ! kill -0 "$BLENDER_PID" 2>/dev/null; then
        echo "ERROR: Blender exited before the addon became reachable" >&2
        exit 1
    fi
    i=$((i + 1))
    sleep 0.3
done
echo "ERROR: port $PORT not reachable within 30s" >&2
kill "$BLENDER_PID" 2>/dev/null || true
exit 1
