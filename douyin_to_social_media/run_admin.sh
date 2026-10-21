#!/usr/bin/env bash
# Chạy admin UI trên host (venv có đủ numpy / faster-whisper / edge-tts).
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
  .venv/bin/pip install -U pip
  .venv/bin/pip install -r requirements.txt
fi
exec .venv/bin/python -u admin_web.py
