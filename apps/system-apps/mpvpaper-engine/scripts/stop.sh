#!/usr/bin/env bash
# Stop only the Hub started by scripts/start.sh. Engine stays under systemd.
set -euo pipefail

RUN_DIR="${XDG_RUNTIME_DIR:-/tmp}/mpvpaper-engine"
PID_FILE="$RUN_DIR/hub.pid"
PORT_FILE="$RUN_DIR/hub.port"
HUB_DIR="$(cd "$(dirname "$(realpath "$0")")/../hub" && pwd)"

if [[ ! -f "$PID_FILE" ]]; then
  echo "Aucun Hub lancé par scripts/start.sh."
  exit 0
fi

hub_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
if [[ ! "$hub_pid" =~ ^[0-9]+$ ]]; then
  echo "Fichier PID invalide; aucun processus arrêté." >&2
  exit 1
fi

command_line="$(tr '\0' ' ' <"/proc/$hub_pid/cmdline" 2>/dev/null || true)"
if [[ "$command_line" != *"$HUB_DIR/scripts/local-hub-server.mjs"* ]]; then
  echo "Le PID $hub_pid ne correspond pas au Hub de ce dépôt; aucun processus arrêté." >&2
  exit 1
fi

kill -TERM "$hub_pid" 2>/dev/null || true
for _ in {1..40}; do
  kill -0 "$hub_pid" 2>/dev/null || break
  sleep 0.1
done
if kill -0 "$hub_pid" 2>/dev/null; then
  echo "Le Hub ne s'est pas arrêté proprement; processus laissé intact." >&2
  exit 1
fi
rm -f -- "$PID_FILE" "$PORT_FILE"
echo "MPVpaper Hub arrêté. Le service Engine reste actif."
