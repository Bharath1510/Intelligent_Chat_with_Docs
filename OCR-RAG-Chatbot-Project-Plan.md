# Project Plan: Enterprise OCR + RAG Chatbot Platform

## 1. Executive Summary

A responsive, enterprise-grade web application that lets users upload documents (images/PDFs/scans), extracts text via OCR, indexes the content for retrieval, and exposes a conversational chatbot (RAG) that answers questions grounded in the uploaded documents. Optimized primarily for laptop/desktop use, fully responsive down to tablets and mobiles.

**Core stack:** Python, FastAPI, LangChain, PaddleOCR, Gemini APIs, a modern JS frontend framework (React recommended), Postgres + a vector store.

---

## 2. Goals & Objectives

- Accurately extract text/tables from scanned documents and images (multi-language support via PaddleOCR).
- Ground chatbot answers in the extracted content using Retrieval-Augmented Generation (RAG), minimizing hallucination.
- Deliver a fast, trendy, and creative UI/UX — desktop/laptop-first, fully responsive.
- Meet enterprise-grade requirements: authentication, authorization, auditability, scalability, data isolation (multi-tenancy if needed), and observability.
- Keep the architecture modular so OCR engine, LLM provider (Gemini), and vector store can be swapped later with minimal rework.

---

## 3. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Frontend (React)                        │
│  Responsive UI • Upload/Chat/Dashboard • WebSocket/SSE streaming│
└───────────────────────────┬───────────────────────────────────┘
                              │ REST / WebSocket (HTTPS)
┌───────────────────────────▼───────────────────────────────────┐
│                        FastAPI Gateway                          │
│  Auth (JWT/OAuth2) • Rate limiting • Request validation         │
├───────────────────────────────────────────────────────────────┤
│  Ingestion Service        │  Chat/RAG Service                    │
│  - File upload handler     │  - LangChain orchestration           │
│  - PaddleOCR extraction    │  - Retriever (vector search)         │
│  - Text cleaning/chunking  │  - Gemini API (generation)           │
│  - Embedding generation    │  - Conversation memory               │
├───────────────────────────────────────────────────────────────┤
│  Background Workers (Celery / RQ + Redis)                        │
│  - Async OCR jobs • Embedding jobs • Doc re-indexing              │
├───────────────────────────────────────────────────────────────┤
│  Storage Layer                                                   │
│  - Postgres (metadata, users, chat history, audit logs)          │
│  - Vector DB (pgvector / Qdrant / Weaviate) for embeddings        │
│  - Object storage (S3 / Azure Blob / MinIO) for raw files         │
└───────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────▼─────────┐
                    │   Gemini API(s)    │
                    │  (embeddings + LLM)│
                    └───────────────────┘
