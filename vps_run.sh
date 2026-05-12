#!/usr/bin/env bash
# S11.5-D VPS Launcher — NOVA SIMPLE ROBUST ENGINE v1
# Paper-only. No private API. No orders. safe_to_open_real_trade=false.
#
# Usage:
#   bash vps_run.sh                    # default symbol BTCUSDT
#   NOVA_SYMBOL=ETHUSDT bash vps_run.sh

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${REPO_DIR}/logs/simple"
LOG_FILE="${LOG_DIR}/vps_observer.log"
PID_FILE="${LOG_DIR}/vps_observer.pid"

mkdir -p "${LOG_DIR}"

VENV="${REPO_DIR}/.venv"
if [ -f "${VENV}/bin/activate" ]; then
    source "${VENV}/bin/activate"
elif [ -f "${VENV}/Scripts/activate" ]; then
    source "${VENV}/Scripts/activate"
fi

cd "${REPO_DIR}"

echo "[vps_run] Starting VPS Observer — $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "[vps_run] Symbol: ${NOVA_SYMBOL:-BTCUSDT}"
echo "[vps_run] Log: ${LOG_FILE}"
echo "[vps_run] safe_to_open_real_trade=false — observation mode only"

nohup python -m src.simple.vps_observer >> "${LOG_FILE}" 2>&1 &
OBSERVER_PID=$!
echo "${OBSERVER_PID}" > "${PID_FILE}"

echo "[vps_run] PID=${OBSERVER_PID} — written to ${PID_FILE}"
echo "[vps_run] Monitor: tail -f ${LOG_FILE}"
echo "[vps_run] Health:  cat state/simple/vps_heartbeat.json"
echo "[vps_run] Stop:    kill \$(cat ${PID_FILE})"
