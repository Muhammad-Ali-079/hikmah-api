"""Reads the text in a photo (English, Arabic, Urdu, German) with the free Tesseract program. Standard library only."""
import base64
import binascii
import subprocess
from typing import Optional

MAX_BYTES = 5_000_000
LANGS = "eng+ara+urd+deu"


def looks_like_image(b: bytes) -> bool:
    return b[:8] == b"\x89PNG\r\n\x1a\n" or b[:3] == b"\xff\xd8\xff" or b[:4] == b"RIFF" and b[8:12] == b"WEBP"


def read_text(b64: str, langs: str = LANGS) -> Optional[str]:
    """Returns the text, '' when nothing was readable, None when the image is not usable or Tesseract is missing."""
    try:
        data = base64.b64decode(b64, validate=False)
    except (binascii.Error, ValueError):
        return None
    if not data or len(data) > MAX_BYTES or not looks_like_image(data):
        return None
    try:
        p = subprocess.run(["tesseract", "stdin", "stdout", "-l", langs, "--psm", "6"], input=data, capture_output=True, timeout=30)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if p.returncode != 0:
        # a language pack may be missing: try English only
        if langs != "eng":
            return read_text(b64, "eng")
        return None
    text = p.stdout.decode("utf-8", "replace")
    return " ".join(text.split())[:500]
