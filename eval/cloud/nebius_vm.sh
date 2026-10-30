#!/usr/bin/env bash
# Run a GraspLoop grid cell on a Nebius AI Cloud GPU VM, from the laptop.
#
# The stack is kit-less Isaac Lab 3.0.0 GA on Newton: no Isaac Sim, no RT cores, no display. So the
# VM can be an H100 (gpu-h100-sxm), which Isaac Sim cannot render on, or an L40S (gpu-l40s-a), both in
# eu-north1; or an RTX PRO 6000 (gpu-rtx6000-a, uk-south2 / eu-south1), the laptop's own architecture.
# Prices (nebius.com/prices, 2026-10-01): L40S $1.55/h, RTX PRO 6000 $1.80/h, H100 $4.50/h on demand.
#
# Needs the Nebius CLI installed and logged in (`nebius profile create`, browser login), an SSH key at
# ~/.ssh/id_ed25519.pub, and NEBIUS_API_KEY in the environment (forwarded to the VM for Nemotron).
#
#   eval/cloud/nebius_vm.sh platforms                       # what this project may create
#   eval/cloud/nebius_vm.sh create gpu-h100-sxm 1gpu-16vcpu-200gb
#   eval/cloud/nebius_vm.sh bootstrap                       # GA stack at ~/workspace/isaaclab-3.0.0-ga (~10 min)
#   eval/cloud/nebius_vm.sh push                            # this repo + the trained walker policies + the API key
#   eval/cloud/nebius_vm.sh run cube --shape cube --seeds 8 --seed0 100 --conditions scripted,oneshot,rerun,physics
#   eval/cloud/nebius_vm.sh status cube                     # tail the remote log
#   eval/cloud/nebius_vm.sh pull                            # _logs/cloud/vm/<name>.json, .log, .usage.jsonl
#   eval/cloud/nebius_vm.sh delete                          # the VM and its boot disk; billing stops here
#
# State lives in _logs/cloud/vm.env (VM_ID, VM_IP, ...). One VM at a time.
set -euo pipefail

HERE=$(cd "$(dirname "$0")/../.." && pwd)
NEBIUS=${NEBIUS:-$HOME/.nebius/bin/nebius}
STATE_DIR=$HERE/_logs/cloud
STATE=$STATE_DIR/vm.env
VM_USER=${VM_USER:-grasploop}            # "root" and "admin" are not allowed for SSH on Nebius images
IMAGE_FAMILY=${IMAGE_FAMILY:-ubuntu24.04-cuda13.0}   # driver preinstalled; CUDA 13 for torch 2.11+cu130
DISK_GIB=${DISK_GIB:-100}                # GA venv 13 G + Isaac Lab + downloaded assets + logs
ISAACLAB=$HOME/workspace/isaaclab-3.0.0-ga
POLICIES="unitree_go2_flat g1_flat"      # agent/locomotion.py reads them from the same path on the VM
SSH_OPTS=(-o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 -o ServerAliveInterval=30)

die() { echo "[nebius_vm] $*" >&2; exit 1; }
need_state() { [ -f "$STATE" ] || die "no VM: run create first"; . "$STATE"; }
vm_ssh() { ssh "${SSH_OPTS[@]}" "$VM_USER@$VM_IP" "$@"; }

cmd_platforms() {
    $NEBIUS compute platform list --format json | python3 -c '
import json, sys
for p in json.load(sys.stdin).get("items", []):
    name = p["metadata"]["name"]
    presets = [x["name"] for x in p.get("spec", {}).get("presets", []) if x["name"].startswith("1gpu") or not name.startswith("gpu")]
    print(f"{name:18s} {\" \".join(presets[:6])}")'
}

