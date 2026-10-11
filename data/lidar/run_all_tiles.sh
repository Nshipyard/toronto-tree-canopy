#!/usr/bin/env bash
# Sequential city-wide tile run. Resumable: skips tiles whose output exists.
# One tile at a time (VM has ~1.1 GB free; a tile peaks ~800 MB).
# Logs to data/tiles_out/run.log
set -u
cd "$(dirname "$0")/../.."
OUT=data/tiles_out
LOG=$OUT/run.log
mkdir -p $OUT
N=$(.venv/bin/python3 -c "import json; print(len(json.load(open('data/tile_plan.json'))['tiles']))")
echo "=== run started $(date -Is), $N tiles ===" | tee -a $LOG
for t in $(seq 0 $((N - 1))); do
  if [ -f "$OUT/tile_${t}.json" ]; then
    echo "tile $t: exists, skipping" | tee -a $LOG
    continue
  fi
  echo "--- tile $t started $(date -Is) ---" | tee -a $LOG
  if .venv/bin/python3 data/lidar/compute_tile.py --tile "$t" >>$LOG 2>&1; then
    echo "tile $t: OK $(date -Is)" | tee -a $LOG
  else
    echo "tile $t: FAILED (exit $?) $(date -Is)" | tee -a $LOG
  fi
done
echo "=== run finished $(date -Is) ===" | tee -a $LOG
