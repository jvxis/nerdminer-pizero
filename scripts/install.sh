#!/usr/bin/env bash
# One-shot installer for pizero-lottery-miner on Raspberry Pi OS (Pi Zero W).
# Builds pooler's cpuminer for ARMv6, installs Python deps, enables SPI.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
echo ">> Repo: $REPO_DIR"

echo ">> Installing system packages..."
sudo apt-get update
sudo apt-get install -y \
    build-essential automake autoconf pkg-config git \
    libcurl4-openssl-dev libjansson-dev libssl-dev libgmp-dev \
    python3-pil python3-numpy python3-requests python3-spidev python3-gpiozero

echo ">> Enabling SPI..."
sudo raspi-config nonint do_spi 0 || \
    echo "   (could not toggle SPI via raspi-config; enable it manually if the LCD is blank)"

echo ">> Building pooler/cpuminer for ARMv6 (this takes a few minutes on a Pi Zero)..."
BUILD_DIR="${REPO_DIR}/.build/cpuminer"
# Pin to a known commit so our patch always applies cleanly.
CPUMINER_COMMIT=5f02105940edb61144c09a7eb960bba04a10d5b7
SUGGEST_PATCH="${REPO_DIR}/patches/0001-cpuminer-suggest-difficulty.patch"
if [ ! -d "$BUILD_DIR/.git" ]; then
    git clone https://github.com/pooler/cpuminer.git "$BUILD_DIR"
fi
cd "$BUILD_DIR"
git checkout -q -- . 2>/dev/null || true   # drop any prior patch so re-runs stay clean
git fetch -q origin 2>/dev/null || true
git checkout -q "$CPUMINER_COMMIT"
# Teach minerd to send mining.suggest_difficulty, so a low-hashrate Pi can ask the
# pool for a difficulty it can actually meet (enabled via run-cpuminer.sh).
git apply "$SUGGEST_PATCH"
echo ">> Applied suggest_difficulty patch."
./autogen.sh
# ARMv6 (Pi Zero / Zero W) has no NEON; plain VFP build.
./configure CFLAGS="-O3 -march=armv6 -mfpu=vfp -mfloat-abi=hard"
make -j"$(nproc)"
sudo make install   # -> /usr/local/bin/minerd
cd "$REPO_DIR"

echo ">> Preparing log directory..."
sudo mkdir -p /var/log/pizero-miner
sudo chown "$USER" /var/log/pizero-miner

if [ ! -f "${REPO_DIR}/config.ini" ]; then
    cp "${REPO_DIR}/config.example.ini" "${REPO_DIR}/config.ini"
    echo ">> Created config.ini from the example. EDIT IT (wallet address + pool) before running."
fi

cat <<EOF

Done.

Next steps:
  1. Edit config.ini  -> set [wallet] address and pick your [pool].
  2. Quick test:
        bash scripts/run-cpuminer.sh        # in one terminal
        python3 dashboard.py                # in another
  3. Run as services (auto-start on boot):
        sudo cp systemd/*.service /etc/systemd/system/
        # edit the WorkingDirectory/ExecStart paths in those files if your repo
        # is not at /home/${USER}/pizero-lottery-miner
        sudo systemctl daemon-reload
        sudo systemctl enable --now pizero-cpuminer pizero-dashboard
EOF