cmd_create() {
    local platform=${1:?platform, e.g. gpu-h100-sxm} preset=${2:?preset, e.g. 1gpu-16vcpu-200gb}
    [ -f "$STATE" ] && die "$STATE exists: delete the current VM first"
    [ -f ~/.ssh/id_ed25519.pub ] || die "no ~/.ssh/id_ed25519.pub"
    mkdir -p "$STATE_DIR"
    local stamp name disk subnet user_data vm_id ip
    stamp=$(date -u +%m%d-%H%M); name=grasploop-$stamp; disk=grasploop-disk-$stamp
    subnet=$($NEBIUS vpc subnet list --format jsonpath='{.items[0].metadata.id}')
    [ -n "$subnet" ] || die "no subnet in this project"
    # raw cloud-config text: CLI 0.12.298 stores the value verbatim, so a JSON-quoted string reaches
    # cloud-init as garbage and no user is created (first VM, 2026-10-29: "Permission denied (publickey)")
    user_data=$(cat <<EOF
#cloud-config
users:
  - name: $VM_USER
    sudo: ALL=(ALL) NOPASSWD:ALL
    shell: /bin/bash
    ssh_authorized_keys:
      - $(cat ~/.ssh/id_ed25519.pub)
EOF
)
    echo "[nebius_vm] creating $name on $platform / $preset, $DISK_GIB GiB $IMAGE_FAMILY, subnet $subnet"
    vm_id=$($NEBIUS compute instance create \
        --name "$name" \
        --resources-platform "$platform" \
        --resources-preset "$preset" \
        --cloud-init-user-data "$user_data" \
        --boot-disk-managed-disk-name "$disk" \
        --boot-disk-managed-disk-type network_ssd \
        --boot-disk-managed-disk-size-gibibytes "$DISK_GIB" \
        --boot-disk-managed-disk-block-size-bytes 4096 \
        --boot-disk-managed-disk-source-image-family-image-family "$IMAGE_FAMILY" \
        --boot-disk-attach-mode READ_WRITE \
        --network-interfaces "[{\"name\": \"eth0\", \"subnet_id\": \"$subnet\", \"ip_address\": {}, \"public_ip_address\": {}}]" \
        --format jsonpath='{.metadata.id}')
    [ -n "$vm_id" ] || die "instance create returned no id"
    echo "[nebius_vm] $vm_id created, waiting for a public IP"
    for _ in $(seq 60); do
        ip=$($NEBIUS compute instance get --id "$vm_id" --format jsonpath='{.status.network_interfaces[0].public_ip_address.address}' 2>/dev/null || true)
        ip=${ip%%/*}
        [ -n "$ip" ] && break
        sleep 5
    done
    [ -n "$ip" ] || die "no public IP after 5 min; check: $NEBIUS compute instance get --id $vm_id"
    cat > "$STATE" <<EOF
VM_ID=$vm_id
VM_IP=$ip
VM_NAME=$name
DISK_NAME=$disk
PLATFORM=$platform
PRESET=$preset
CREATED=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF
    echo "[nebius_vm] $name at $ip; waiting for ssh"
    VM_IP=$ip
    for _ in $(seq 60); do vm_ssh true 2>/dev/null && break; sleep 5; done
    vm_ssh 'nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader'
    echo "[nebius_vm] state in $STATE. Billing runs until: $0 delete"
}

cmd_bootstrap() {
    need_state
    vm_ssh 'bash -s' < "$HERE/eval/cloud/bootstrap_nebius_vm.sh"
}

cmd_push() {
    need_state
    [ -n "${NEBIUS_API_KEY:-}" ] || die "NEBIUS_API_KEY is not set in this shell"
    # the repo as checked out here (gitignored outputs excluded; .git included so results record the commit)
    rsync -az --delete --filter=':- .gitignore' --exclude '_logs' -e "ssh ${SSH_OPTS[*]}" "$HERE/" "$VM_USER@$VM_IP:~/grasploop/"
    for p in $POLICIES; do
        [ -d "$ISAACLAB/logs/rsl_rl/$p" ] || { echo "[nebius_vm] no local policy $p, skipped"; continue; }
        vm_ssh "mkdir -p ~/workspace/isaaclab-3.0.0-ga/logs/rsl_rl/$p"
        rsync -az -e "ssh ${SSH_OPTS[*]}" "$ISAACLAB/logs/rsl_rl/$p/" "$VM_USER@$VM_IP:~/workspace/isaaclab-3.0.0-ga/logs/rsl_rl/$p/"
    done
    vm_ssh 'umask 077; cat > ~/.grasploop_env' <<< "NEBIUS_API_KEY=$NEBIUS_API_KEY"
    vm_ssh 'mkdir -p ~/grasploop/_logs/cloud && cd ~/grasploop && git log -1 --format="[nebius_vm] repo at %h %s" && ls ~/workspace/isaaclab-3.0.0-ga/logs/rsl_rl/'
}

cmd_run() {
    need_state
    local name=${1:?run name}; shift
    local py='$HOME/workspace/isaaclab-3.0.0-ga/.venv/bin/python'
    # the subshell execs into the detached grid so the ssh pipe closes at once (an && chain ending in & keeps it open until the grid ends)
    vm_ssh "cd ~/grasploop && (set -a && . ~/.grasploop_env && set +a && \
        exec nohup $py eval/run_grid.py --viz none $* --json _logs/cloud/$name.json > _logs/cloud/$name.log 2>&1 < /dev/null) & \
        echo \"[nebius_vm] $name started, pid \$!\""
}

cmd_status() {
    need_state
    local name=${1:?run name}
    vm_ssh "pgrep -af '[r]un_grid.py' || echo '[nebius_vm] no run_grid process'; tail -n 15 ~/grasploop/_logs/cloud/$name.log"
}

cmd_pull() {
    need_state
    mkdir -p "$STATE_DIR/vm"
    rsync -az -e "ssh ${SSH_OPTS[*]}" "$VM_USER@$VM_IP:~/grasploop/_logs/cloud/" "$STATE_DIR/vm/"
    ls -la "$STATE_DIR/vm/"
}

cmd_delete() {
    need_state
    echo "[nebius_vm] deleting $VM_NAME ($VM_ID)"
    $NEBIUS compute instance delete --id "$VM_ID"
    # the boot disk was created inline; it may outlive the instance
    local disk_id
    disk_id=$($NEBIUS compute disk list --format json | python3 -c "
import json, sys
for d in json.load(sys.stdin).get('items', []):
    if d['metadata']['name'] == '$DISK_NAME': print(d['metadata']['id'])" || true)
    if [ -n "$disk_id" ]; then
        for _ in $(seq 24); do $NEBIUS compute disk delete --id "$disk_id" 2>/dev/null && break; sleep 5; done
        echo "[nebius_vm] disk $DISK_NAME deleted"
    fi
    mv "$STATE" "$STATE_DIR/vm-$(date -u +%Y%m%dT%H%M%SZ).env.done"
    echo "[nebius_vm] gone. Check the console once: $NEBIUS compute instance list"
}

case "${1:-}" in
    platforms|create|bootstrap|push|run|status|pull|delete) cmd=$1; shift; "cmd_$cmd" "$@" ;;
    *) sed -n '2,21p' "$0"; exit 1 ;;
esac
