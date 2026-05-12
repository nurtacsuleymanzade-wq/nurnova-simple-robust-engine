#!/usr/bin/env bash
# simple_uninstall_systemd.sh — Uninstall nurnova-simple-observer systemd service

set -euo pipefail

SERVICE_NAME="nurnova-simple-observer"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

echo "[simple_uninstall] Stopping service..."
systemctl stop "${SERVICE_NAME}" || true

echo "[simple_uninstall] Disabling service..."
systemctl disable "${SERVICE_NAME}" || true

echo "[simple_uninstall] Removing service file..."
rm -f "${SERVICE_FILE}"

echo "[simple_uninstall] Reloading daemon..."
systemctl daemon-reload

echo "[simple_uninstall] Service ${SERVICE_NAME} removed."
