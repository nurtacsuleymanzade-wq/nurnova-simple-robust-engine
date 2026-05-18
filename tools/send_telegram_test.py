#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
from urllib import parse, request

ENV_PATH = Path("/etc/nova-engine.env")
MESSAGE = (
    "NURNOVA LIVE PIPELINE TEST ✅\n"
    "VPS Telegram bağlantısı çalışıyor.\n"
    "Mode: PAPER_ONLY\n"
    "Real trade: DISABLED"
)


def _load_env(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"ENV file missing: {path}")
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def main() -> int:
    _load_env(ENV_PATH)
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing in /etc/nova-engine.env")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = parse.urlencode({"chat_id": chat_id, "text": MESSAGE}).encode("utf-8")
    req = request.Request(url, data=data, method="POST")
    with request.urlopen(req, timeout=15) as resp:  # nosec B310
        body = resp.read().decode("utf-8", errors="replace")
    payload = json.loads(body)
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram API error: {body}")
    print("Telegram test message sent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
