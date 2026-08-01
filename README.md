# 🧠 DocuBrain AI — OCR + RAG Document Chat

> Upload scanned documents (PDF/images), extract text with **PaddleOCR**, review and correct OCR output side-by-side, then **chat with your documents** using a RAG pipeline powered by **LangChain + Google Gemini**.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18+-61DAFB?logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-5+-3178C6?logo=typescript&logoColor=white)
![TailwindCSS](https://img.shields.io/badge/Tailwind_CSS-3+-06B6D4?logo=tailwindcss&logoColor=white)
![LangChain](https://img.shields.io/badge/LangChain-RAG-1C3C3C?logo=langchain&logoColor=white)

---

## ✨ Key Features

| Feature | Description |
|---|---|
| 📄 **Document Upload** | Drag & drop PDF, PNG, JPG, TIFF files (up to 25MB) with real-time progress |
| 🔍 **PaddleOCR Extraction** | Multi-block text extraction with bounding boxes and confidence scores |
| 📝 **Side-by-Side OCR Review** | Compare extracted text blocks vs editable text with word count |
| ⏳ **Async Processing with Live Status** | OCR & indexing run as background tasks with auto-polling status updates |
| 🧩 **LangChain Chunking** | Recursive text splitting (500 chars, 100 overlap) for optimal retrieval |
| 🎯 **Hybrid Vector Search** | Cosine similarity + keyword BM25 with Reciprocal Rank Fusion (RRF) |
| 💬 **RAG Chat with Streaming** | Real-time SSE token streaming via async Gemini API with source citations |
| 🔄 **Persistent State Management** | React Context API preserves state across page navigations |
| 🛡️ **Prompt Injection Guard** | Input sanitizer detects and neutralizes injection patterns |
| 🌙 **Dark/Light Theme** | Glassmorphism UI with smooth theme transitions |
| 🤖 **Gemini AI Integration** | Google Gemini embeddings + chat generation (works offline with fallback) |

---

## 🏗️ Architecture

```
┌──────────────────────┐          ┌──────────────────────────────┐
│   React + TypeScript │  REST/   │   FastAPI Backend             │
│   Vite + Tailwind    │  SSE     │                              │
│                      │◄────────►│   /documents/upload          │
│   Pages:             │          │   /documents/{id}/review     │
│   • Dashboard        │          │   /documents/{id}/confirm    │
│   • Upload & OCR     │          │   /chat/stream (SSE)         │
│   • RAG Chat         │          │   /rag/search                │
│   • Document Library │          │                              │
└──────────────────────┘          │   Services:                  │
                                  │   ├── OCR (PaddleOCR/PyPDF)  │
                                  │   ├── Embeddings (Gemini)    │
                                  │   ├── RAG (LangChain + RRF)  │
                                  │   └── Sanitizer              │
                                  │                              │
                                  │   Storage: SQLite + JSON     │
                                  │   vectors for embeddings     │
                                  └──────────────────────────────┘
```

---

## 🔄 How It Works

```
Upload PDF/Image
      │
      ▼
┌─────────────┐    ┌──────────────┐    ┌──────────────┐
│  PaddleOCR  │───►│  Side-by-Side │───►│   LangChain  │
│  Extraction │    │  OCR Review   │    │   Chunking   │
└─────────────┘    └──────────────┘    └──────┬───────┘
                                              │
                                              ▼
                                    ┌──────────────────┐
                                    │  Gemini Embeddings│
                                    │  (768-dim vectors)│
                                    └──────┬───────────┘
                                           │
                                           ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  SSE Stream  │◄───│  Gemini LLM  │◄───│ Hybrid Search│
│  + Citations │    │  Generation  │    │ (Vector+BM25)│
└──────────────┘    └──────────────┘    └──────────────┘
```

---

## 🚀 Quick Start

### Prerequisites
- **Python 3.10 – 3.12** with pip — **not 3.13/3.14**: `paddlepaddle` (the engine
  behind PaddleOCR) publishes no wheels for them, and without it every scan fails.
- **Node.js 18+** with npm

### 1. Clone & Setup Backend

```bash
cd backend

# Create virtual environment (use a 3.12 interpreter explicitly if it isn't your default)
py -3.12 -m venv venv    # Windows
python3.12 -m venv venv  # Mac/Linux

# Activate (Windows)
venv\Scripts\activate
# Activate (Mac/Linux)
source venv/bin/activate

# Install dependencies (first run downloads the PP-OCR models, ~100MB)
pip install -r requirements.txt
```

Verify the OCR engine actually loaded before uploading anything — `GET /health`
reports `ocr.available`, and the dashboard shows the same state:

```bash
curl http://localhost:8000/health
# {"status":"healthy","ocr":{"engine":"PaddleOCR","available":true,"error":null}, ...}
```

If it reports `degraded`, OCR is not running and scans will fail with an explicit
error rather than silently producing placeholder text.

### 2. Configure Environment

```bash
# Copy the example and optionally add your Gemini API key
cp .env.example .env
# Edit .env and paste your key from https://aistudio.google.com/apikey
```

> **Note:** The app works without a Gemini API key — it falls back to local lexical
> embeddings and answers by quoting the best-matching retrieved passage. Add the key
> for synthesized answers. OCR itself never depends on the key.

### 3. Start Backend

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

### 4. Setup & Start Frontend

```bash
cd frontend
npm install
npm run dev
```

### 5. Open the App

Visit **http://localhost:3000** — no login required, start uploading documents immediately!

---

## 📁 Project Structure

```
OCR_Project/
├── backend/
│   ├── app/
│   │   ├── api/v1/           # REST endpoints (ingestion, chat, rag, health)
│   │   ├── core/             # Middleware, logging, prompt sanitizer
│   │   ├── db/               # SQLAlchemy models, vector store repository
│   │   ├── services/         # OCR, embeddings, RAG pipeline
│   │   ├── config.py         # App configuration
│   │   └── main.py           # FastAPI entry point
│   ├── requirements.txt
│   └── tests/
├── frontend/
│   ├── src/
│   │   ├── components/       # Navbar, Sidebar
│   │   ├── pages/            # Dashboard, Upload, Chat, Documents
│   │   ├── services/         # API client + SSE stream reader
│   │   ├── context/          # ThemeContext, AppContext (global state)
│   │   └── types/            # TypeScript interfaces
│   └── package.json
├── .env.example
├── .gitignore
└── README.md
```

---

## 🧪 Tech Stack Deep Dive

| Layer | Technology | Purpose |
|---|---|---|
| **Backend** | FastAPI (async) | High-performance REST API with SSE streaming |
| **OCR** | PaddleOCR + PyPDF | PDF text layer where present, PaddleOCR on scanned pages |
| **RAG** | LangChain | Recursive text chunking + prompt templating |
| **Embeddings** | Google Gemini `gemini-embedding-001` | 768-dim semantic vectors (batched) |
| **Search** | Cosine similarity + BM25 RRF | Hybrid retrieval for accuracy |
| **Generation** | Google Gemini `gemini-2.5-flash` | Grounded response generation |
| **Database** | SQLite + SQLAlchemy | Zero-config persistent storage |
| **Frontend** | React 18 + TypeScript + Vite | Modern SPA with type safety |
| **Styling** | Tailwind CSS | Dark/light theme, glassmorphism, micro-animations |
| **Safety** | Prompt injection sanitizer | Regex-based input defense |

---

## 🔑 Gemini API Key (Optional)

1. Go to [Google AI Studio](https://aistudio.google.com/apikey)
2. Create a new API key
3. Add it to your `.env` file: `GEMINI_API_KEY=your-key-here`

Without a key, the app still works using:
- **Local lexical embeddings** (hashed bag-of-words) so cosine similarity still
  tracks real word overlap and retrieval returns useful passages
- **Grounded extract responses** that quote directly from retrieved document chunks

Chunks record which embedding model produced them. Vectors from different models
are not comparable, so after switching models a document must be re-indexed —
retrieval skips mismatched chunks and logs a warning naming the affected files.

## 🔁 Document Lifecycle

```
uploaded → processing (PaddleOCR) → ocr_ready → indexing → indexed
                    │                              │
                    └──────────► failed ◄──────────┘   (POST /documents/{id}/reprocess to retry)
```

Background work dies with the process, so anything left in `processing` or
`indexing` when the server restarts is marked `failed` with a reason on startup
rather than spinning in the UI forever.

---

## 📜 License

This is a personal portfolio project.
