#!/usr/bin/env bash
# simple_install_systemd.sh — Install nurnova-simple-observer systemd service
# Paper-only. No private API. No real orders. safe_to_open_real_trade always false.

set -euo pipefail

SERVICE_NAME="nurnova-simple-observer"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Prefer repo .venv python; fall back to system python3
if [ -f "${REPO_ROOT}/.venv/bin/python" ]; then
    PYTHON_BIN="${REPO_ROOT}/.venv/bin/python"
else
    PYTHON_BIN="$(which python3)"
fi

echo "[simple_install] Repo root   : ${REPO_ROOT}"
echo "[simple_install] Python bin  : ${PYTHON_BIN}"
echo "[simple_install] Service file: ${SERVICE_FILE}"

cat > "${SERVICE_FILE}" <<EOF
[Unit]
Description=NurNova Simple Robust Engine v1 — 24/7 Production Observer (paper-only)
After=network.target
Documentation=https://github.com/nurnova/simple-robust-engine

[Service]
Type=simple
WorkingDirectory=${REPO_ROOT}
ExecStart=${PYTHON_BIN} -m src.simple.run_s24_production_observer --interval-seconds 60 --dry-run-alerts
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=${SERVICE_NAME}
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

echo "[simple_install] Service file written."

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl start "${SERVICE_NAME}"

echo ""
echo "[simple_install] Service installed and started."
echo ""
echo "Useful commands:"
echo "  systemctl status ${SERVICE_NAME}"
echo "  journalctl -u ${SERVICE_NAME} -f"
echo "  systemctl restart ${SERVICE_NAME}"
echo "  systemctl stop ${SERVICE_NAME}"
echo "  bash scripts/simple_status.sh"
