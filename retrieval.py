"""Searching the knowledge base (SQLite FTS5 + BM25). Standard library only.

Flow:  question -> search words (groups of alternatives) -> BM25 candidates -> re-rank by how many
       of the question's ideas the passage really contains -> hits (or nothing, when nothing is close enough).
"""
import re
import sqlite3
import unicodedata
from typing import Dict, List, Optional, Tuple

from . import arabic, glossary

STOP = set("""
a an the and or but if then than so of to in on at by for from with about into over after before between under again further
is are was were be been being am do does did doing have has had having can could shall should will would may might must
i me my mine we us our you your he him his she her it its they them their this that these those there here
what which who whom whose when where why how whats
not no nor only own same too very just also ever any all each both few more most other some such
tell please explain say says said saying let know want need give show find according regarding concerning related
in-detail detail details everything something anything
ke ki ka ko se mein me mai par per hai hain kya baare bare baray aur ya wala wali liye lie ye wo kay kaise kyun ist der die das und ein eine wie was ist über uber zu von im
""".split())

# very common in these books: they must not decide the search alone
WEAK = set("""islam islamic muslim muslims allah allahs prophet prophets messenger messengers narrated hadith hadiths quran ayah ayat verse verses
surah bukhari sahih god lord people man men person thing things one two like make made makes get got go went""".split())

URDU_STOP = set('کا کی کے کو سے میں پر ہے ہیں تھا تھی تھے کیا کیوں کیسے اور یا کہ جو ہو ہوں نے بھی یہ وہ اس ان ایک بارے لیے'.split())

TOKEN_RE = re.compile(r"[^\W_]+(?:'[^\W_]+)?", re.UNICODE)


