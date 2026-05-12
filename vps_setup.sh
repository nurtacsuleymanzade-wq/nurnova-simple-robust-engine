#!/bin/bash
# NurNova VPS Kurulum Scripti
# Kullanim: bash vps_setup.sh

set -e

echo "=========================================="
echo "  NurNova VPS Kurulum"
echo "=========================================="

# ---- BURAYA DOLDUR ----
GITHUB_REPO="https://github.com/KULLANICI_ADI/REPO_ADI.git"
TELEGRAM_BOT_TOKEN="BURAYA_BOT_TOKEN"
TELEGRAM_CHAT_ID="BURAYA_CHAT_ID"
# -----------------------

PROJECT_DIR="/opt/nurnova"
PYTHON="python3"

# 1. Sistem paketleri
echo ""
echo "[1/7] Sistem paketleri yukleniyor..."
sudo apt-get update -q
sudo apt-get install -y python3 python3-pip git

# 2. Python paketleri
echo "[2/7] Python paketleri yukleniyor..."
pip3 install websockets aiohttp --break-system-packages 2>/dev/null || pip3 install websockets aiohttp

# 3. Repo
echo "[3/7] Repo indiriliyor..."
if [ -d "$PROJECT_DIR" ]; then
    echo "Repo zaten var, guncelleniyor..."
    cd "$PROJECT_DIR" && git pull origin main
else
    sudo mkdir -p "$PROJECT_DIR"
    sudo chown $USER:$USER "$PROJECT_DIR"
    git clone "$GITHUB_REPO" "$PROJECT_DIR"
    cd "$PROJECT_DIR"
fi

cd "$PROJECT_DIR"

# 4. Klasorler
echo "[4/7] Klasorler olusturuluyor..."
mkdir -p data/simple state/simple reports/simple

# 5. Env dosyasi
echo "[5/7] Env dosyasi olusturuluyor..."
cat > /opt/nurnova/.env << EOF
TELEGRAM_BOT_TOKEN=$TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID=$TELEGRAM_CHAT_ID
NURNOVA_STATUS_INTERVAL=900
NURNOVA_LOOP_INTERVAL=30
EOF
chmod 600 /opt/nurnova/.env

# 6. Systemd servisleri
echo "[6/7] Servisler olusturuluyor..."

# WebSocket servisi
sudo tee /etc/systemd/system/nurnova-ws.service > /dev/null << EOF
[Unit]
Description=NurNova WebSocket Collector
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$PROJECT_DIR
ExecStart=$PYTHON -m src.simple.run_live_ws_runtime
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=nurnova-ws

[Install]
WantedBy=multi-user.target
EOF

# Telegram notifier servisi (pipeline dahil)
sudo tee /etc/systemd/system/nurnova-bot.service > /dev/null << EOF
[Unit]
Description=NurNova Telegram Bot + Pipeline
After=network-online.target nurnova-ws.service
Wants=nurnova-ws.service

[Service]
Type=simple
User=$USER
WorkingDirectory=$PROJECT_DIR
EnvironmentFile=$PROJECT_DIR/.env
ExecStart=$PYTHON telegram_notifier.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=nurnova-bot

[Install]
WantedBy=multi-user.target
EOF

# 7. Baslat
echo "[7/7] Servisler baslatiliyor..."
sudo systemctl daemon-reload
sudo systemctl enable nurnova-ws nurnova-bot
sudo systemctl restart nurnova-ws
sleep 5
sudo systemctl restart nurnova-bot

echo ""
echo "=========================================="
echo "  Kurulum tamamlandi!"
echo "=========================================="
echo ""
echo "Servis durumu:"
echo ""
sudo systemctl status nurnova-ws --no-pager | head -8
echo ""
sudo systemctl status nurnova-bot --no-pager | head -8
echo ""
echo "Log izleme:"
echo "  sudo journalctl -u nurnova-ws -f"
echo "  sudo journalctl -u nurnova-bot -f"
echo ""
echo "Servisi durdurma:"
echo "  sudo systemctl stop nurnova-ws nurnova-bot"
echo ""
echo "Guncelleme (repo pull + restart):"
echo "  cd /opt/nurnova && git pull && sudo systemctl restart nurnova-ws nurnova-bot"
