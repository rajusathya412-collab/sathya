"""NyayaConnect AI - agent backend. Loop: PLAN -> TOOL-USE (repeat) -> ACTION."""
import json, os, uuid
from pathlib import Path
import httpx
from anthropic import Anthropic
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()
D = Path(__file__).parent / "data"
LAWYERS = json.loads((D / "lawyers.json").read_text())
KB = json.loads((D / "legal_kb.json").read_text())
STORE = D / "store.json"  # persisted cases + bookings
client = Anthropic()
MODEL = os.getenv("MODEL", "claude-sonnet-5-5")
app = FastAPI(title="NyayaConnect AI")

def save(kind, rec):
    db = json.loads(STORE.read_text()) if STORE.exists() else {"cases": [], "bookings": []}
    db[kind].append(rec); STORE.write_text(json.dumps(db, indent=2, ensure_ascii=False))

# ---------------- TOOLS ----------------
def lookup_legal_kb(category):  # tool 1: dataset lookup
    return KB.get(category, {"error": "unknown category", "known": list(KB)})

def check_urgency(deadline_days=None, safety_threat=False):  # tool 2: rule engine
    if safety_threat: return {"level": "immediate_escalation", "action": "Call 112 / 181 now"}
    if deadline_days is None: return {"level": "routine"}
    if deadline_days <= 3: return {"level": "urgent"}
    return {"level": "time_sensitive" if deadline_days <= 15 else "routine"}

def geocode_location(place):  # tool 3: EXTERNAL API (OpenStreetMap Nominatim)
    r = httpx.get("https://nominatim.openstreetmap.org/search",
                  params={"q": place + ", India", "format": "json", "limit": 1, "addressdetails": 1},
                  headers={"User-Agent": "nyayaconnect-hackathon"}, timeout=10).json()
    if not r: return {"error": "not found"}
    a = r[0]["address"]
    return {"city": a.get("city") or a.get("town") or a.get("state_district"), "state": a.get("state")}

def match_lawyers(category, language, city=""):  # tool 4: dataset + scoring
    out = []
    for l in LAWYERS:
        if category not in l["areas"]: continue
        score = 3 + (2 if language in l["languages"] else 0) + (2 if city and city.lower() in l["city"].lower() else 0)
        out.append({**l, "score": score, "language_match": language in l["languages"]})
    return sorted(out, key=lambda x: -x["score"])[:3]

SARVAM = {"English":"en-IN","Hindi":"hi-IN","Kannada":"kn-IN","Tamil":"ta-IN","Telugu":"te-IN","Malayalam":"ml-IN","Bengali":"bn-IN","Marathi":"mr-IN","Gujarati":"gu-IN","Punjabi":"pa-IN","Odia":"od-IN"}
def translate_text(text, source_language, target_language):  # tool 7: EXTERNAL API (Sarvam AI translate)
    key = os.getenv("SARVAM_API_KEY")
    if not key: return {"error": "SARVAM_API_KEY not set; translate yourself and flag for human review"}
    src, tgt = SARVAM.get(source_language), SARVAM.get(target_language)
    if not src or not tgt: return {"error": "language not supported by translation API", "supported": list(SARVAM)}
    r = httpx.post("https://api.sarvam.ai/translate", headers={"api-subscription-key": key},
                   json={"input": text, "source_language_code": src, "target_language_code": tgt}, timeout=20)
    return {"translated_text": r.json().get("translated_text"), "provider": "Sarvam AI"} if r.status_code == 200 else {"error": r.text[:200]}

def generate_case_brief(category, summary, facts, missing_info, urgency, language):  # ACTION 1
    rec = {"case_id": "NC-" + uuid.uuid4().hex[:4].upper(), "category": category, "summary": summary,
           "facts": facts, "missing_info": missing_info, "urgency": urgency, "client_language": language,
           "status": "pending lawyer verification", "disclaimer": "Intake summary, not legal advice."}
    save("cases", rec); return rec

def book_appointment(case_id, lawyer_id, slot):  # ACTION 2
    l = next((x for x in LAWYERS if x["id"] == lawyer_id), None)
    if not l or slot not in l["slots"]: return {"error": "slot unavailable", "slots": l["slots"] if l else []}
    rec = {"booking_id": "BK-" + uuid.uuid4().hex[:4].upper(), "case_id": case_id, "lawyer": l["name"], "slot": slot}
    l["slots"].remove(slot); save("bookings", rec); return rec

