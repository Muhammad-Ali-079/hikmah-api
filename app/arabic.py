"""Arabic helpers (standard library only): remove vowel marks and unify letter shapes so a word typed, photographed or
spoken without marks still matches the Qur'an text."""
import re
import unicodedata

_MARKS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭ࣓-ࣿـ]")
_MAP = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ی": "ي", "ې": "ي", "ة": "ه", "ہ": "ه", "ھ": "ه", "ک": "ك", "ؤ": "و", "ئ": "ي"})
ARABIC_WORD = re.compile(r"[؀-ۿ]+")


def normalize(text: str) -> str:
    t = unicodedata.normalize("NFKC", text)
    t = _MARKS.sub("", t).translate(_MAP)
    return " ".join(ARABIC_WORD.findall(t))


BISMILLAH = normalize("بسم الله الرحمن الرحيم")
