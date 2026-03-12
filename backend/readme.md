**Architecture Overview:**
```
┌──────────────────────────────────────────────────────────┐
│                    FastAPI Gateway                       │
│                    (api/routes.py)                       │
└───────────────────────────┬──────────────────────────────┘
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
      ┌────────────┐  ┌────────────┐  ┌────────────┐
      │ Interpreter│  │   Scanner  │  │  Validator │
      │(LLM-based) │──▶(HTML parser)│──▶(Fix-focused)│
      │            │  │            │  │            │
      │ NL -> JSON │  │Site scanning│  │ Compliance │
      │ Schema     │  │  & diffing  │  │ + confidence│
      └────────────┘  └────────────┘  └────────────┘
              │             │             │
              └─────────────┬─────────────┘
                            ▼
                    ┌──────────────┐
                    │  Audit Log   │
                    │ (immutable)  │
                    └──────────────┘
```

**Project Structure:**
```
backend/
├── main.py                # FastAPI entrypoint
├── config.py              # Settings & env vars
├── requirements.txt
├── models/
│   ├── __init__.py
│   ├── schemas.py         # All Pydantic models
│   └── audit.py           # Audit trail models
├── services/
│   ├── __init__.py
│   ├── interpreter.py     # Module 1: Regulatory Interpreter
│   ├── scanner.py         # Module 2: Scraping & Comparison
│   ├── validator.py       # Module 3: Explainable Validation
│   └── drafter.py         # Module 4: Drafting / Diff Logic
├── core/
│   ├── __init__.py
│   ├── audit_logger.py    # Module 5: Audit Trail
│   └── llm_client.py      # LLM abstraction (OpenAI/Gemini)
├── api/
│   ├── __init__.py
│   └── routes.py          # API endpoints
└── tests/
    └── test_pipeline.py
```
