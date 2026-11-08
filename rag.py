"""Answering from the books only. Standard library only (the LLM call uses urllib).

Rules that keep the bot honest:
 1. If the question names an exact place (hadith 1117, 2:255, Ayat al-Kursi) -> show that text. No LLM needed.
 2. Otherwise search. If nothing is close enough -> say so. Never answer from the model's own memory.
 3. The sources are always printed word-for-word by the SERVER. An LLM (optional) may only write a short summary,
    and every sentence must cite [n]; sentences that cite nothing, or carry numbers/quotes/Arabic not found in
    the cited text, are thrown away.
"""
import json
import os
import re
import urllib.request
from typing import List, Optional

from . import retrieval as R
from . import guard

MIN_COVERAGE = 0.67   # share of the question's ideas a passage must contain
MAX_SOURCES = 4

NOT_FOUND = ("I could not find anything about this in the books I was given "
             "(the Qur'an and Sahih al-Bukhari). I will not guess in matters of religion. "
             "Please try other words, or ask a scholar.")

SYSTEM = (
    "You summarise Islamic source texts. You get a question and numbered sources. "
    "Write at most 3 short sentences that answer the question using ONLY the sources. "
    "End every sentence with the number of the source it comes from, like [1]. "
    "Never add facts, numbers, names or quotations that are not in the cited source. "
    "Do not write Arabic. If the sources do not answer the question, reply exactly: NONE"
)


def _clip(text: str, n: int = 1400) -> str:
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + " …"


def _source(h: dict, n: int) -> dict:
    if h["kind"] == "arabic":   # show the original text with its vowel marks, not the search copy
        h = dict(h, text=h["chapter"], chapter="")
    return {
        "n": n, "kind": h["kind"], "ref": h["ref"], "book": h["book"], "chapter": h["chapter"],
        "narrator": h["narrator"], "text": _clip(h["text"]), "noisy": h["noisy"],
        "surah": h["num"] if h["kind"] in ("quran", "arabic") else None, "ayah": h["num2"] if h["kind"] in ("quran", "arabic") else None,
    }


def llm_configured() -> bool:
    return bool(os.environ.get("LLM_API_KEY") and os.environ.get("LLM_BASE_URL") and os.environ.get("LLM_MODEL"))


def call_llm(system: str, user: str) -> Optional[str]:
    """Any OpenAI-compatible endpoint (Groq, Gemini, OpenRouter ...). Returns None on any failure."""
    try:
        body = json.dumps({
            "model": os.environ["LLM_MODEL"], "temperature": 0, "max_tokens": 300,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }).encode()
        req = urllib.request.Request(
            os.environ["LLM_BASE_URL"].rstrip("/") + "/chat/completions", data=body,
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + os.environ["LLM_API_KEY"]})
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read())["choices"][0]["message"]["content"].strip()
    except Exception:
        return None


CITE = re.compile(r"\[(\d+)\]")
NUM = re.compile(r"\d+")
QUOTE = re.compile(r'"([^"]{3,})"')
ARABIC = re.compile(r"[؀-ۿ]")


def validate_summary(raw: str, sources: List[dict]) -> str:
    """Keep only sentences that cite a real source and add nothing the source does not contain."""
    if not raw or raw.strip().upper().startswith("NONE"):
        return ""
    by_n = {s["n"]: s["text"].lower() for s in sources}
    keep = []
    for sent in re.split(r"(?<=[.!?\]])\s+", raw.strip()):
        cites = [int(c) for c in CITE.findall(sent)]
        if not cites or any(c not in by_n for c in cites) or ARABIC.search(sent):
            continue
        body = CITE.sub("", sent)
        pool = " ".join(by_n[c] for c in cites)
        if any(x not in pool for x in NUM.findall(body)):
            continue
        if any(q.lower() not in pool for q in QUOTE.findall(body)):
            continue
        keep.append(sent.strip())
    return " ".join(keep)


