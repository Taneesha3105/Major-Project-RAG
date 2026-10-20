# DealLens — AI-assisted M&A Due Diligence

DealLens is a virtual data room for merger and acquisition teams. Users upload the target's financial,
legal, tax and contractual documents (including scanned PDFs). The system extracts, OCRs, chunks and embeds
them, and then provides:

- **Evidence-backed Q&A**: answers from Gemini grounded only in the data room, with numbered citations to the exact document, page and section.
- **AI risk register**: per-workstream detection of risks, contradictions between documents, and missing information, plus an investment-committee executive summary.
- **Due-diligence checklist**: a standard 42-item request list. The AI checks each item against the data room (evidence found, partial, or missing).
- **Deal workflow**: deal stages, team membership, role-based access control, and a full audit trail.

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | React 18, Vite, plain CSS (design tokens, light/dark), React Router, Recharts, react-markdown |
| Backend | Python 3.12, FastAPI, Pydantic v2 |
| Database / ORM | PostgreSQL 18 + pgvector (HNSW) + full-text search · SQLAlchemy 2 (async) · Alembic migrations |
| Document processing | pdfplumber, pypdfium2, python-docx, openpyxl |
| OCR (open source) | RapidOCR (PP-OCR models on ONNX Runtime). Optional fallback: Gemini Vision |
| Embeddings (open source) | Sentence-Transformers `BAAI/bge-small-en-v1.5` (384-d, runs locally) |
| Retrieval | Hybrid: pgvector cosine + PostgreSQL full-text search, fused with Reciprocal Rank Fusion |
| Reranking (open source) | FlashRank `ms-marco-MiniLM-L-12-v2` cross-encoder |
| LLM | Google Gemini (`google-genai` SDK), with streaming and structured JSON output |

## Architecture

```
┌──────────────────────── FE (React + Vite) ────────────────────────┐
│ pages/  ─ components/ ─ context/ (auth, theme, toasts) ─ api/      │
└───────────────┬────────────────────────────────────────────────────┘
                │ REST + Server-Sent Events (/api/v1, JWT bearer)
┌───────────────▼──────────────── BE (FastAPI) ──────────────────────┐
│ controllers/   thin HTTP layer: validation, auth, RBAC  ("C")       │
│ schemas/       Pydantic request/response contracts      ("V")       │
│ services/      business logic, workflows, audit logging             │
│ repositories/  all SQL / data access                                │
│ models/        SQLAlchemy ORM entities                  ("M")       │
│ ai/            Gemini gateway · embeddings · reranker · OCR ·       │
│                hybrid retrieval · prompts                           │
│ ingestion/     extract → OCR → clean → chunk                        │
│ job_queue      background workers for ingestion & AI analysis       │
└───────────────┬────────────────────────────────────────────────────┘
                │ asyncpg
        PostgreSQL + pgvector  (users, deals, documents, chunks+vectors,
                                conversations, findings, checklist, audit)
```

