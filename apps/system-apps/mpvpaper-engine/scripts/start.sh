#!/usr/bin/env bash
# Start the prebuilt local Hub. Engine itself remains managed by systemd --user.
set -euo pipefail

SCRIPT_DIR="$(dirname "$(realpath "$0")")"
ENGINE_DIR="$(realpath "$SCRIPT_DIR/..")"
HUB_DIR="$ENGINE_DIR/hub"
RUN_DIR="${XDG_RUNTIME_DIR:-/tmp}/mpvpaper-engine"
PID_FILE="$RUN_DIR/hub.pid"
PORT_FILE="$RUN_DIR/hub.port"
STATE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/mpvpaper-engine/hub-state"
LOG_FILE="${STATE_DIR%/hub-state}/hub.log"

command -v python3 >/dev/null || { echo "python3 est requis." >&2; exit 1; }
systemctl --user is-active --quiet mpvpaper-engine.service || {
  echo "Démarrez d'abord le moteur : systemctl --user start mpvpaper-engine.service" >&2
  exit 1
}

node_bin="${MPVPAPER_NODE_BIN:-$(command -v node || true)}"
if [[ -z "$node_bin" ]]; then
  node_bin="$(find "$HOME/.nvm/versions/node" -mindepth 3 -maxdepth 3 -path '*/bin/node' -type f 2>/dev/null | sort -V | tail -n 1 || true)"
fi
[[ -n "$node_bin" && -x "$node_bin" ]] || { echo "Node.js >= 22.13 est requis." >&2; exit 1; }
[[ -f "$HUB_DIR/scripts/local-hub-server.mjs" && \
   -f "$HUB_DIR/node_modules/wrangler/bin/wrangler.js" && \
   -f "$HUB_DIR/dist/server/wrangler.json" ]] || {
  echo "Hub précompilé ou dépendances absents. Lancez : $ENGINE_DIR/scripts/build.sh" >&2
  exit 1
}

mkdir -p "$RUN_DIR" "$STATE_DIR" "$(dirname "$LOG_FILE")"
if [[ -f "$PID_FILE" ]]; then
  old_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  old_command=""
  if [[ "$old_pid" =~ ^[0-9]+$ ]]; then
    old_command="$(tr '\0' ' ' <"/proc/$old_pid/cmdline" 2>/dev/null || true)"
  fi
  if [[ "$old_pid" =~ ^[0-9]+$ ]] && kill -0 "$old_pid" 2>/dev/null && \
     [[ "$old_command" == *"$HUB_DIR/scripts/local-hub-server.mjs"* ]]; then
    old_port="$(cat "$PORT_FILE" 2>/dev/null || true)"
    echo "MPVpaper Hub déjà actif : http://127.0.0.1:${old_port:-?}/"
    exit 0
  fi
  rm -f -- "$PID_FILE" "$PORT_FILE"
fi

port="${MPVPAPER_HUB_PORT:-$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')}"
[[ "$port" =~ ^[0-9]+$ ]] && (( port > 0 && port < 65536 )) || {
  echo "Port Hub invalide : $port" >&2; exit 2;
}
"$node_bin" "$HUB_DIR/scripts/local-hub-server.mjs" "$port" "$STATE_DIR" \
  >>"$LOG_FILE" 2>&1 </dev/null &
hub_pid=$!
printf '%s\n' "$hub_pid" >"$PID_FILE"
printf '%s\n' "$port" >"$PORT_FILE"

for _ in {1..80}; do
  if ! kill -0 "$hub_pid" 2>/dev/null; then
    echo "Le Hub s'est arrêté. Consultez $LOG_FILE" >&2
    rm -f -- "$PID_FILE" "$PORT_FILE"
    exit 1
  fi
  if python3 - "$port" <<'PY'
import socket, sys
try:
    with socket.create_connection(("127.0.0.1", int(sys.argv[1])), timeout=0.2): pass
except OSError:
    raise SystemExit(1)
PY
  then
    echo "MPVpaper Hub prêt : http://127.0.0.1:$port/"
    exit 0
  fi
  sleep 0.25
done
echo "Délai dépassé au démarrage du Hub. Consultez $LOG_FILE" >&2
kill -TERM "$hub_pid" 2>/dev/null || true
rm -f -- "$PID_FILE" "$PORT_FILE"
exit 1