def ascii_fold(s: str) -> str:
    s = s.replace("’", "'").replace("‘", "'")
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def stem(w: str) -> str:
    """A small stemmer, only used to judge how many question ideas a passage contains."""
    w = ascii_fold(w).lower().replace("'", "")
    for suf in ("ings", "ing", "ies", "ied", "ers", "er", "ed", "es", "s", "ly"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[: -len(suf)] + ("y" if suf in ("ies", "ied") else "")
    return w


def words_of(text: str) -> List[str]:
    return [stem(t) for t in TOKEN_RE.findall(text)]


class Query:
    """groups: each group is a list of alternative stems (an English word, or the English words a foreign word maps to)."""

    def __init__(self, groups: List[List[str]], raw_terms: List[str], urdu: Optional[List[str]] = None):
        self.groups = groups
        self.raw_terms = raw_terms
        self.urdu = urdu or []   # words written in Urdu/Arabic script: matched against the Urdu tafsir

    @property
    def empty(self) -> bool:
        return not self.groups

    def fts_expr(self) -> str:
        seen, out = set(), []
        for g in self.groups:
            for t in g:
                t = re.sub(r"[^a-z0-9]", "", ascii_fold(t).lower())
                if len(t) >= 2 and t not in seen:
                    seen.add(t)
                    out.append(f'"{t}"')
        return " OR ".join(out)


def build_query(question: str, extra_english: Optional[List[str]] = None) -> Query:
    """extra_english: search words an LLM produced for a non-English question."""
    toks = [t.lower() for t in TOKEN_RE.findall(question.replace("’", "'"))]
    groups: List[List[str]] = []
    weak_groups: List[List[str]] = []
    urdu: List[str] = []
    for t in toks:
        folded = ascii_fold(t).lower()
        if t in glossary.GLOSSARY or folded in glossary.GLOSSARY:
            eng = glossary.GLOSSARY.get(t) or glossary.GLOSSARY[folded]
            g = list(dict.fromkeys(stem(e) for e in eng))
            (weak_groups if (folded in WEAK or t in WEAK) else groups).append(g)
            continue
        if not re.search(r"[a-z]", folded):
            if re.search(r"[\u0600-\u06FF]", t) and len(t) >= 2 and t not in URDU_STOP:
                urdu.append(t)
            continue  # a word in another script that we do not know (kept for the Urdu tafsir search)
        if folded in STOP or len(folded) < 3:
            continue
        s = stem(folded)
        (weak_groups if folded in WEAK else groups).append([s])
    for e in extra_english or []:
        for w in TOKEN_RE.findall(e):
            s = stem(w)
            if ascii_fold(w).lower() not in STOP and [s] not in groups:
                groups.append([s])
    if not groups:
        groups = weak_groups  # e.g. "Who is Allah?": only weak words, still usable
    # keep the order, drop duplicates
    uniq, seen = [], set()
    for g in groups:
        key = tuple(g)
        if key not in seen:
            seen.add(key)
            uniq.append(g)
    return Query(uniq[:12], toks, list(dict.fromkeys(urdu))[:10])


# ------------------------------------------------------------------ direct references
HADITH_REF = re.compile(r"(?:hadith|hadees|hadis|bukhari|حدیث|بخاری)\D{0,12}?(\d{1,4})\b", re.I)
VERSE_REF = re.compile(r"\b(\d{1,3})\s*[:.]\s*(\d{1,3})(?:\s*[-–]\s*(\d{1,3}))?\b")
VERSE_WORDS = re.compile(r"(?:surah|sura|surat|سورہ)\s+(\d{1,3})\D{1,12}?(?:ayah|ayat|verse|آیت)\s+(\d{1,3})", re.I)


def find_reference(question: str) -> Optional[Tuple[str, int, int, int]]:
    """('hadith', no, 0, 0) or ('quran', surah, first_ayah, last_ayah) when the question names an exact place."""
    q = question.lower()
    for name, (s, a, b) in glossary.NAMED_PASSAGES.items():
        if name in q:
            return ("quran", s, a, b)
    m = VERSE_WORDS.search(question)
    if m:
        return ("quran", int(m.group(1)), int(m.group(2)), int(m.group(2)))
    m = VERSE_REF.search(question)
    if m and 1 <= int(m.group(1)) <= 114:
        a = int(m.group(2))
        return ("quran", int(m.group(1)), a, int(m.group(3) or a))
    m = HADITH_REF.search(question)
    if m and 1 <= int(m.group(1)) <= 7563:
        return ("hadith", int(m.group(1)), 0, 0)
    return None


# ------------------------------------------------------------------ database
COLS = "p.id, p.kind, p.ref, p.num, p.num2, p.vol, p.book, p.chapter, p.narrator, p.text, p.noisy"


def row_to_dict(r) -> dict:
    return {
        "id": r[0], "kind": r[1], "ref": r[2], "num": r[3], "num2": r[4], "vol": r[5],
        "book": r[6] or "", "chapter": r[7] or "", "narrator": r[8] or "", "text": r[9], "noisy": bool(r[10]),
    }


def get_hadith(db: sqlite3.Connection, no: int) -> Optional[dict]:
    r = db.execute(f"SELECT {COLS} FROM passages p WHERE kind='hadith' AND ? BETWEEN num AND num2 LIMIT 1", (no,)).fetchone()
    return row_to_dict(r) if r else None


def get_verses(db: sqlite3.Connection, surah: int, first: int, last: int, limit: int = 12) -> List[dict]:
    rows = db.execute(
        f"SELECT {COLS} FROM passages p WHERE kind='quran' AND num=? AND num2 BETWEEN ? AND ? ORDER BY num2 LIMIT ?",
        (surah, first, last, limit),
    ).fetchall()
    return [row_to_dict(r) for r in rows]


def search(db: sqlite3.Connection, query: Query, limit: int = 6, kinds: Optional[List[str]] = None) -> List[dict]:
    """Best passages first. Every hit has 'coverage' = share of the question's ideas that the passage contains."""
    if query.empty:
        return []
    expr = query.fts_expr()
    if not expr:
        return []
    kind_sql = ""
    args: list = [expr]
    if kinds:
        kind_sql = " AND p.kind IN (%s)" % ",".join("?" * len(kinds))
        args += kinds
    try:
        rows = db.execute(
            f"SELECT {COLS}, bm25(passages_fts, 1.0, 0.5, 1.0) AS score FROM passages_fts JOIN passages p ON p.id = passages_fts.rowid "
            f"WHERE passages_fts MATCH ?{kind_sql} ORDER BY score LIMIT 80",
            args,
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    hits = []
    for r in rows:
        d = row_to_dict(r[:11])
        stems = set(words_of(d["text"] + " " + d["chapter"] + " " + d["book"]))
        matched = sum(1 for g in query.groups if any(t in stems for t in g))
        d["coverage"] = matched / len(query.groups)
        d["matched"] = matched
        d["score"] = (-r[11]) * (0.35 + d["coverage"]) + d["coverage"]
        hits.append(d)
    hits.sort(key=lambda h: -h["score"])
    # a shorter passage that says the same thing is easier to read: tiny nudge, then drop duplicates by reference
    out, seen = [], set()
    for h in hits:
        if h["ref"] in seen:
            continue
        seen.add(h["ref"])
        out.append(h)
        if len(out) >= limit:
            break
    return out


def get_tafsir(db: sqlite3.Connection, surah: int, ayah: int) -> List[dict]:
    """The tafsir passages that explain this verse."""
    rows = db.execute(f"SELECT {COLS} FROM passages p WHERE kind='tafsir' AND num=? AND num2=? ORDER BY id", (surah, ayah)).fetchall()
    return [row_to_dict(r) for r in rows]


def search_urdu(db: sqlite3.Connection, query: Query, limit: int = 4) -> List[dict]:
    """Questions written in Urdu are matched against the Urdu tafsir (when it was loaded)."""
    if not query.urdu:
        return []
    expr = " OR ".join('"%s"' % w.replace('"', "") for w in query.urdu)
    try:
        rows = db.execute(
            f"SELECT {COLS}, bm25(passages_fts) AS score FROM passages_fts JOIN passages p ON p.id = passages_fts.rowid "
            "WHERE passages_fts MATCH ? AND p.kind='tafsir' ORDER BY score LIMIT 30", (expr,)).fetchall()
    except sqlite3.OperationalError:
        return []
    hits = []
    for r in rows:
        d = row_to_dict(r[:11])
        have = sum(1 for w in query.urdu if w in d["text"])
        d["coverage"] = have / len(query.urdu)
        d["score"] = -r[11]
        hits.append(d)
    hits = [h for h in hits if h["coverage"] >= MIN_URDU_COVERAGE]
    hits.sort(key=lambda h: (-h["coverage"], -h["score"]))
    return hits[:limit]


MIN_URDU_COVERAGE = 0.67


def get_arabic(db: sqlite3.Connection, surah: int, ayah: int) -> Optional[dict]:
    """The Arabic text of a verse (text = marks-free copy for searching, chapter = the original with vowel marks)."""
    r = db.execute(f"SELECT {COLS} FROM passages p WHERE kind='arabic' AND num=? AND num2=? LIMIT 1", (surah, ayah)).fetchone()
    return row_to_dict(r) if r else None


def search_arabic(db: sqlite3.Connection, question: str, limit: int = 2) -> List[dict]:
    """An ayah typed, photographed or spoken in Arabic: find the verse it comes from. Needs the Arabic text loaded."""
    words = [w for w in arabic.normalize(question).split() if len(w) >= 2]
    if len(words) < 2:
        return []
    words = list(dict.fromkeys(words))[:14]
    expr = " OR ".join('"%s"' % w for w in words)
    try:
        rows = db.execute(
            f"SELECT {COLS}, bm25(passages_fts) AS score FROM passages_fts JOIN passages p ON p.id = passages_fts.rowid "
            "WHERE passages_fts MATCH ? AND p.kind='arabic' ORDER BY score LIMIT 25", (expr,)).fetchall()
    except sqlite3.OperationalError:
        return []
    out = []
    for r in rows:
        d = row_to_dict(r[:11])
        have = set(d["text"].split())
        d["coverage"] = sum(1 for w in words if w in have) / len(words)
        out.append(d)
    out = [d for d in out if d["coverage"] >= 0.6]
    out.sort(key=lambda d: -d["coverage"])
    return out[:limit]


def open_db(path: str) -> sqlite3.Connection:
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
    return db