**Ingestion pipeline.** Upload → SHA-256 de-duplication → stored on disk → background job → text extraction
(pages with no text layer are rendered and OCR'd) → normalisation and removal of repeated headers/footers →
structure-aware chunking (page-bounded, heading-aware, sentence overlap) → embeddings → `document_chunks`
(vector + generated `tsvector`) → Gemini summary and key facts.

**Question answering.** Follow-up questions are rewritten into standalone queries → vector top-30 and
keyword top-30 → RRF fusion → FlashRank rerank → top-6 sources → Gemini streams an answer citing `[n]` →
the answer is stored with its citations, retrieval metadata, latency and user feedback (for evaluation).

## Roles and permissions

| Role | Capabilities |
|---|---|
| Administrator | Everything, including user management. Sees all deals. |
| Deal lead | Create deals, manage the deal team, upload/delete documents, run AI, edit findings and checklist |
| Analyst (default sign-up role) | Upload documents, use the assistant, run AI analysis, edit findings and checklist |
| Viewer | Read-only, plus the AI assistant |

Users only see deals they are members of. Managing a deal requires the **lead** membership role, and an
**observer** membership is read-only regardless of the user's platform role.

## Running locally

Prerequisites: PostgreSQL with the **pgvector** extension (`brew install pgvector` on macOS), Python 3.12, and Node 18+.

### 1. Database (one-time)

```bash
psql -d postgres -c "CREATE ROLE mna_app LOGIN PASSWORD 'choose-a-password';"
psql -d postgres -c "CREATE DATABASE mna_diligence OWNER mna_app;"
# Creating the vector extension needs a superuser the first time:
psql -d mna_diligence -c "CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS pg_trgm;"
```

### 2. Backend

```bash
cd BE
python3.12 -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env              # set POSTGRES_PASSWORD, GEMINI_API_KEY, JWT_SECRET_KEY
alembic upgrade head              # create the schema from the ORM migrations
python -m app.seed                # create the admin user (ADMIN_EMAIL / ADMIN_PASSWORD in .env)
uvicorn app.main:app --reload --reload-dir app --port 8000
```

The API docs are at http://localhost:8000/docs. On first start the embedding and reranker models
(~150 MB) download into `BE/.cache/models`.

### 3. Frontend

```bash
cd FE
npm install
npm run dev                        # http://localhost:3000 (proxies /api to :8000)
```

Sign in with the seeded admin (default `admin@deallens.local` / `Admin@12345`, which you should change in
Settings), or create an analyst account on the register page.

### Sample data room

`samples/generate_samples.py` builds a fictional data room: an audited-financials PDF, a **scanned**
management presentation (to exercise OCR), a customer MSA (DOCX) and a customer revenue spreadsheet (XLSX).
Inconsistencies are planted on purpose (FY2024 revenue differs between documents, change-of-control clauses,
an unprovided claim) so the contradiction and risk detection can be demonstrated.

```bash
BE/.venv/bin/python samples/generate_samples.py   # writes samples/data-room/
```

## Database schema management

The schema is defined by the SQLAlchemy models in `BE/app/models/` and versioned with Alembic.

```bash
alembic revision --autogenerate -m "describe change"   # after editing a model
alembic upgrade head
alembic check                                          # verify models and DB are in sync
```

## Tests

```bash
cd BE && pytest
```

## Evaluation hooks

Every assistant message stores its retrieved sources, which of them were cited, the rewritten query,
per-stage retrieval timings, end-to-end latency and thumbs-up/down feedback (`messages.retrieval_meta`,
`messages.feedback`). These cover the methodology's evaluation criteria: retrieval relevance, grounding
(citation coverage) and successful evidence retrieval. `POST /api/v1/deals/{id}/search` exposes raw
hybrid-retrieval results with vector, lexical, fused and rerank scores for retrieval experiments.

## Project layout

```
BE/
  alembic/                 migrations (ORM-driven)
  app/
    ai/                    llm.py (Gemini) · embeddings.py · reranker.py · ocr.py · retrieval.py · prompts.py
    controllers/           auth, users, deals, documents, chat, diligence, dashboard + deps (RBAC)
    core/                  config, security (JWT/bcrypt), permissions, exceptions, logging
    db/                    declarative base, async session
    ingestion/             extractors, cleaning, chunker
    models/                ORM entities and enums
    repositories/          data access
    schemas/               Pydantic contracts
    services/              business logic, job queue, storage, checklist template
    main.py · seed.py
  tests/
FE/
  src/
    api/                   fetch client (JWT, uploads with progress, SSE) + endpoint services
    components/            ui primitives, deals, documents, chat, risks
    context/               auth, theme, toasts
    layouts/               app shell, auth layout
    pages/                 dashboard, deals, admin, settings, deal/* workspace tabs
    styles/                tokens, base, components, layout, pages
samples/                   sample data-room generator
legacy/                    previous chatbot prototype (kept for reference; safe to delete)
```
