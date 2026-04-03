#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# Create databucket test LXC on pve3 (192.168.100.201)
#
# Run from local machine:
#   deploy/pve3-create-lxc.sh
#
# Prerequisites:
#   - SSH access to root@192.168.100.201
#   - Debian 13 container template available on pve3
# ============================================================

PVE_HOST="root@192.168.100.201"
CTID="${CTID:-300}"
CT_HOSTNAME="databucket-test"
CT_MEMORY=2048
CT_SWAP=512
CT_DISK=50          # GB, on data SSD
CT_CORES=2
CT_BRIDGE="vmbr0"
CT_IP="${CT_IP:-192.168.100.130/24}"
CT_GW="192.168.100.1"
STORAGE="local-lvm"
TEMPLATE="local:vztmpl/debian-13-standard_13.0-1_amd64.tar.zst"

echo "=== Creating databucket test LXC on pve3 ==="
echo "  CTID:     $CTID"
echo "  Hostname: $CT_HOSTNAME"
echo "  IP:       $CT_IP"
echo "  Memory:   ${CT_MEMORY}MB"
echo "  Disk:     ${CT_DISK}GB"
echo ""

# Check if template exists, download if not
ssh "$PVE_HOST" bash <<REMOTE_CHECK
if ! pveam list local | grep -q "debian-13-standard"; then
    echo "Downloading Debian 13 template..."
    pveam update
    pveam download local debian-13-standard_13.0-1_amd64.tar.zst
fi
REMOTE_CHECK

# Create container
echo "Creating container $CTID..."
ssh "$PVE_HOST" bash <<REMOTE_CREATE
set -euo pipefail

# Check if CTID already exists
if pct status $CTID 2>/dev/null; then
    echo "Container $CTID already exists. Destroy first:"
    echo "  pct stop $CTID && pct destroy $CTID"
    exit 1
fi

pct create $CTID $TEMPLATE \
    --hostname $CT_HOSTNAME \
    --memory $CT_MEMORY \
    --swap $CT_SWAP \
    --cores $CT_CORES \
    --rootfs ${STORAGE}:${CT_DISK} \
    --net0 name=eth0,bridge=$CT_BRIDGE,ip=$CT_IP,gw=$CT_GW \
    --features nesting=1,keyctl=1 \
    --unprivileged 0 \
    --start 1 \
    --onboot 1

echo "Waiting for container to start..."
sleep 5

# Install Docker and dependencies inside container
pct exec $CTID -- bash -c '
set -euo pipefail

# Update system
apt-get update && apt-get upgrade -y

# Install Docker
apt-get install -y ca-certificates curl gnupg
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=\$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian bookworm stable" > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Install Python and boto3
apt-get install -y python3 python3-pip python3-venv git
pip install --break-system-packages boto3

# Enable Docker
systemctl enable docker
systemctl start docker

echo "Docker and Python installed."
'
REMOTE_CREATE

echo ""
echo "=== LXC container created ==="
echo ""
echo "Next steps:"
echo "  1. SSH into container:"
echo "     ssh root@${CT_IP%%/*}"
echo ""
echo "  2. Deploy databucket:"
echo "     deploy/pve3-deploy.sh"
