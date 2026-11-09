"""Opens the knowledge database. If the file is missing it is downloaded once from YOUR private Hugging Face dataset."""
import os
import shutil
import sqlite3
import threading
import urllib.request
from typing import Optional

from . import retrieval

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "islamic.sqlite"))
_lock = threading.Lock()
_db: Optional[sqlite3.Connection] = None


def _download() -> bool:
    repo, token = os.environ.get("HF_DATASET_REPO", ""), os.environ.get("HF_TOKEN", "")
    if not repo:
        return False
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    req = urllib.request.Request(f"https://huggingface.co/datasets/{repo}/resolve/main/islamic.sqlite")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    tmp = DB_PATH + ".part"
    try:
        with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f)
        os.replace(tmp, DB_PATH)
        return True
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        return False


def get_db() -> Optional[sqlite3.Connection]:
    """None when the knowledge base is not available (the server still works for login)."""
    global _db
    if _db is not None:
        return _db
    with _lock:
        if _db is None:
            if not os.path.exists(DB_PATH) and not _download():
                return None
            _db = retrieval.open_db(DB_PATH)
    return _db


def stats() -> dict:
    db = get_db()
    if db is None:
        return {"ready": False}
    meta = dict(db.execute("SELECT key, value FROM meta").fetchall())
    return {"ready": True, "quran_verses": int(meta.get("quran_verses", 0)), "hadith_records": int(meta.get("hadith_records", 0)),
            "tafsir_records": db.execute("SELECT COUNT(*) FROM passages WHERE kind='tafsir'").fetchone()[0],
            "built_at": meta.get("built_at", "")}
