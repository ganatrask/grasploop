#!/usr/bin/env bash
# Bootstrap a fresh Nebius AI Cloud GPU VM so GraspLoop runs on it exactly as on the laptop.
#
# Target: a VM from the `ubuntu24.04-cuda13.0` image family (NVIDIA driver preinstalled; CUDA 13 is
# what Isaac Lab 3.0.0 GA's torch 2.11+cu130 needs). No Isaac Sim, no RT cores, no display: the
# kit-less GA stack on Newton/MJWarp with Warp ray-traced cameras runs on any CUDA GPU, including
# the H100, which Isaac Sim cannot render on.
#
# It installs the GA checkout at the same path the laptop uses ($HOME/workspace/isaaclab-3.0.0-ga),
# so agent/locomotion.py finds the walker policies and every command in README.md runs unchanged.
# Idempotent: re-running skips finished steps. The GraspLoop repo and the trained walker policies
# are copied in afterwards by eval/cloud/nebius_vm.sh push (the policies are not in the repo).
#
#   ssh grasploop@<vm-ip> 'bash -s' < eval/cloud/bootstrap_nebius_vm.sh     # what nebius_vm.sh bootstrap runs
set -euo pipefail

ISAACLAB=${ISAACLAB:-$HOME/workspace/isaaclab-3.0.0-ga}
ISAACLAB_TAG=v3.0.0
export PATH="$HOME/.local/bin:$PATH"

echo "[bootstrap] gpu: $(nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader)"

if ! command -v git >/dev/null || ! command -v ffmpeg >/dev/null; then
    sudo apt-get update -qq
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq git rsync ffmpeg libgl1 libglib2.0-0 >/dev/null
fi
if ! command -v uv >/dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null
fi
echo "[bootstrap] uv $(uv --version)"

mkdir -p "$(dirname "$ISAACLAB")"
if [ ! -d "$ISAACLAB/.git" ]; then
    git clone --quiet --branch "$ISAACLAB_TAG" --depth 1 https://github.com/isaac-sim/IsaacLab.git "$ISAACLAB"
fi
cd "$ISAACLAB"
if [ ! -x .venv/bin/python ]; then
    # Same resolution as the laptop install: the tag's uv.lock plus the `ovrtx` extra (OVRTX path tracer for the
    # hero camera; optional in Isaac Lab's pyproject, present on the laptop). No Isaac Sim extra.
    uv sync --frozen --extra ovrtx
fi
PY="$ISAACLAB/.venv/bin/python"
$PY - <<'EOF'
import torch, warp, newton, isaaclab
print(f"[bootstrap] torch {torch.__version__} cuda {torch.version.cuda} ok={torch.cuda.is_available()} "
      f"warp {warp.__version__} newton {newton.__version__} isaaclab {isaaclab.__version__}")
assert torch.cuda.is_available(), "torch sees no GPU: check the driver on this image"
EOF
echo "[bootstrap] done: $PY"