```

---

## 4. Tech Stack

| Layer | Technology | Notes |
|---|---|---|
| Backend framework | **FastAPI** | Async, OpenAPI docs auto-generated |
| OCR engine | **PaddleOCR** | Run as a microservice or in-process; GPU optional for speed |
| LLM orchestration | **LangChain** | Chains, retrievers, memory, agent tooling |
| LLM/embeddings | **Gemini API** (`gemini-2.x` + `text-embedding-004` or latest embedding model) | Verify current model names before build — see note below |
| Vector store | **pgvector** (simplest, same Postgres) or **Qdrant** (if scale demands) | Start with pgvector for lower ops overhead |
| Relational DB | **PostgreSQL** | Users, documents, chat sessions, audit trail |
| Task queue | **Celery + Redis** (or RQ) | Async OCR/embedding jobs so uploads don't block requests |
| Frontend | **React + TypeScript + Vite** | Tailwind CSS + shadcn/ui or Radix for a trendy, consistent design system |
| Realtime | **WebSockets / Server-Sent Events** | Streaming chatbot responses token-by-token |
| Auth | **OAuth2 / JWT** (FastAPI-Users or custom) | SSO (SAML/OIDC) if enterprise clients require it |
| Containerization | **Docker + docker-compose**, Kubernetes-ready | For consistent dev/prod parity |
| Observability | **OpenTelemetry, Prometheus, Grafana, structured logging** | Enterprise-grade monitoring |
| CI/CD | **GitHub Actions** | Lint, test, build, deploy pipeline |

> Note: Gemini model names and available endpoints change over time. Before locking the stack, verify the current Gemini model/embedding names in Google's official docs at build time, since specifics may have shifted since this plan was written.

---

## 5. Core Modules

### 5.1 Document Ingestion & OCR Pipeline
- Accept PDF, JPG, PNG, TIFF, multi-page scans.
- Pre-processing: deskew, denoise, contrast normalization (OpenCV) before PaddleOCR for accuracy.
- PaddleOCR extracts text + bounding boxes + (optionally) table structure (PP-Structure module).
- Store raw file in object storage; store extracted text + layout metadata in Postgres.
- Emit an async job so large files don't block the UI (progress bar via polling or WebSocket).

### 5.2 Chunking & Embedding
- Split cleaned OCR text using LangChain text splitters (semantic or recursive character splitting, tuned per document type).
- Generate embeddings via Gemini embeddings API.
- Store vectors + metadata (doc id, page, chunk id) in the vector store.

### 5.3 RAG / Chat Engine
- LangChain retriever pulls top-k relevant chunks per query (hybrid search: vector + keyword/BM25 for precision).
- Prompt template grounds Gemini's generation in retrieved context, with citation of source document/page.
- Conversation memory (per-session) for multi-turn coherence.
- Guardrails: if retrieval confidence is low, respond with "not found in documents" rather than hallucinating.

### 5.4 Chatbot API & Streaming
- FastAPI endpoint streams tokens via SSE/WebSocket for a responsive, "typing" chat experience.
- Endpoint returns citations (document name, page number) alongside the answer.

### 5.5 Frontend (Responsive, Trendy UI)
- **Layout:** Split view on desktop/laptop — document/chat history sidebar + main chat pane + document preview pane. Collapses to a single-column, tab-based layout on tablets/mobiles.
- **Design language:** Clean, modern SaaS aesthetic — soft shadows, rounded corners, subtle gradients/glassmorphism accents, dark/light mode toggle, micro-interactions (typing indicators, upload progress animations, smooth transitions).
- **Key screens:**
  1. Login/SSO screen
  2. Dashboard (recent documents, usage stats)
  3. Upload & OCR review screen (side-by-side original scan vs extracted text, editable)
  4. Chat screen (RAG-grounded conversation, source citations, follow-up suggestions)
  5. Document library (search, tags, status)
  6. Admin/settings (user management, API usage, audit logs) — enterprise tier
- **Responsiveness:** Desktop-first breakpoints (≥1280px primary target), graceful degradation to tablet (768–1279px) and mobile (<768px) using CSS Grid/Flexbox + Tailwind responsive utilities.

### 5.6 Enterprise Security & Compliance
- JWT-based auth with refresh tokens; optional SSO (OIDC/SAML) for enterprise clients.
- Role-based access control (Admin, Editor, Viewer).
- Per-tenant data isolation if multi-tenant.
- Encryption at rest (DB/object storage) and in transit (TLS).
- Audit logging: every upload, query, and admin action logged with user/timestamp.
- Rate limiting & input validation (prevent prompt injection via uploaded documents — sanitize/flag suspicious content before it reaches the LLM context).

### 5.7 Observability & Ops
- Structured JSON logging with request/correlation IDs.
- Metrics: OCR latency, RAG retrieval latency, Gemini API latency/error rate, token usage/cost tracking.
- Centralized dashboard (Grafana) + alerting.

---

## 6. Non-Functional Requirements (Enterprise Grade)

- **Scalability:** Stateless FastAPI instances behind a load balancer; horizontal scaling of OCR/embedding workers.
- **Availability:** Target 99.9% uptime; health checks + readiness probes for k8s.
- **Data privacy:** Configurable data retention policy; ability to delete a tenant's data fully (right-to-be-forgotten).
- **Cost control:** Cache repeated queries/embeddings; batch embedding calls; monitor Gemini API token spend.
- **Extensibility:** OCR engine, vector store, and LLM provider abstracted behind interfaces so they can be swapped later.

---

## 7. Development Phases & Timeline (Indicative — adjust to team size)

| Phase | Duration | Deliverables |
|---|---|---|
| **Phase 0 – Discovery & Design** | 1–2 wks | Finalized requirements, UI wireframes/mockups, architecture sign-off |
| **Phase 1 – Foundation** | 2 wks | FastAPI skeleton, auth, DB schema, Docker setup, CI/CD pipeline |
| **Phase 2 – OCR Pipeline** | 2–3 wks | PaddleOCR integration, async job queue, upload UI, extraction review screen |
| **Phase 3 – RAG Engine** | 2–3 wks | Chunking, embeddings, vector store, LangChain retriever, Gemini integration |
| **Phase 4 – Chat UI & Streaming** | 2 wks | Chat screen, SSE/WebSocket streaming, citations, conversation memory |
| **Phase 5 – Enterprise Hardening** | 2 wks | RBAC, audit logs, rate limiting, observability, security review |
| **Phase 6 – Polish & Responsive QA** | 1–2 wks | Cross-device testing, performance tuning, UI polish/animations |
| **Phase 7 – UAT & Launch** | 1 wk | User acceptance testing, deployment, documentation |

**Total: ~12–16 weeks** for a small team (2–4 engineers + 1 designer), adjustable based on scope.

---

## 8. Suggested Team Roles

- 1 Backend engineer (FastAPI, LangChain, RAG pipeline)
- 1 ML/OCR engineer (PaddleOCR tuning, embeddings, prompt engineering)
- 1 Frontend engineer (React, responsive design, streaming UI)
- 1 UI/UX designer (design system, trendy visual direction)
- 1 DevOps/QA (CI/CD, observability, cross-device testing) — can be shared/part-time

---

## 9. Key Risks & Mitigations

| Risk | Mitigation |
|---|---|
| OCR accuracy on poor-quality scans | Pre-processing pipeline (deskew/denoise); allow manual text correction in review UI |
| Gemini API rate limits/cost overrun | Caching, batching, token usage dashboards, fallback queuing |
| Hallucinated chatbot answers | Strict grounding prompts, low-confidence fallback response, citations shown to user |
| Prompt injection via malicious documents | Sanitize extracted text, isolate document content from system instructions |
| Scaling OCR under heavy load | Async workers, horizontal scaling, GPU-backed OCR nodes if needed |

---

## 10. Appendix: Build Prompt

Use the prompt below with an AI coding assistant (Claude Code, etc.) to scaffold the project. Adjust the bracketed placeholders as needed.

> ```
> Build an enterprise-grade, responsive web application for OCR + RAG-based document chat.
>
> STACK:
> - Backend: Python + FastAPI (async), LangChain for RAG orchestration, PaddleOCR for text extraction
>   from uploaded images/PDFs, Google Gemini API for embeddings + chat generation.
> - Vector store: pgvector (Postgres extension) for simplicity; abstract behind a repository interface
>   so it can be swapped for Qdrant later.
> - Task queue: Celery + Redis for async OCR and embedding jobs.
> - Frontend: React + TypeScript + Vite, Tailwind CSS, shadcn/ui components. Desktop/laptop-first
>   responsive design (primary breakpoint ≥1280px), gracefully degrading to tablet and mobile.
> - Auth: JWT-based with refresh tokens, role-based access control (Admin/Editor/Viewer).
>
> REQUIREMENTS:
> 1. Document upload flow: accept PDF/JPG/PNG, run PaddleOCR asynchronously, show upload progress,
>    and display a side-by-side "original scan vs extracted text" review screen where users can
>    correct OCR errors before indexing.
> 2. RAG chat: chunk extracted text, generate embeddings via Gemini, store in pgvector, build a
>    LangChain retriever with hybrid (vector + keyword) search. Chat responses must be grounded in
>    retrieved chunks, streamed token-by-token via SSE or WebSocket, and must include source
>    citations (document name + page number). If retrieval confidence is low, respond that the
>    answer isn't found in the documents rather than guessing.
> 3. UI/UX: modern SaaS aesthetic — soft shadows, rounded corners, subtle gradient accents,
>    dark/light mode toggle, smooth micro-interactions (typing indicators, upload progress
>    animations). Desktop layout: sidebar (document list) + main chat pane + document preview pane.
>    Mobile layout: collapse into tabbed single-column view.
> 4. Enterprise features: audit logging of uploads/queries/admin actions, rate limiting, input
>    sanitization on OCR'd text before it reaches the LLM context (defend against prompt injection
>    from malicious documents), structured JSON logging with correlation IDs.
> 5. Provide Docker + docker-compose setup for local dev (FastAPI, Postgres+pgvector, Redis, frontend).
> 6. Include a health check endpoint and basic OpenTelemetry/Prometheus metrics hooks.
>
> DELIVERABLES:
> - FastAPI backend with clear module separation: /ingestion, /rag, /auth, /chat, /admin.
> - React frontend with the screens: Login, Dashboard, Upload & OCR Review, Chat, Document Library, Admin.
> - README with setup instructions and environment variable list (including where to plug in the
>   Gemini API key).
> - Basic test coverage (pytest for backend, Vitest/RTL for frontend) for the core OCR-to-chat flow.
>
> Start by scaffolding the backend project structure and Docker setup, then the OCR ingestion
> endpoint, then the RAG chat endpoint, then the frontend shell, iterating screen by screen.
> ```

---

## 11. Functional Screens in Sequence

This walks through the application screen-by-screen in the order a user actually moves through them, with purpose, key UI elements, and functional behavior for each. Desktop/laptop layout described first; mobile adaptation noted where it differs meaningfully.

```
Login/SSO → Dashboard → Upload → OCR Processing (async) → OCR Review & Correction
   → Document Library ⇄ Chat (RAG) → Admin/Settings & Audit Log (role-gated)
