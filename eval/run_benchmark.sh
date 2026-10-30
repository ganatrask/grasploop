#!/usr/bin/env bash
# The final local benchmark (docs/01): one run_grid.py process per shape, one at a
# time on the single GPU, every attempt filmed, the reviewer judging every attempt afterwards, then the
# report. Prompt, model settings and the API are frozen from this point.
#
#   nohup eval/run_benchmark.sh > _logs/bench/run.log 2>&1 &
#
# Env knobs: SHAPES (Franka shapes), ALLEGRO_SHAPES (empty by default), SEEDS, SEED0, MODEL,
# REASONING (default|low|none), ATTEMPTS, COND, OUT. 20-75 min and $0.12-0.27 per Franka shape at 8 seeds
# (results/bench-2026-10-27).
set -uo pipefail
cd "$(dirname "$0")/.."
PY=${PY:-$HOME/workspace/isaaclab-3.0.0-ga/.venv/bin/python}
OUT=${OUT:-_logs/bench}
SHAPES=${SHAPES:-cube box_flat sphere_s box_tall capsule_s sphere_m}
ALLEGRO_SHAPES=${ALLEGRO_SHAPES:-}
SEEDS=${SEEDS:-8}; SEED0=${SEED0:-100}; MODEL=${MODEL:-lightning}; REASONING=${REASONING:-default}; ATTEMPTS=${ATTEMPTS:-3}
COND=${COND:-scripted,oneshot,rerun,physics,vision}
mkdir -p "$OUT"
echo "[bench] start $(date)  shapes=[$SHAPES] allegro=[$ALLEGRO_SHAPES] seeds=$SEEDS from $SEED0 model=$MODEL reasoning=$REASONING"
run_one() {  # robot shape
  local tag="$1_$2"
  if [ -s "$OUT/$tag.json" ]; then echo "[bench] $tag: exists, skipping"; return; fi
  echo "[bench] $tag: start $(date +%H:%M:%S)"
  $PY eval/run_grid.py --viz none --robot "$1" --shape "$2" --seeds "$SEEDS" --seed0 "$SEED0" --conditions "$COND" \
      --model "$MODEL" --reasoning "$REASONING" --attempts "$ATTEMPTS" --review-all \
      --cameras "$OUT/frames" --video "$OUT/video" --json "$OUT/$tag.json" > "$OUT/$tag.log" 2>&1
  echo "[bench] $tag: exit $? at $(date +%H:%M:%S): $(grep '^\[grid\] summary' "$OUT/$tag.log" | tail -1 | cut -c1-400)"
}
for s in $SHAPES; do run_one franka "$s"; done
for s in $ALLEGRO_SHAPES; do run_one allegro "$s"; done
DONE=$(ls "$OUT"/*_*.json | grep -v "\.partial\.json$")
python3 eval/report.py $DONE --out "$OUT/report" && echo "[bench] report -> $OUT/report/index.html"
$PY eval/make_videos.py --video-dir "$OUT/video" --results $DONE --out "$OUT/review" --no-reel | tail -1
echo "[bench] done $(date)"
