"""Words people use in Urdu, Roman Urdu, German and Arabic spelling -> English words used in the books.

The books are in English, so a question in another language is turned into English search words.
When an LLM key is set, the LLM does this better; this list makes the bot work with no LLM at all (free, offline).
"""

# one entry: word -> English search words (the first English word is the main one)
_RAW = """
namaz salah salat namaaz نماز gebet beten salat: prayer salat
roza roze rozay sawm siyam fasting روزہ روزے fasten fasten: fasting
ramzan ramadan رمضان ramadhan: ramadan fasting
zakat zakah زکوٰۃ زکات almosen: zakat charity
sadqa sadaqah sadaqa صدقہ صدقات spende: charity
hajj haj حج pilgrimage pilgerfahrt: hajj pilgrimage
umrah umra عمرہ: umra
wudu wuzu وضو ablution: ablution wudu
ghusl غسل: bath ghusl
tayammum تیمم: tayammum dust
nikah shadi shaadi نکاح شادی ehe heirat: marriage
talaq talaaq طلاق scheidung: divorce
sabr صبر geduld: patience
shukr شکر dankbarkeit: thanks grateful
jannat jannah جنت paradies himmel: paradise
jahannam dozakh jahanam جہنم hölle: hell fire
dua duaa دعا bittgebet: supplication invoke
tauba toba توبہ reue: repentance
maafi maghfirat معافی vergebung: forgive forgiveness
gunah gunaah گناہ sünde: sin
walidain walideen والدین eltern: parents
maa ammi ماں mutter: mother
baap والد vater: father
padosi پڑوسی nachbar: neighbour
jhoot jhut جھوٹ lüge lügen: lie lying
ghibat gheebat غیبت: backbiting
amanat امانت anvertrautes: trust
riba sood سود zinsen zins: usury interest
halal حلال: lawful halal
haram حرام: forbidden unlawful haram
qabr قبر grab: grave
qayamat قیامت auferstehung: resurrection judgment
rizq رزق: provision sustenance
ilm علم wissen: knowledge
ghussa غصہ zorn: anger
hasad حسد neid: envy
kibr تکبر: pride arrogance
yateem یتیم waise: orphan
ghareeb غریب miskin مسکین arme: poor needy
bimari بیماری krankheit: sick illness disease
maut موت tod sterben: death
rasool nabi نبی رسول prophet gesandter: messenger prophet
shaitan شیطان satan teufel: satan devil
eman iman ایمان glaube: faith belief
islam اسلام: islam
quran قرآن koran: quran
kalima shahada کلمہ: testimony
masjid مسجد moschee: mosque
juma jumma جمعہ freitag: friday
eid عید: eid
dua-e-qunoot qunoot: qunut
sajda sajdah سجدہ: prostration
ruku رکوع: bowing
qibla qiblah قبلہ: qibla
azan adhan اذان: adhan call
tahajjud تہجد: tahajjud night
witr وتر: witr
sunnat sunnah سنت: sunnah
bidat bidah بدعت: innovation
jihad جہاد: jihad
shirk شرک: polytheism
tawheed tauhid توحید: oneness tauhid
dost dosti دوست freund: friend friendship
dushman دشمن feind: enemy
beti بیٹی tochter: daughter
beta بیٹا sohn: son
biwi بیوی ehefrau: wife
shohar شوہر ehemann: husband
bachay bacche بچے kinder: children
ameer امیر reich: rich wealth
paisa maal مال geld: wealth money
kamai کمائی: earning
vaada وعدہ versprechen: promise
insaaf انصاف gerechtigkeit: justice
zulm ظلم unrecht: oppression
sharab شراب alkohol: wine intoxicant
sood: usury
neend نیند schlaf: sleep
khana کھانا essen: food eat
pani پانی wasser: water
jhoota: lie
musafir مسافر reise: travel traveller
safar سفر: journey travel
ilm-e-deen: knowledge
waqt zeit وقت: time
ashura عاشورہ: ashura
laylatul qadr lailatul قدر: night qadr
"""

GLOSSARY: dict = {}
for _line in _RAW.strip().splitlines():
    if ":" not in _line:
        continue
    left, right = _line.split(":", 1) if _line.count(":") == 1 else (_line.rsplit(":", 1)[0], _line.rsplit(":", 1)[1])
    # the right side holds the English words; the left side holds the trigger words (words ending in ':' on the left are triggers too)
    triggers = [w.strip(":") for w in left.split() if w.strip(":")]
    english = [w for w in right.split() if w]
    for t in triggers:
        GLOSSARY.setdefault(t.lower(), [])
        for e in english:
            if e not in GLOSSARY[t.lower()]:
                GLOSSARY[t.lower()].append(e)

# Famous passages people ask for by name -> (surah, first ayah, last ayah)
NAMED_PASSAGES = {
    "ayat al kursi": (2, 255, 255), "ayatul kursi": (2, 255, 255), "ayat ul kursi": (2, 255, 255), "ayat-ul-kursi": (2, 255, 255),
    "آیت الکرسی": (2, 255, 255), "ayat kursi": (2, 255, 255), "throne verse": (2, 255, 255),
    "surah fatiha": (1, 1, 7), "surah al fatiha": (1, 1, 7), "al-fatiha": (1, 1, 7), "al fatiha": (1, 1, 7), "سورہ فاتحہ": (1, 1, 7),
    "surah ikhlas": (112, 1, 4), "surah al ikhlas": (112, 1, 4), "al-ikhlas": (112, 1, 4), "سورہ اخلاص": (112, 1, 4),
    "surah falaq": (113, 1, 5), "surah al falaq": (113, 1, 5), "al-falaq": (113, 1, 5),
    "surah nas": (114, 1, 6), "surah an nas": (114, 1, 6), "an-nas": (114, 1, 6),
    "surah kausar": (108, 1, 3), "surah al kawthar": (108, 1, 3), "al-kawthar": (108, 1, 3),
    "surah asr": (103, 1, 3), "surah al asr": (103, 1, 3), "al-asr": (103, 1, 3),
}
