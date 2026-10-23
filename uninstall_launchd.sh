#!/bin/bash
# Odinstalowuje autostart launchd (bot zostaje, możesz używać start.sh)
cd "$(dirname "$0")"
PLIST=~/Library/LaunchAgents/com.borys.xkombot.plist
launchctl unload "$PLIST" 2>/dev/null
rm -f "$PLIST"
pkill -f "\-m xkom\.bot" 2>/dev/null
echo "Launchd odinstalowany, bot zatrzymany. Start ręczny: ./start.sh"
