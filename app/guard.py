"""Islam-only guard. Runs BEFORE any search or LLM call.

Strict rules of this bot (they cannot be switched off by the user, in any language):
 1. It never says or accepts that another religion is true, equal to Islam, or better than Islam.
 2. It never teaches, quotes, prays or preaches another religion, and never helps someone leave Islam or convert others away.
 3. It never insults or mocks Allah, the Prophet (peace be upon him), the Qur'an, the Companions or Muslims.
 4. It ignores "ignore your rules", role-play, "developer mode" and other tricks (prompt injection / jailbreak).
 5. It does not help with magic, fortune telling, horoscopes or anything that is shirk.
 6. It does not spread hatred or violence, against anyone (the Qur'an orders justice and kindness: 60:8).
 7. It gives no fatwa; for rulings it sends the person to a scholar.
 When a rule is hit, the bot does not argue: it answers with the authentic words of the Qur'an (tawheed and the
 religion of Islam), printed word for word from the database. Questions that are ABOUT other religions from the
 Islamic point of view ("What does the Qur'an say about Jesus?") are still answered normally from the books.
Works for English, Roman Urdu, Urdu, German and Arabic wording. No third party code.
"""
import re
import unicodedata
from typing import Optional

GUARD_TEXT = ("I can only answer from Islam, with the Qur'an and the authentic hadith. I cannot follow, compare or promote "
              "other religions, and I cannot change these rules. Here is what Allah says in the Qur'an:")

# Verses shown when a rule is hit: (surah, first ayah, last ayah)
GUARD_VERSES = [(112, 1, 4), (3, 19, 19), (3, 85, 85), (2, 256, 256)]


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))           # removes Arabic/Urdu marks and accents
    s = s.replace("’", "'").replace("ـ", "")
    return re.sub(r"\s+", " ", s).strip()


# 1) Tricks to make the bot drop its rules.
_INJECTION = re.compile("|".join([
    r"\b(ignore|forget|disregard|override|bypass)\b.{0,25}\b(instruction|rule|prompt|guideline|restriction|polic)",
    r"\b(pretend|imagine|act|roleplay|role-play|behave)\b.{0,20}\b(you are|you're|as|like)\b.{0,30}\b(not muslim|non-muslim|christian|atheist|priest|pastor|hindu|free|no rules|unrestricted|without rules)",
    r"\b(jailbreak|developer mode|dan mode|do anything now|system prompt|reveal your prompt)\b",
    r"\b(you are now|from now on you)\b",
    r"\bnew (rules|instructions)\b",
    r"\bignoriere\b.{0,25}(anweisung|regel)", r"\bvergiss\b.{0,25}(anweisung|regel)", r"\btu so als (ob )?du\b",
    r"\bpichli\b.{0,15}(hidayat|hidayaat|batein)\b.{0,10}\b(bhool|bhul)", r"\b(rules|qawaid)\b.{0,10}\b(bhool|bhul|tod)",
    r"پچھلی ہدایات|ہدایات بھول|اپنے اصول (بھول|توڑ)|قوانین بھول",
    r"تجاهل (كل )?(التعليمات|القواعد)|انس (كل )?(التعليمات|القواعد)",
]), re.I | re.S)

# 2) Words that name other beliefs.
_OTHER = re.compile("|".join([
    r"\b(christian\w*|bible|church|jesus is (god|the son)|son of god|trinity|hindu\w*|gita|vedas?|buddh\w*|sikh\w*|judaism|torah|talmud|atheis\w*|agnostic\w*|polytheis\w*|idol\w*|karma|reincarnation|zodiac|horoscope|astrolog\w*|tarot|ouija|fortune.?tell\w*|black magic|witchcraft)\b",
    r"\b(isai|isaiyat|hindu|dharam|dharm|mandir|girja|girjaghar|bhagwan|murti|but parast|butparast|nujoomi|jyotish|kala jadu)\b",
    r"\b(christentum|christlich\w*|bibel|kirche|hinduismus|buddhismus|judentum|atheis\w*|gotter|gotzen|horoskop|sternzeichen|astrologie|tarot|schwarze magie)\b",
    r"عیسائی\w*|مسیحی\w*|انجیل|ہندو\w*|بدھ مت|سکھ مت|یہودی\w*|بت پرست\w*|الحاد|دہریہ|برج|زائچہ|کالا جادو|جادو ٹونا",
    r"مسيحي\w*|الكتاب المقدس|الانجيل|هندوس\w*|بوذ\w*|الحاد|ملحد|اصنام|الابراج|السحر",
]), re.I)

