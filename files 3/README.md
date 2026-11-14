# NyayaConnect AI - multilingual legal intake agent
Agent loop: PLAN (separate LLM call) -> TOOL-USE (up to 8 iterations) -> ACTION (save case brief, book appointment).
Tools: lookup_legal_kb (dataset), check_urgency (rules), geocode_location (OpenStreetMap API), translate_text (Sarvam AI API), match_lawyers (dataset), generate_case_brief, book_appointment.
Datasets: backend/data/lawyers.json, backend/data/legal_kb.json (hand-made sample data).

Languages: all 22 scheduled Indian languages + English (auto-detect, language picker, browser voice input where supported).

## Run
cd backend && pip install -r requirements.txt && cp .env.example .env  (add key)
uvicorn main:app --reload   -> open http://localhost:8000

## AI usage disclosure
Built with Claude (AI coding assistant) during the hackathon for code generation; team reviewed and tested all code.

Lawyer dashboard: http://localhost:8000/lawyer.html (edit AI briefs, mark verified).

Lawyer dashboard needs a passcode (env LAWYER_PASSCODE, default lawyer123 - change it).
Accuracy test: cd backend && python eval.py (20 multilingual queries; writes eval_results.json).
