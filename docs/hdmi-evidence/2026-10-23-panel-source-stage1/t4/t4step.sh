#!/bin/bash
set -e
cd /home/chris/Projects/h713
E=docs/hdmi-evidence/2026-10-23-panel-source-stage1/t4; mkdir -p $E
S=/tmp/claude-1000/-home-chris-Projects-h713/471f0481-276c-419b-8280-cf48ee2422e5/scratchpad
SSH=(ssh -F /dev/null -o BatchMode=yes -o ConnectTimeout=5 root@192.168.4.1)
if [ -n "$2" ]; then date -Is > $E/shell-$1.time
  timeout 20 "${SSH[@]}" "python3 -u /usr/lib/h713-hdmi/mips-shell.py --cmd '$2' --wait 2" > $E/shell-$1.txt 2>&1; tail -4 $E/shell-$1.txt; fi
[ -n "$3" ] && timeout 20 "${SSH[@]}" "sleep $3"
timeout 20 "${SSH[@]}" "python3 - $1" < $S/t4read.py > $E/read-$1.json