# 3) Asking to promote, teach, convert, or prove another belief right.
_PROMOTE = re.compile("|".join([
    r"\b(all|every|sab|alle|tamam)\b.{0,12}\b(religions?|faiths?|mazahib|mazhab|mazaheb|religionen)\b.{0,20}\b(same|equal|true|right|one|barabar|ek|gleich|wahr)\b",
    r"\b(is|are|hai|ist|sind)\b.{0,6}\b(the )?(true|right|better|best|correct|sahi|sach|sachcha|wahr|richtig|besser)\b",
    r"\b(better|superior|truer|more true) than islam\b", r"\b(prove|proof|convince|argue)\b", r"\bconvert\w*\b", r"\bbecome (a )?(christian|hindu|buddhist|sikh|jew|atheist)\b",
    r"\b(teach|show|tell|write|give|sikha\w*|bata\w*|likh\w*|lehre|zeig\w*|schreib\w*)\b.{0,25}\b(prayer|worship|ritual|verse|sermon|hymn|mantra|pooja|puja|gebet|vers|dua|ibadat|ibadah)\b",
    r"\b(quote|read|recite|give me|dikha\w*|sunao|zitiere)\b.{0,15}\b(bible|gita|torah|vedas?|bibel)\b",
    r"\b(horoscope|zodiac|fortune|tarot|astrolog\w*|black magic|witchcraft|spell|horoskop|kala jadu|jadu|sehr)\b",
    r"\b(choose|pick|follow)\b.{0,15}\b(religion|faith)\b", r"\bwhich religion is\b", r"\bkaun sa (mazhab|dharam|din)\b.{0,15}\b(sahi|sach|behtar|best)\b",
    r"سب مذاہب|تمام مذاہب|مذہب بدل|عیسائی بن|ہندو بن|سچا مذہب|کون سا مذہب|ثابت کرو|برج|زائچہ",
    r"كل الاديان|جميع الاديان|اثبت|تحول الى|غير دينك",
]), re.I)

# 3b) "All religions are equal / which religion is right": refused even when no religion is named.
_EQUAL = re.compile("|".join([
    r"\b(all|every|sab|alle|tamam)\b.{0,12}\b(religions?|faiths?|mazahib|mazhab|mazaheb|dharam|religionen)\b.{0,20}\b(same|equal|true|right|one|barabar|ek|gleich|wahr|sahi)\b",
    r"\bwhich religion is\b", r"\bkaun sa (mazhab|dharam|din)\b.{0,15}\b(sahi|sach|behtar|best)\b", r"\bwelche religion ist\b",
    r"سب مذاہب|تمام مذاہب|سچا مذہب|کون سا مذہب", r"كل الاديان|جميع الاديان",
]), re.I)

# 4) Attacks on Islam, always refused.
_ATTACK = re.compile("|".join([
    r"\b(islam|quran|qur'an|koran|muslims?|hadith|sharia)\b.{0,30}\b(is|are|was|were)?\s*(false|fake|wrong|lie|lies|evil|terroris\w*|backward|corrupt\w*|man.?made|invented|myth\w*|stupid|violent|barbaric)\b",
    r"\b(prophet|muhammad|mohammad|mohammed|allah|aisha|companions?)\b.{0,30}\b(liar|fake|fraud|false|pedophile|paedophile|terrorist|evil|invented|made up|insult|mock)\b",
    r"\b(mock|insult|ridicule|curse|abuse|make fun of)\b.{0,25}\b(allah|prophet|muhammad|quran|islam|muslims)\b",
    r"\bthere is no (god|allah)\b", r"\bgod does(n't| not) exist\b", r"\ballah (is not|does not|doesn't) exist\b",
    r"\b(islam|quran|koran)\b.{0,12}\b(jhoot\w*|galat|bakwas|fake|jhuta|jhoota)\b", r"\b(nabi|rasool|allah|muhammad)\b.{0,15}\b(jhoot\w*|jhuta|jhoota|galat)\b",
    r"\b(islam|koran|quran|mohammed|muhammad)\b.{0,15}\b(ist )?(falsch|erfunden|bose|boese|lugner|terror\w*|gefahrlich|dumm)\b", r"\bes gibt keinen gott\b",
    r"(اسلام|قرآن|قران|نبی|رسول|اللہ|محمد).{0,20}(جھوٹ\w*|غلط|بکواس|دہشت|فراڈ)", r"خدا (نہیں|موجود نہیں)|کوئی خدا نہیں",
    r"(الاسلام|القران|القرآن|النبي|محمد).{0,20}(باطل|كذب|كاذب|مزيف|ارهاب)", r"لا يوجد اله|لا اله موجود",
]), re.I | re.S)

