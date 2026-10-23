#!/bin/bash
# Start bota w tle (nohup). Log: state/logs/bot.log
cd "$(dirname "$0")"
if pgrep -f "\-m xkom\.bot" >/dev/null; then
  echo "Bot juz działa (PID: $(pgrep -f '\-m xkom\.bot' | tr '\n' ' '))."
  echo "Stop: ./stop.sh"
  exit 0
fi
# log() sam pisze do bot.log; stdout trafia do /dev/null (inaczej linie się dublowały)
nohup python3 -u -m xkom.bot >/dev/null 2>> state/logs/bot.log &
echo "Bot uruchomiony w tle (PID $!). Log: state/logs/bot.log"
echo "Status: ./status.sh | Stop: ./stop.sh"
