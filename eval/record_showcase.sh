#!/usr/bin/env bash
# Films every stage of GraspLoop for review, one sim process at a time (~25 min on the laptop, ~$0.05):
#   1. Franka, scripted reference on six shapes, 3 seeds each
#   2. Franka cube: Nemotron one-shot, physics repair, physics + vision repair, 2 seeds (run_grid)
#   3. Franka thin box and tall box: Nemotron with physics repair (adaptation to a thin and a tall object)
#   4. Kuka-Allegro, scripted power grasp on the cube, 3 seeds
# then eval/make_videos.py -> $OUT/review/{reel.mp4, NN_<tag>.mp4, index.md}.
#   nohup eval/record_showcase.sh > _logs/showcase/run.log 2>&1 &
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PY:-$HOME/workspace/isaaclab-3.0.0-ga/.venv/bin/python}
OUT=${OUT:-_logs/showcase}
V=$OUT/video
mkdir -p "$OUT"
echo "[showcase] start $(date)"
for shape in cube box_flat sphere_s sphere_m box_tall capsule_s; do
  $PY eval/gate_t1.py --viz none --shape $shape --seeds 3 --seed0 100 --video $V --json $OUT/01_scripted_$shape.json
done
$PY eval/run_grid.py --viz none --shape cube --seeds 2 --seed0 100 --conditions oneshot,physics,vision --model lightning \
    --cameras $OUT/frames --video $V --json $OUT/02_grid_cube.json
$PY eval/run_loop.py --viz none --shape box_flat --seeds 2 --seed0 100 --feedback physics --video $V --json $OUT/03_loop_box_flat.json
$PY eval/run_loop.py --viz none --shape box_tall --seeds 1 --seed0 100 --feedback physics --video $V --json $OUT/03_loop_box_tall.json
$PY eval/gate_t1.py --viz none --robot allegro --shape cube --seeds 3 --seed0 100 --video $V --json $OUT/04_scripted_allegro_cube.json
$PY eval/make_videos.py --video-dir $V --results $OUT/0*.json --out $OUT/review
echo "[showcase] done $(date)"