def to_english(question: str) -> str:
    """Questions in other languages (Arabic, Hindi, Turkish, French, Spanish, Indonesian ...) are translated to English
    ONLY when an LLM is configured. The translation is used for searching; the books are still shown word for word.
    Without an LLM the question is searched as written (English, Roman Urdu, Urdu and German work out of the box)."""
    if not llm_configured() or not question.strip():
        return question
    if not re.search(r"[^\x00-\x7f]", question) and not re.search(r"\b(el|la|los|les|der|die|das|und|est|une|bir|ve|yang|dan|hai|kya)\b", question.lower()):
        return question
    out = call_llm("Translate the user's text into English. Output only the translation. Do not answer it, do not add anything.", question)
    return out.strip()[:500] if out else question


def answer(db, question: str, llm=None) -> dict:
    """llm: function(system, user) -> str|None. Defaults to the configured OpenAI-compatible LLM (or none)."""
    question = (question or "").strip()[:500]
    if not question:
        return {"status": "empty", "answer": "", "sources": []}

    # Islam-only guard: checked on the original words AND on the English translation (so a trick in any language is caught).
    rule = guard.check(question)
    if rule is None and llm is None:
        english = to_english(question)
        if english != question:
            rule = guard.check(english)
            if rule is None:
                question = english
    if rule:
        return {"status": "guard", "code": "guard", "rule": rule, "answer": guard.GUARD_TEXT, "summary": "",
                "sources": guard.verses_for_guard(db, R, _source)}

    ref = R.find_reference(question)
    if ref:
        if ref[0] == "hadith":
            h = R.get_hadith(db, ref[1])
            hits = [h] if h else []
        else:
            hits = R.get_verses(db, ref[1], ref[2], ref[3])
        if hits and ref[0] == "quran":
            ar = [R.get_arabic(db, h["num"], h["num2"]) for h in hits[:3]]
            for h in list(hits[:3]):
                hits += R.get_tafsir(db, h["num"], h["num2"])[:1]   # the tafsir of the verse, when it is loaded
            hits = [a for a in ar if a] + hits                       # the Arabic text first, when it is loaded
        if hits:
            srcs = [_source(h, i + 1) for i, h in enumerate(hits)]
            return {"status": "exact", "code": "exact", "answer": "Here is the text exactly as it is in the book:", "sources": srcs, "summary": ""}
        return {"status": "not_found", "answer": "That exact passage is not in my data (it may be a page that could not be read from the scan).", "sources": []}

    arabic_hits = R.search_arabic(db, question)
    if arabic_hits:
        hits = []
        for a in arabic_hits[:1]:
            hits += [a] + R.get_verses(db, a["num"], a["num2"], a["num2"])[:1] + R.get_tafsir(db, a["num"], a["num2"])[:1]
        srcs = [_source(h, i + 1) for i, h in enumerate(hits)]
        return {"status": "ok", "answer": "This Arabic text is found in the Qur'an. Here is the verse with its translation:", "summary": "", "sources": srcs}

    q = R.build_query(question)
    hits = [h for h in R.search(db, q, 12) if h["coverage"] >= MIN_COVERAGE][:MAX_SOURCES]
    # tafsir: the explanation of the verses found, and (for Urdu questions) a direct search in the Urdu tafsir
    seen = {h["ref"] for h in hits}
    extra = R.search_urdu(db, q, 3)
    for h in [h for h in hits if h["kind"] == "quran"][:2]:
        extra += R.get_tafsir(db, h["num"], h["num2"])[:1]
    for h in extra:
        if h["ref"] not in seen and len(hits) < MAX_SOURCES + 3:
            seen.add(h["ref"])
            hits.append(h)
    if not hits:
        return {"status": "not_found", "code": "not_found", "answer": NOT_FOUND, "sources": []}
    srcs = [_source(h, i + 1) for i, h in enumerate(hits)]

    summary = ""
    fn = llm if llm is not None else (call_llm if llm_configured() else None)
    if fn:
        prompt = "Question: " + question + "\n\n" + "\n\n".join(f"[{s['n']}] ({s['ref']}) {s['text']}" for s in srcs)
        summary = validate_summary(fn(SYSTEM, prompt) or "", srcs)
    if summary:
        return {"status": "ok", "answer": summary, "summary": summary, "sources": srcs}
    return {"status": "ok", "code": "passages", "answer": "These passages from the books speak about your question. Read them in full below:",
            "summary": "", "sources": srcs}
