#!/bin/bash
# Instaluje autostart bota (launchd): start przy logowaniu, auto-restart po crashu/resecie.
# Uwaga: NIE budzi Maca ze snu — w krytyczne dni ustaw "Nie uśpiaj, gdy ekran jest wygaszony"
# (Ustawienia systemowe > Bateria > Opcje... > Zapobiegaj uśpieniu) albo App Amphetamine.
cd "$(dirname "$0")"

# 1) zatrzymaj wersję nohup (start.sh), żeby nie było dwóch instancji
pkill -f "\-m xkom\.bot" 2>/dev/null
sleep 2

# 2) zainstaluj agenta
PLIST=~/Library/LaunchAgents/com.borys.xkombot.plist
cp launchd/com.borys.xkombot.plist "$PLIST"
launchctl unload "$PLIST" 2>/dev/null
launchctl load -w "$PLIST"

sleep 3
if pgrep -f "\-m xkom\.bot" >/dev/null; then
  echo "OK — bot działa pod launchd (PID: $(pgrep -f '\-m xkom\.bot' | tr '\n' ' '))"
  echo "  stop:        ./uninstall_launchd.sh && ./stop.sh  (albo: launchctl unload $PLIST)"
  echo "  log:         state/logs/bot.log"
else
  echo "BŁĄD — launchd nie uruchomił bota. Sprawdź: launchctl list | grep xkom"
  tail -5 state/logs/bot_stderr.log 2>/dev/null
  exit 1
fi
