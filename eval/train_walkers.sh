#!/usr/bin/env bash
# Train the two walking policies GraspLoop's Go2 and G1 cells drive: NVIDIA's RSL-RL train.py on the kit-less
# Newton velocity tasks, exactly as run for the records in results/scale-2026-10-29 (Go2 1500 iterations, about
# 8 min; G1 3000 iterations, about 36 min, both at 4096 envs on one RTX 5090 laptop GPU). Checkpoints land in
# $ISAACLAB/logs/rsl_rl/<experiment>/<date>/model_*.pt, where agent/locomotion.py picks the newest one
# (or set GRASPLOOP_POLICY_GO2 / GRASPLOOP_POLICY_G1 to a checkpoint path).
#
#   ISAACLAB=~/workspace/isaaclab-3.0.0-ga eval/train_walkers.sh        # both robots, in sequence
#   eval/train_walkers.sh go2                                            # one robot
set -u
ISAACLAB="${ISAACLAB:-$HOME/workspace/isaaclab-3.0.0-ga}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
LOGS="$HERE/_logs/loco"
mkdir -p "$LOGS"
cd "$ISAACLAB"
PY=.venv/bin/python
train() {  # robot task experiment iterations
  echo "[train] $1 start $(date)"
  $PY scripts/reinforcement_learning/train.py --task "$2" --viz none --num_envs 4096 --max_iterations "$4" > "$LOGS/$1_train.log" 2>&1
  echo "[train] $1 exit $? $(date): $(ls -dt logs/rsl_rl/$3/* 2>/dev/null | head -1)"
}
for robot in ${@:-go2 g1}; do
  case "$robot" in
    go2) train go2 Isaac-Velocity-Flat-UnitreeGo2 unitree_go2_flat 1500 ;;
    g1)  train g1  Isaac-Velocity-Flat-G1          g1_flat          3000 ;;
    *)   echo "unknown robot $robot (go2|g1)"; exit 2 ;;
  esac
done
echo "[train] done $(date)"
