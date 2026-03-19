# K8s Bundle Analyzer — Architecture & Design Decisions

## Overview

A full-stack application for analyzing Kubernetes Troubleshoot support bundles. It combines **heuristic pattern detection** (15 deterministic detectors) with **AI-powered analysis** (via OpenRouter — model-agnostic, defaults to Claude) to identify root causes, correlate issues, and generate actionable remediation playbooks.

**Stack:** FastAPI (Python) backend + React/TypeScript frontend with Three.js, Recharts, and Tailwind CSS.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Frontend (React/Vite)                    │
│  Dashboard → AnalysisView → [Charts, 3D Map, Chat, Logs]   │
│  Components: ErrorBoundary, DOMPurify, Recharts, Three.js   │
├─────────────────────────────────────────────────────────────┤
│                    Vite Dev Proxy (/api →)                   │
├─────────────────────────────────────────────────────────────┤
│                  Backend (FastAPI/Uvicorn)                   │
│  Routers: /api/bundles/* (upload, analyze, chat, compare)   │
│  ┌──────────────────────────────────────────────────┐       │
│  │              Analysis Pipeline                    │       │
│  │  1. BundleParser (tar.gz → structured data)       │       │
│  │  2. HeuristicAnalyzer (15 pattern detectors)      │       │
│  │  3. AIAnalyzer (OpenRouter API, with guardrails)   │       │
│  │  4. LogCorrelator (event grouping + sparklines)   │       │
│  │  5. TopologyBuilder (cluster map graph)           │       │
│  └──────────────────────────────────────────────────┘       │
│  ┌──────────────────────────────────────────────────┐       │
│  │           AI Safety Layer (guardrails.py)          │       │
│  │  - Prompt injection detection                     │       │
│  │  - Output validation (severity, category, HTML)   │       │
│  │  - Input sanitization (strips injections from data)│      │
│  │  - Profanity filtering                            │       │
│  └──────────────────────────────────────────────────┘       │
│  Persistence: JSON files on disk (bundle_info, analyses)    │
├─────────────────────────────────────────────────────────────┤
│                 Docker (non-root, healthchecks)              │
└─────────────────────────────────────────────────────────────┘
```

---

## Key Design Decisions

### 1. Heuristics-First, AI-Second

**Decision:** Run 15 deterministic heuristic detectors before the AI analyzer. The AI only adds issues the heuristics missed.

**Why:**
- Heuristics are fast, free, and deterministic — they produce the same result every time.
- AI is slow (~5-15s), costs money, and may hallucinate. By running heuristics first, we guarantee a useful baseline even if the AI is unavailable.
- The AI receives heuristic findings as context, so it focuses on deeper patterns (root cause chains, cross-component correlations) instead of re-detecting obvious issues.
- **Testability:** Heuristic detectors have clear input→output contracts — each one can be tested with a focused unit test (see `test_heuristic_analyzer.py`).

### 2. Graceful AI Degradation

**Decision:** The app works fully without an API key. Chat, analysis, and all features fall back to heuristic/keyword-based responses. When an API key is present, all AI calls go through OpenRouter, making the system model-agnostic (configurable via `OPENROUTER_MODEL` env var, defaults to `anthropic/claude-sonnet-4`).

**Why:**
- Developers evaluating the tool shouldn't need an API key just to try it.
- Production outages of the AI service shouldn't break the analysis pipeline.
- Fallback responses are still useful — they extract pod statuses, events, and logs directly from the bundle data.

### 3. Shared Guardrails Module (`guardrails.py`)

**Decision:** Extract prompt injection patterns, profanity filters, and output validators into a shared module used by both `ai_analyzer.py` and `chat.py`.

**Why:**
- **DRY:** Both the analyzer and chat need the same safety checks. Duplicating patterns means they'd drift apart over time.
- **Testability:** One test file (`test_guardrails.py`) covers all safety primitives. We can parametrize attack vectors and verify all are caught.
- **Defense in depth:** Input is sanitized before sending to the AI, the system prompt constrains behavior, and output is validated after parsing. Three independent layers.

### 4. AI Output Validation

**Decision:** Every field returned by the AI is validated — severity must be in `{critical, warning, info}`, category must be in the allowed set, HTML tags are stripped, and fields are truncated to 2000 chars.

**Why:**
- AI models can return unexpected values. A severity of "ULTRA_CRITICAL" or a category of "hacking-tools" would break the UI or mislead users.
- HTML in AI output is an XSS vector. Even though the frontend also sanitizes with DOMPurify, defense in depth means we strip at the source.
- Truncation prevents a single verbose AI response from consuming unbounded memory or breaking layouts.
- **This is testable:** `test_ai_analyzer.py::TestOutputValidation` verifies each of these constraints with specific payloads.

### 5. XSS Protection with DOMPurify

**Decision:** Chat renders AI markdown using `dangerouslySetInnerHTML`, but wraps all output through `DOMPurify.sanitize()` with an explicit allowlist of tags (`pre`, `code`, `strong`, `li`, `ul`, `br`) and attributes (`class`).

**Why:**
- The chat renders formatted markdown (code blocks, bold, lists) — plain text would be a poor UX.
- `dangerouslySetInnerHTML` without sanitization is a critical XSS vulnerability. If the AI is tricked (or the response is tampered with), malicious HTML could execute.
- DOMPurify is the industry-standard sanitizer used by Wikipedia, Google, and others.
- Allowlisting is safer than denylisting — we define what's safe rather than trying to enumerate what's dangerous.
- **Frontend tests** verify that `<script>`, `<iframe>`, `<img onerror>`, and `<object>` tags are all stripped.

### 6. React Error Boundaries

**Decision:** Wrap crash-prone components (3D ClusterMap, LogCorrelationView, BundleChat) in `ErrorBoundary` components with contextual fallback UIs. Add an app-level boundary around `<Routes>`.

**Why:**
- Three.js/WebGL can crash on unsupported hardware. Without a boundary, the entire page white-screens.
- Each boundary has a specific fallback message (e.g., "3D visualization unavailable — WebGL may not be supported") rather than a generic error.
- The app-level boundary catches anything that escapes component-level boundaries, with a "Return to Dashboard" link.

### 7. JSON File Persistence (Not a Database)

**Decision:** Bundle metadata and analysis results are stored as JSON files on disk (`data/bundles/{id}/bundle_info.json`, `latest_analysis.json`, `analyses/{timestamp}.json`).

**Why:**
- The app is a developer tool, not a multi-tenant SaaS. A database would add deployment complexity (migrations, connection pooling, ORM) without proportional benefit.
- JSON files are human-readable, easy to debug, and trivially backed up.
- History is implemented by timestamped analysis files — a simple directory listing gives you the full history.
- In-memory caches (`_bundles`, `_analyses`) provide fast access; files provide durability across restarts.

### 8. Docker Production Hardening

**Decision:** Run containers as non-root users, add healthchecks, set resource limits, and use `restart: unless-stopped`.

**Why:**
- Non-root containers follow the principle of least privilege. If a container is compromised, the attacker has limited system access.
- Healthchecks enable orchestrators (Docker Compose, Kubernetes) to detect and restart unhealthy containers automatically.
- Resource limits prevent a single container from consuming all host resources.
- `depends_on: condition: service_healthy` ensures the frontend only starts after the backend is ready.

---

## Testing Strategy

### Philosophy

> **Test the contracts, not the implementation.** Each test verifies an observable behavior from the user's or system's perspective, not internal method calls.

### Test Pyramid

```
         ┌──────────┐
         │  E2E /   │  (Future: Playwright browser tests)
         │  Manual  │
        ┌┴──────────┴┐
        │ Integration │  API endpoint tests (TestClient)
       ┌┴────────────┴┐
       │  Unit Tests   │  Heuristics, Guardrails, AI output
      ┌┴──────────────┴┐
      │  Component Tests│  ErrorBoundary, DOMPurify, HealthScore
      └────────────────┘
```

### Backend Tests (`pytest`)

| Test File | What It Tests | Why It Matters |
|-----------|--------------|----------------|
| `test_heuristic_analyzer.py` | All 15 detectors with real K8s data shapes | Ensures deterministic detection is correct. Tests both positive detection AND absence of false positives. |
| `test_guardrails.py` | Injection patterns, profanity, output validation | **AI safety.** Parametrized tests cover 10+ injection vectors and verify zero false positives on legitimate K8s queries. |
| `test_ai_analyzer.py` | System prompt safety, input sanitization, output validation, fallback | Verifies the AI can't be jailbroken via bundle data, that output is constrained, and that fallback works without API key. |
| `test_chat_guardrails.py` | Chat injection blocking, profanity filtering, fallback answers | End-to-end guardrail tests through the `BundleChat.ask()` interface. |
| `test_api_endpoints.py` | Upload → Analyze → Get → Delete workflow | Integration test with a real tar.gz bundle created in-memory. Verifies the full pipeline. |

### Frontend Tests (`vitest`)

| Test File | What It Tests | Why It Matters |
|-----------|--------------|----------------|
| `ErrorBoundary.test.tsx` | Catch, fallback rendering, recovery | Prevents white-screen crashes from reaching users. |
| `BundleChat.test.tsx` | DOMPurify sanitization of AI output | **XSS prevention.** Tests `<script>`, `<iframe>`, `<img onerror>` are stripped while allowed tags survive. |
| `HealthScore.test.tsx` | Score thresholds, label text, trend sparkline | Ensures the primary health indicator renders correctly at all severity levels. |
| `SeverityBadge.test.tsx` | All severity variants | Visual regression safety for the most-used UI component. |

### How to Run

```bash
# Backend
cd backend && source venv/bin/activate
pip install -r requirements.txt
pytest -v

# Frontend
cd frontend
npm install
npm test
```

### Testing AI Code — Our Approach

The hardest part of testing AI-integrated systems is that **AI responses are non-deterministic**. Our strategy:

1. **Don't test the AI's answer — test the guardrails around it.** We verify that injection attempts are blocked, that output is validated, and that the system prompt has safety constraints. We don't assert the AI's exact wording.

2. **Test the fallback path thoroughly.** When the AI is unavailable, the system falls back to heuristic analysis. This path is fully deterministic and exhaustively tested.

3. **Mock the API for contract tests.** `test_ai_analyzer.py::TestAPICallConfiguration` uses `unittest.mock` to verify the API is called with `timeout=60.0` without actually calling Claude.

4. **Parametrize attack vectors.** `test_guardrails.py` uses `@pytest.mark.parametrize` with 10+ prompt injection strings. Adding a new vector is one line of code.

5. **Test at multiple layers.** Input sanitization, system prompt constraints, and output validation are tested independently. A failure in one layer is caught by the next.

---

## Feature Inventory

### Analysis Pipeline
- 15 heuristic detectors (CrashLoopBackOff, OOMKilled, ImagePull, Pending, HighRestarts, FailedEvents, NodeNotReady, PVC, Certificates, ResourceQuota, DNS, Connections, Eviction, NodePressure, DeprecatedAPIs)
- AI-powered root cause analysis with Claude
- Log correlation engine (groups related events, generates sparkline data)
- Cluster topology builder (nodes, namespaces, deployments, services, pods + edges)
- Health score calculation

### AI Features
- AI analysis (deeper patterns, cross-component correlations)
- Bundle chat (conversational Q&A scoped to bundle data)
- Preflight check generation (YAML spec from detected issues)
- Playbook generation (markdown remediation steps)

### Safety
- Prompt injection detection (shared patterns in `guardrails.py`)
- Profanity filtering
- Input sanitization (strips injection lines from bundle data before sending to AI)
- Output validation (severity, category, HTML stripping, truncation)
- XSS protection (DOMPurify with tag allowlist)
- System prompt persona lock (AI cannot change role/identity)
- Chat-specific guardrails (off-topic refusal, explicit language refusal)

### Frontend
- Dashboard with upload, analysis management, and history
- Analysis overview with 4 stat cards, 4 charts, AI insights, signal timeline
- Health score trend chart (across analysis runs)
- Interactive 3D cluster topology map (Three.js) with search, labels, fullscreen
- Log correlation view with enhanced sparklines
- Cluster health grid with interactive dots and hover tooltips
- Issue detail cards with AI explanations, proposed fixes, confidence bars
- Bundle comparison view
- Playbook export (markdown/download)
- Preflight spec viewer (YAML with syntax highlighting)
- React error boundaries (component-level + app-level)

### Infrastructure
- Docker with non-root users, healthchecks, resource limits
- JSON file persistence with history tracking
- Graceful AI degradation (works without API key)

---

## File Structure

```
backend/
  app/
    main.py              # FastAPI app, CORS, health endpoint
    models.py            # Pydantic models (Issue, AnalysisResult, etc.)
    bundle_parser.py     # Tar.gz extraction + K8s resource parsing
    routers/
      bundles.py         # All API endpoints
    analyzers/
      heuristic.py       # 15 deterministic pattern detectors
      ai_analyzer.py     # Claude-powered analysis with guardrails
      chat.py            # Conversational Q&A with guardrails
      log_correlator.py  # Event grouping + sparkline generation
      guardrails.py      # Shared AI safety primitives
      preflight_generator.py  # YAML preflight spec generation
  tests/
    conftest.py          # Shared K8s fixtures (pods, nodes, events)
    test_heuristic_analyzer.py
    test_guardrails.py
    test_ai_analyzer.py
    test_chat_guardrails.py
    test_api_endpoints.py

frontend/
  src/
    api/client.ts        # Axios API client
    types/index.ts       # TypeScript interfaces
    pages/
      Dashboard.tsx      # Upload + bundle list
      AnalysisView.tsx   # Main analysis dashboard (charts, timeline, tabs)
      HistoryView.tsx    # Analysis history + comparison selector
      CompareView.tsx    # Side-by-side comparison
    components/
      ClusterMap.tsx     # Three.js 3D topology (search, fullscreen, labels)
      ClusterHealthGrid.tsx  # Interactive resource health dots
      HealthScore.tsx    # Circular progress + trend sparkline
      LogCorrelationView.tsx # Event groups with sparklines
      BundleChat.tsx     # AI chat with DOMPurify XSS protection
      ErrorBoundary.tsx  # React error boundary
      IssueCard.tsx      # Expandable issue details
      AIInsightsCard.tsx # AI bullet-point insights
      PlaybookExport.tsx # Markdown playbook modal
      PreflightViewer.tsx # YAML viewer modal
      Navbar.tsx, SeverityBadge.tsx, LoadingSpinner.tsx
    test/
      setup.ts
    components/__tests__/
      ErrorBoundary.test.tsx
      BundleChat.test.tsx
      HealthScore.test.tsx
      SeverityBadge.test.tsx
```