FUNCS = {f.__name__: f for f in [lookup_legal_kb, check_urgency, geocode_location, match_lawyers, translate_text, generate_case_brief, book_appointment]}
S = lambda props, req: {"type": "object", "properties": props, "required": req}
STR, NUM = {"type": "string"}, {"type": "number"}
TOOLS = [
 {"name": "lookup_legal_kb", "description": "Get documents/questions/notes for a legal category: property, employment, family, consumer, cheque_bounce.", "input_schema": S({"category": STR}, ["category"])},
 {"name": "check_urgency", "description": "Classify urgency from days until deadline/hearing and safety threat.", "input_schema": S({"deadline_days": NUM, "safety_threat": {"type": "boolean"}}, [])},
 {"name": "geocode_location", "description": "Resolve a place the client mentions into city/state (external API).", "input_schema": S({"place": STR}, ["place"])},
 {"name": "match_lawyers", "description": "Find best lawyers by category, client language and city.", "input_schema": S({"category": STR, "language": STR, "city": STR}, ["category", "language"])},
 {"name": "translate_text", "description": "Translate text between Indian languages and English via Sarvam AI. Use it to cross-check the English brief for the client's statement when the client's language is not Hindi/English.", "input_schema": S({"text": STR, "source_language": STR, "target_language": STR}, ["text", "source_language", "target_language"])},
 {"name": "generate_case_brief", "description": "ACTION: save a structured English case brief for the lawyer.", "input_schema": S({"category": STR, "summary": STR, "facts": {"type": "array", "items": STR}, "missing_info": {"type": "array", "items": STR}, "urgency": STR, "language": STR}, ["category", "summary", "facts", "missing_info", "urgency", "language"])},
 {"name": "book_appointment", "description": "ACTION: book a slot with a lawyer. Only after the client confirms a lawyer and slot.", "input_schema": S({"case_id": STR, "lawyer_id": STR, "slot": STR}, ["case_id", "lawyer_id", "slot"])},
]

SYSTEM = """You are NyayaConnect, a multilingual legal INTAKE agent for India (not a lawyer; never give legal opinions).
Detect the client's language automatically. Support ALL Indian languages (the 22 scheduled languages: Assamese, Bengali, Bodo, Dogri, Gujarati, Hindi, Kannada, Kashmiri, Konkani, Maithili, Malayalam, Manipuri, Marathi, Nepali, Odia, Punjabi, Sanskrit, Santali, Sindhi, Tamil, Telugu, Urdu) plus English, in native script or romanized/code-mixed text (Hinglish, Kanglish). Reply in the same language and script the client uses. If you are not confident in a language, say so, reply in simple Hindi or English, and flag it for human translator review. Briefs are always in English and must include the client's original language name.
Workflow: understand the problem -> lookup_legal_kb -> check_urgency -> geocode_location if a place is mentioned ->
for non-English clients cross-check key statements with translate_text -> ask the client for missing key facts (max 3 questions, one turn) -> generate_case_brief -> match_lawyers -> offer slots ->
book_appointment only after the client confirms. If safety is at risk, say to call 112 and escalate. Never invent facts or slots."""

class Chat(BaseModel):
    lang: str = "auto"
    messages: list  # [{role, content}] plain text history

@app.post("/api/chat")
def chat(body: Chat):
    trace, msgs, outputs = [], list(body.messages), {}
    sysmsg = SYSTEM + f"\nClient-selected language: {body.lang} ('auto' = detect it)."
    # 1) PLAN - separate reasoning step, no tools
    plan = client.messages.create(model=MODEL, max_tokens=400, system=sysmsg + "\nOutput ONLY a JSON list of 3-5 short plan steps for this turn.", messages=msgs)
    trace.append({"type": "plan", "text": plan.content[0].text})
    msgs.append({"role": "user", "content": msgs[-1]["content"] + f"\n\n[Agent plan: {plan.content[0].text}]"}); msgs.pop(-2)
    # 2) TOOL-USE loop -> 3) ACTION tools write to the store
    for _ in range(8):
        r = client.messages.create(model=MODEL, max_tokens=1500, system=sysmsg, tools=TOOLS, messages=msgs)
        msgs.append({"role": "assistant", "content": r.content})
        if r.stop_reason != "tool_use":
            return {"reply": "".join(b.text for b in r.content if b.type == "text"), "trace": trace, "outputs": outputs}
        results = []
        for b in r.content:
            if b.type != "tool_use": continue
            try: res = FUNCS[b.name](**b.input)
            except Exception as e: res = {"error": str(e)}
            trace.append({"type": "tool", "name": b.name, "input": b.input, "output": res})
            if b.name in ("generate_case_brief", "match_lawyers", "book_appointment"): outputs[b.name] = res
            results.append({"type": "tool_result", "tool_use_id": b.id, "content": json.dumps(res, ensure_ascii=False)})
        msgs.append({"role": "user", "content": results})
    return {"reply": "Sorry, I could not finish. Please try again.", "trace": trace, "outputs": outputs}

def lawyer_only(x_passcode: str = Header("")):  # simple role gate for the lawyer portal
    if x_passcode != os.getenv("LAWYER_PASSCODE", "lawyer123"): raise HTTPException(401, "Invalid passcode")

class Edit(BaseModel):
    summary: str
    facts: list
    missing_info: list

def load():
    return json.loads(STORE.read_text()) if STORE.exists() else {"cases": [], "bookings": []}

@app.get("/api/cases", dependencies=[Depends(lawyer_only)])
def cases(): return load()

@app.post("/api/cases/{case_id}/verify", dependencies=[Depends(lawyer_only)])
def verify(case_id: str, e: Edit):
    db = load()
    for c in db["cases"]:
        if c["case_id"] == case_id:
            c.update(summary=e.summary, facts=e.facts, missing_info=e.missing_info, status="verified by lawyer")
            STORE.write_text(json.dumps(db, indent=2, ensure_ascii=False)); return c
    return {"error": "case not found"}

app.mount("/", StaticFiles(directory=Path(__file__).parent.parent / "frontend", html=True), name="ui")
