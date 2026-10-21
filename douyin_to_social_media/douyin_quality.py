"""Chế độ ưu tiên chất lượng video ngắn (chấp nhận chậm hơn).

Mọi bước ASR → phụ đề đọc hằng số từ đây. Có thể override bằng biến môi trường.
"""

from __future__ import annotations

import os

# --- 1. ASR (faster-whisper) ---
# large-v3 = chính xác nhất; int8 để vừa RAM máy ~8–12GB.
WHISPER_MODEL = (os.environ.get("WHISPER_MODEL") or "large-v3").strip() or "large-v3"
WHISPER_COMPUTE = (os.environ.get("WHISPER_COMPUTE") or "int8").strip() or "int8"
WHISPER_BEAM_SIZE = int(os.environ.get("WHISPER_BEAM_SIZE") or "5")
WHISPER_BEST_OF = int(os.environ.get("WHISPER_BEST_OF") or "5")
WHISPER_PATIENCE = float(os.environ.get("WHISPER_PATIENCE") or "1.0")

# --- 2–3. Highlight / Script (LLM) ---
HIGHLIGHT_TEMPERATURE = float(os.environ.get("DTS_HIGHLIGHT_TEMP") or "0.12")
SCRIPT_TEMPERATURE = float(os.environ.get("DTS_SCRIPT_TEMP") or "0.28")
HIGHLIGHT_SEG_LIMIT = int(os.environ.get("DTS_HIGHLIGHT_SEGS") or "200")
HIGHLIGHT_TEXT_CHARS = int(os.environ.get("DTS_HIGHLIGHT_CHARS") or "160")
LLM_GROQ_TIMEOUT = int(os.environ.get("DTS_LLM_GROQ_TIMEOUT") or "180")
LLM_GEMINI_TIMEOUT = int(os.environ.get("DTS_LLM_GEMINI_TIMEOUT") or "180")
LLM_OLLAMA_TIMEOUT = int(os.environ.get("DTS_LLM_OLLAMA_TIMEOUT") or "300")
LLM_OLLAMA_NUM_PREDICT = int(os.environ.get("DTS_LLM_NUM_PREDICT") or "4000")

# --- 4. Cut / encode ---
FFMPEG_PRESET = (os.environ.get("DTS_FFMPEG_PRESET") or "slow").strip() or "slow"
FFMPEG_CRF = (os.environ.get("DTS_FFMPEG_CRF") or "18").strip() or "18"
FFMPEG_AUDIO_BITRATE = (os.environ.get("DTS_FFMPEG_AUDIO_BR") or "256k").strip() or "256k"
# Re-encode khi ghép (không stream-copy) để tránh giật / lệch keyframe.
CUT_REENCODE_CONCAT = True

# --- 5. TTS ---
# edge neural > piper medium về độ tự nhiên; auto ưu tiên FPT (nam Bắc) → Edge → Piper.
TTS_PROVIDER = (os.environ.get("DTS_TTS_PROVIDER") or "auto").strip() or "auto"
PIPER_MP3_QSCALE = (os.environ.get("DTS_PIPER_QSCALE") or "0").strip() or "0"

# --- 6. Mux audio ---
MUX_BGM_VOLUME = float(os.environ.get("DTS_BGM_VOLUME") or "0.38")
MUX_TTS_VOLUME = float(os.environ.get("DTS_TTS_VOLUME") or "0.95")
MUX_AUDIO_BITRATE = (os.environ.get("DTS_MUX_AUDIO_BR") or "320k").strip() or "320k"

# --- 7. Subtitle burn ---
SUB_FONT_SIZE = int(os.environ.get("DTS_SUB_FONT_SIZE") or "64")
SUB_OUTLINE = int(os.environ.get("DTS_SUB_OUTLINE") or "5")
SUB_MARGIN_V = int(os.environ.get("DTS_SUB_MARGIN_V") or "200")
