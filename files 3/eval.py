"""Accuracy test for issue classification + urgency. Run: python eval.py
Tests the classifier prompt only (not the full agent loop). Have native speakers review the test texts."""
import json, os, collections
from anthropic import Anthropic
from dotenv import load_dotenv
load_dotenv(); client = Anthropic(); MODEL = os.getenv("MODEL", "claude-sonnet-5-5")
# (language, text, expected_category, expected_urgency)
T = [
("English","I bought a plot but another person says it belongs to him.","property","routine"),
("Hindi","मेरी जमीन पर पड़ोसी ने कब्जा कर लिया है।","property","routine"),
("Kannada","ನಾನು ಖರೀದಿಸಿದ ನಿವೇಶನದ ಮೇಲೆ ಇನ್ನೊಬ್ಬರು ಹಕ್ಕು ಸಾಧಿಸುತ್ತಿದ್ದಾರೆ.","property","routine"),
("Tamil","நான் வாங்கிய நிலத்துக்கு வேறொருவர் உரிமை கோருகிறார்.","property","routine"),
("English","My company terminated me yesterday without notice.","employment","routine"),
("Hindi","कंपनी ने बिना नोटिस के मुझे नौकरी से निकाल दिया।","employment","routine"),
("Telugu","నా జీతం మూడు నెలలుగా చెల్లించలేదు.","employment","routine"),
("Punjabi","ਮੈਨੂੰ ਨੌਕਰੀ ਤੋਂ ਕੱਢ ਦਿੱਤਾ ਗਿਆ ਹੈ ਅਤੇ ਤਨਖਾਹ ਨਹੀਂ ਮਿਲੀ।","employment","routine"),
("Hindi","मेरे पति मुझे मारते हैं और मुझे अपनी जान का डर है।","family","immediate_escalation"),
("English","I want a divorce by mutual consent. How does it work?","family","routine"),
("Malayalam","എന്റെ ഭർത്താവ് വിവാഹമോചനം ആവശ്യപ്പെടുന്നു.","family","routine"),
("English","The phone I bought is defective and the seller refuses a refund.","consumer","routine"),
("Bengali","আমি যে ফ্রিজ কিনেছি সেটা কাজ করছে না, দোকানদার টাকা ফেরত দিচ্ছে না।","consumer","routine"),
("Marathi","ऑनलाइन मागवलेली वस्तू आली नाही आणि पैसे परत मिळाले नाहीत.","consumer","routine"),
("English","A customer's cheque for 2 lakh bounced 10 days ago.","cheque_bounce","time_sensitive"),
("Gujarati","મારો ચેક બાઉન્સ થયો છે અને મને નોટિસ મળી છે.","cheque_bounce","time_sensitive"),
("Hinglish","Mere landlord ne kal tak ghar khali karne ka notice diya hai.","property","urgent"),
("Kanglish","Nanna property case hearing naale ide, nanage lawyer beku.","property","urgent"),
("English","I received a legal notice about unpaid rent and must reply within 2 days.","property","urgent"),
("English","I want to register a company next month.","other","routine"),
]
PROMPT = """Classify this legal intake message. Categories: property, employment, family, consumer, cheque_bounce, other.
Urgency: routine, time_sensitive (deadline within ~15 days), urgent (deadline/hearing within ~3 days), immediate_escalation (safety threat).
Reply ONLY JSON: {"category":"...","urgency":"..."}\n\nMessage: """
res, by = [], collections.defaultdict(lambda: [0, 0])
for lang, text, cat, urg in T:
    out = client.messages.create(model=MODEL, max_tokens=60, messages=[{"role": "user", "content": PROMPT + text}]).content[0].text
    try: g = json.loads(out[out.index("{"):out.rindex("}") + 1])
    except Exception: g = {}
    ok_c, ok_u = g.get("category") == cat, g.get("urgency") == urg
    by[lang][0] += ok_c; by[lang][1] += 1
    res.append({"lang": lang, "text": text, "expected": [cat, urg], "got": [g.get("category"), g.get("urgency")], "cat_ok": ok_c, "urg_ok": ok_u})
n = len(T)
print(f"Category accuracy: {sum(r['cat_ok'] for r in res)}/{n}   Urgency accuracy: {sum(r['urg_ok'] for r in res)}/{n}")
for l, (a, b) in by.items(): print(f"  {l}: {a}/{b}")
json.dump(res, open("eval_results.json", "w"), indent=1, ensure_ascii=False)
print("Mistakes saved in eval_results.json")