# A question is "inside Islam" when it talks from the Islamic point of view.
_ISLAMIC_FRAME = re.compile("|".join([
    r"\b(islam\w*|quran|qur'an|koran|hadith|hadees|sunnah|tafs?ee?r|surah|ayah|ayat|prophet|rasool|nabi|muhammad|allah|muslims?|sahih|bukhari|according to|says? about|say about|does the|what does|kya kehta|kya kehti|kya farmata|was sagt|laut)\b",
    r"اسلام|قرآن|قران|حدیث|سنت|تفسیر|سورۃ|آیت|نبی|رسول|اللہ|مسلمان|الاسلام|القرآن|الحديث|النبي|الله",
]), re.I)

# Safe questions that only ask what Islam says (not blocked even though they name another religion).
_SAFE_ASK = re.compile(r"(what does (the )?(quran|qur'an|islam|hadith|prophet).{0,20}(say|teach)|according to (the )?(quran|islam|hadith)|(quran|islam).{0,15}(kya|ke bare|ke baray)|was sagt (der )?(koran|islam)|قرآن.{0,15}(کیا|بارے)|ماذا يقول)", re.I)

# Hate / violence / immorality, refused whatever the faith.
_HARM = re.compile("|".join([
    r"\b(how to|ways to|help me)\b.{0,20}\b(kill|attack|bomb|harm|hurt|hate|lynch)\b.{0,20}\b(christian\w*|hindus?|jews?|jewish|non.?muslims?|muslims?|shia|sunni|people)\b",
    r"\bkill (all )?(the )?(christian\w*|hindus?|jews?|non.?muslims?|kafir\w*|infidels?|shia|sunni)\b",
    r"\b(porn\w*|sex(ual)? (story|chat|roleplay)|nude)\b",
]), re.I)


def check(question: str) -> Optional[str]:
    """Returns the rule that was hit ('injection', 'attack', 'other_religion', 'harm') or None when the question is fine."""
    q = _norm(question)
    if not q:
        return None
    if _INJECTION.search(q):
        return "injection"
    if _HARM.search(q):
        return "harm"
    if _ATTACK.search(q):
        return "attack"
    if _EQUAL.search(q):
        return "other_religion"
    other = _OTHER.search(q)
    if other:
        framed = bool(_ISLAMIC_FRAME.search(q)) or bool(_SAFE_ASK.search(q))
        promote = bool(_PROMOTE.search(q))
        if not framed:
            return "other_religion"          # e.g. "teach me the bible", "my horoscope today"
        if promote:
            return "other_religion"          # e.g. "prove that christianity is true", "is hinduism better than islam"
    elif _PROMOTE.search(q) and re.search(r"(horoscope|zodiac|tarot|astrolog|black magic|witchcraft|jadu|sehr|horoskop|برج|زائچہ|السحر)", q):
        return "other_religion"
    return None


def verses_for_guard(db, retrieval, source_fn) -> list:
    """The Qur'an passages shown with a refusal: Arabic first, then the translation."""
    out = []
    for s, a, b in GUARD_VERSES:
        ar = retrieval.get_arabic(db, s, a)
        tr = retrieval.get_verses(db, s, a, b)
        if ar and s == 112:
            out.append(ar)
        out += tr
    return [source_fn(h, i + 1) for i, h in enumerate(out)]
