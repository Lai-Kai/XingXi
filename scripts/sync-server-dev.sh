#!/usr/bin/env bash

set -u

server="${1:-}"
port="${2:-22}"
interval="${SYNC_INTERVAL_SECONDS:-3}"
source_dir="/mnt/d/xing_xi/deer-flow/"
remote_dir="/data/laikai/deer-flow/"
lock_dir="/tmp/deer-flow-server-sync-${UID}"

if [[ -z "$server" ]]; then
  echo "Usage: $0 <user@host> [ssh-port]" >&2
  echo "Example: $0 laikai@192.0.2.10 22" >&2
  exit 2
fi

if [[ ! "$port" =~ ^[0-9]+$ ]] || ((port < 1 || port > 65535)); then
  echo "Invalid SSH port: $port" >&2
  exit 2
fi

if [[ ! "$interval" =~ ^([1-9][0-9]*)([.][0-9]+)?$|^0[.][0-9]*[1-9][0-9]*$ ]]; then
  echo "SYNC_INTERVAL_SECONDS must be a positive number" >&2
  exit 2
fi

if [[ ! -d "$source_dir" ]]; then
  echo "Local project not found: $source_dir" >&2
  exit 1
fi

if ! mkdir "$lock_dir" 2>/dev/null; then
  echo "Another DeerFlow sync process is already running." >&2
  exit 1
fi
cleanup() {
  rmdir "$lock_dir" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

ssh_transport="ssh -p $port -o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=3 -o ControlMaster=auto -o ControlPersist=10m -o ControlPath=$HOME/.ssh/deer-flow-%C"

echo "Checking SSH access to $server:$remote_dir"
if ! ssh -p "$port" \
  -o BatchMode=yes \
  -o ConnectTimeout=10 \
  "$server" \
  "test -d '$remote_dir' && test -w '$remote_dir'"; then
  echo "SSH key authentication failed or the remote project is not writable." >&2
  echo "Configure an SSH key first, then run this script again." >&2
  exit 1
fi

echo "Syncing $source_dir -> $server:$remote_dir every ${interval}s"
echo "Press Ctrl+C to stop."

while true; do
  rsync -rltz \
    --delete-delay \
    --itemize-changes \
    --exclude='/.git/' \
    --exclude='/.env' \
    --exclude='/docker/docker-compose-server-dev.yaml' \
    --exclude='/frontend/.next/' \
    --exclude='/frontend/node_modules/' \
    --exclude='/frontend/.chrome-library-check/' \
    --exclude='/backend/.venv/' \
    --exclude='/backend/.deer-flow/' \
    --exclude='/backend/.pytest-tmp-*' \
    --exclude='*/.pytest_cache/' \
    --exclude='/logs/' \
    --exclude='*/__pycache__/' \
    --exclude='*.log' \
    -e "$ssh_transport" \
    "$source_dir" \
    "$server:$remote_dir" || echo "Sync failed; retrying in ${interval}s." >&2

  sleep "$interval"
done
