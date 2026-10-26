"""학습과 서빙이 함께 쓰는 텍스트 정규화 (training-serving skew 방지)."""
from __future__ import annotations

import re
import unicodedata

MAX_CHARS = 500
_SPACES = re.compile(r"\s+")


def normalize(text: str) -> str:
    """유니코드 정규화(NFC) → 공백 정리 → 길이 제한."""
    text = unicodedata.normalize("NFC", str(text))
    text = _SPACES.sub(" ", text).strip()
    return text[:MAX_CHARS]