```

### Screen 1 — Login / SSO
- **Purpose:** Authenticate the user before any access.
- **Elements:** Email/password fields, "Sign in with SSO" button (OIDC/SAML for enterprise tenants), "Forgot password" link, light/dark toggle.
- **Functionality:** Calls `/auth/login`, sets JWT + refresh token (httpOnly cookie or secure storage). On success → redirects to Dashboard. Failed login shows inline error, no page reload.
- **Mobile:** Single centered card, full-width inputs.

### Screen 2 — Dashboard (Home)
- **Purpose:** Landing point after login; quick orientation and shortcuts.
- **Elements:** Summary cards (documents processed, active chats, storage used, API usage this month), "Upload New Document" primary CTA, recent documents list (thumbnail, name, status badge: Processing/Ready/Failed), recent chat sessions list.
- **Functionality:** Pulls from `/dashboard/summary` and `/documents?recent=true`. Clicking a document opens it in the Document Library/Preview; clicking a chat session resumes it in the Chat screen.
- **Mobile:** Cards stack vertically; lists become scrollable tabs ("Documents" / "Chats").

### Screen 3 — Upload
- **Purpose:** Get files into the system.
- **Elements:** Drag-and-drop zone + file picker, accepted formats note (PDF/JPG/PNG/TIFF), multi-file queue with per-file progress bars, tag/category input (optional metadata), "Start Processing" button.
- **Functionality:** Files upload to object storage via `/documents/upload`; on completion, triggers an async OCR job per file (Celery task) and returns a `job_id` for status polling.
- **Mobile:** Camera capture option added alongside file picker (useful for scanning physical documents on the go).

### Screen 4 — OCR Processing (transient/async state)
- **Purpose:** Give visible feedback while PaddleOCR runs in the background.
- **Elements:** Per-file progress indicator (Queued → Extracting Text → Structuring → Done/Failed), estimated time, cancel option.
- **Functionality:** Frontend polls `/jobs/{job_id}/status` or subscribes via WebSocket; on completion auto-navigates (or shows a "Review Now" button) to the OCR Review screen. On failure, shows reason (e.g., unsupported format, corrupted file) with a retry option.
- **Mobile:** Same behavior, condensed to a single progress card per file.

### Screen 5 — OCR Review & Correction
- **Purpose:** Let the user verify/correct extracted text before it's indexed for chat — critical for accuracy since OCR is never 100%.
- **Elements:** Split pane — original scanned image/PDF on the left (zoomable, with detected bounding boxes highlighted), editable extracted text on the right (paragraph/table structure preserved where possible). "Confirm & Index" button, "Discard" button, confidence-score highlighting on low-confidence words.
- **Functionality:** Saves edits via `/documents/{id}/text`; "Confirm & Index" triggers chunking + embedding job, then marks the document `Ready` for chat.
- **Mobile:** Tabs replace the split pane ("Original" / "Text") since side-by-side doesn't fit; edits still supported.

### Screen 6 — Document Library
- **Purpose:** Central place to browse, search, and manage all uploaded documents.
- **Elements:** Search bar (full-text + tag filter), grid/list toggle, status badges, bulk actions (delete, re-index, tag), per-document menu (Preview, Chat about this doc, Download, Delete).
- **Functionality:** `/documents` with pagination/search params. "Chat about this doc" deep-links into the Chat screen scoped to that document (or document set).
- **Mobile:** List view only (grid dropped), swipe actions replace hover menus.

### Screen 7 — Chat (RAG)
- **Purpose:** The core interaction — ask questions, get grounded answers.
- **Elements:** Left sidebar (chat session history + document scope selector — "All documents" or specific ones), main conversation pane with streaming responses, each answer showing source citations (document name + page, clickable to jump to that page in a preview panel), input box with suggested follow-up questions, "New Chat" button.
- **Functionality:** Sends query to `/chat` (WebSocket/SSE for streaming); backend runs retrieval → Gemini generation → streams tokens; citations rendered as chips/links under each answer; low-confidence retrieval returns an explicit "not found in your documents" response instead of guessing.
- **Mobile:** Sidebar collapses into a hamburger/drawer; citation preview opens as a bottom sheet instead of a side panel.

### Screen 8 — Document Preview (side panel / modal)
- **Purpose:** Let the user jump straight to the source page cited in a chat answer, without losing chat context.
- **Elements:** Rendered page image/PDF viewer, highlighted region matching the cited chunk, close/back-to-chat control.
- **Functionality:** Opens in-place (side panel on desktop, modal/bottom sheet on mobile) so the chat conversation stays visible/resumable.

### Screen 9 — Admin / Settings (role-gated: Admin only)
- **Purpose:** Manage users, roles, and tenant-level configuration.
- **Elements:** User list with role assignment (Admin/Editor/Viewer), invite-user form, API usage/cost dashboard (Gemini token consumption), data retention policy controls, tenant branding (logo/colors) if white-labeled.
- **Functionality:** CRUD via `/admin/users`, `/admin/settings`; changes take effect immediately, logged to the audit trail.
- **Mobile:** Read-mostly view; heavier admin actions (bulk role changes) nudge the user toward desktop.

### Screen 10 — Audit Log (role-gated: Admin)
- **Purpose:** Enterprise compliance — full traceability of who did what.
- **Elements:** Filterable table (user, action type, resource, timestamp, IP), export-to-CSV button.
- **Functionality:** Reads from the audit log table populated by every upload/query/admin action across the app.

### Screen 11 — Profile / Account Settings (all roles)
- **Purpose:** Personal account management.
- **Elements:** Name/email, password change, theme preference (dark/light), notification preferences, connected SSO identity (if applicable), logout.

---

## 12. Next Steps

1. Review the screen sequence above against real user workflows and adjust ordering/permissions as needed.
2. Confirm scope: single-tenant vs multi-tenant, expected user volume, and document types/languages for OCR.
2. Validate current Gemini model/embedding API names and pricing before finalizing the stack (these change over time).
3. Get UI direction sign-off (wireframes/mockups) before frontend development begins.
4. Set up repo, CI/CD, and Docker environment as the first sprint deliverable.
