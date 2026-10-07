#!/bin/bash
# guard.sh LIMIT_MB MAX_SECONDS LOG -- command...
# Runs the command, samples its whole process tree every second and stops it if the tree's resident
# memory passes LIMIT_MB, if the system's free-memory level falls below 40%, or after MAX_SECONDS.
limit=$1; maxs=$2; log=$3; shift 4
"$@" >"$log" 2>&1 &
pid=$!
peak=0; start=$SECONDS; reason="exited"
tree() { ps -axo pid=,ppid= | awk -v root="$1" '{p[$1]=$2} END {ids[root]=1; c=1; while (c) {c=0; for (k in p) if (!(k in ids) && (p[k] in ids)) {ids[k]=1; c=1}} for (k in ids) print k}'; }
stop() { local t; t=$(tree $pid); kill -TERM $t 2>/dev/null; sleep 2; kill -KILL $t 2>/dev/null; }
# Killed itself (pkill -f on the command also matches this script): still stop the tree and report.
trap 'stop; echo "GUARD: stopped (signalled), peak ${peak} MB" | tee -a "$log"; exit 143' TERM INT
while kill -0 $pid 2>/dev/null; do
  rss=$(ps -o rss= -p "$(tree $pid | paste -sd, -)" 2>/dev/null | awk '{s+=$1} END {print int(s/1024)}')
  level=$(sysctl -n kern.memorystatus_level)
  [ "${rss:-0}" -gt "$peak" ] && peak=$rss
  if [ "${rss:-0}" -gt "$limit" ]; then reason="memory ${rss} MB over ${limit} MB"; stop; break; fi
  if [ "$level" -lt 40 ]; then reason="system free memory at ${level}%"; stop; break; fi
  if [ $((SECONDS - start)) -ge "$maxs" ]; then reason="time limit ${maxs}s"; stop; break; fi
  sleep "${GUARD_INTERVAL:-1}"
done
echo "GUARD: stopped ($reason), peak ${peak} MB" | tee -a "$log"
