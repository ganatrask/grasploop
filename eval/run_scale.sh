#!/usr/bin/env bash
# The robots x tasks cells beyond the Franka lift benchmark, one grid process per cell, sequentially,
# then the matrix table and the review clips. Policies for go2/g1 come from NVIDIA's train.py
# (eval/train_walkers.sh); each cell is skipped when its record already exists.
#
#   nohup eval/run_scale.sh > _logs/scale/run.log 2>&1 &
set -uo pipefail
cd "$(dirname "$0")/.."
PY=${PY:-$HOME/workspace/isaaclab-3.0.0-ga/.venv/bin/python}
OUT=${OUT:-_logs/scale}
SEEDS=${SEEDS:-8}; SEED0=${SEED0:-100}; MODEL=${MODEL:-lightning}; ATTEMPTS=${ATTEMPTS:-3}
COND=${COND:-scripted,oneshot,rerun,physics}
CELLS=${CELLS:-"go2:nav g1:nav franka:place:cube franka:place:box_flat franka:place:box_tall"}
mkdir -p "$OUT"
echo "[scale] start $(date) cells=[$CELLS]"
for cell in $CELLS; do
  IFS=: read -r robot task shape <<< "$cell"
  if [ "$task" = "nav" ]; then tag="${robot}_nav"; extra="--robot $robot"; else tag="${robot}_${task}_${shape}"; extra="--robot $robot --task $task --shape $shape"; fi
  if [ -s "$OUT/$tag.json" ]; then echo "[scale] $tag: exists, skipping"; continue; fi
  echo "[scale] $tag: start $(date +%H:%M:%S)"
  $PY eval/run_grid.py --viz none $extra --seeds "$SEEDS" --seed0 "$SEED0" --conditions "$COND" --model "$MODEL" --attempts "$ATTEMPTS" \
      --video "$OUT/video" --json "$OUT/$tag.json" > "$OUT/$tag.log" 2>&1
  echo "[scale] $tag: exit $? at $(date +%H:%M:%S): $(grep '^\[grid\] summary' "$OUT/$tag.log" | tail -1 | cut -c1-300)"
done
DONE=$(ls "$OUT"/*.json | grep -v "\.partial\.json$")
python3 eval/matrix.py _logs/bench/franka_*.json _logs/bench/allegro_cube.json $DONE --out "$OUT/matrix.md" | head -3
$PY eval/stats.py $DONE --out "$OUT/stats" | tail -1                       # pooled, paired over every cell
for f in $DONE; do t=$(basename "$f" .json); $PY eval/stats.py "$f" --out "$OUT/stats_$t" > /dev/null; done
$PY eval/make_videos.py --video-dir "$OUT/video" --results $DONE --out "$OUT/review" --no-reel | tail -1
echo "[scale] done $(date)"
