RAG Chatbot
A low-latency, document-grounded chatbot using RAG, PostgreSQL + pgvector, local ONNX embeddings, FlashRank and Gemini.

Tech Stack
Frontend: React + Vite
Backend: Python + FastAPI
Database: PostgreSQL + pgvector
Embeddings: all-MiniLM-L6-v2 + ONNX Runtime
Retrieval: Vector + Sparse + Lexical
Reranking: FlashRank
LLM: Gemini 3.6 Flash

Run
Backend

cd BE
.venv\Scripts\activate
uvicorn app.main:app --reload --port 8000

Frontend

cd FE
npm install
npm run dev

Open http://localhost:3000.