#!/bin/bash
# Zatrzymaj bota
cd "$(dirname "$0")"
if pgrep -f "\-m xkom\.bot" >/dev/null; then
  pkill -f "\-m xkom\.bot"
  sleep 1
  echo "Bot zatrzymany."
else
  echo "Bot nie działa."
fi
