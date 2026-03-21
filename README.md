# K8s Bundle Analyzer

**Turn Kubernetes support bundles into actionable diagnosis in seconds.**

Built on top of the [Troubleshoot](https://troubleshoot.sh) support bundle format by [Replicated](https://replicated.com).

K8s Bundle Analyzer is a web-based tool that ingests support bundles from `kubectl support-bundle` and produces structured root-cause analysis with remediation guidance. It combines deterministic heuristic detection with LLM-powered correlation to help ISV support engineers diagnose customer cluster issues quickly -- without needing direct access to the cluster. The output is designed to be shared: remediation playbooks and preflight checks that close the loop from diagnosis to prevention.

## Features

### Core Analysis

- **15 Heuristic Detectors** -- Fast, deterministic pattern matching for common Kubernetes failure modes. No API key required.
  - CrashLoopBackOff, OOMKilled, ImagePullBackOff
  - Pending pods, high restart counts, evicted pods
  - Node NotReady, node pressure (memory/disk/PID)
  - PVC binding failures, resource quota exceeded
  - Certificate expiration, DNS failures, connection errors
  - Deprecated API usage, failed events
- **AI Root-Cause Analysis** -- Feeds heuristic findings and cluster state to Claude, which correlates symptoms across components and identifies causal chains. Separates root causes from downstream effects.
- **RAG Pipeline** -- OpenAI embeddings with ChromaDB vector store. Bundle content is chunked and indexed for semantic retrieval, powering evidence-grounded chat responses with cited sources.
- **Health Score with Trend** -- Aggregated cluster health score with severity-weighted issue prioritization. Tracks score across analysis runs to show improvement or degradation over time.

### Interactive Tools

- **Chat with Bundle** -- Conversational Q&A against bundle data. Ask "why can't service X reach service Y?" and get evidence-backed answers grounded in actual logs and events. Includes prompt injection protection and DOMPurify XSS prevention on rendered responses.
- **3D Cluster Topology Map** -- Three.js visualization of pod/service/node relationships with health status overlay. Supports search, fullscreen mode, and label toggling.
- **Log Correlation** -- Cross-source log analysis that links events across pods, nodes, and system components. Sparkline visualizations show event density over time.
- **Cluster Health Grid** -- Interactive dot-grid view of resource health states. Click into any resource for details.
- **Cross-Bundle Search** -- Semantic search across all indexed bundles using vector similarity. Find similar issues and patterns across your support bundle history.

### Actionable Output

- **Remediation Playbook Export** -- Shareable, structured remediation steps tied to specific evidence. Designed for ISV engineers to hand to customers.
- **Preflight Check Generation** -- Automatically generates `troubleshoot.sh/v1beta2` Preflight specs from detected issues. Turns reactive diagnosis into proactive prevention.
- **History and Comparison** -- View past analyses and diff results across bundles to track cluster health over time.

### UI Resilience

- **React Error Boundaries** -- Component-level fault isolation prevents a single rendering error from taking down the entire dashboard.
- **Interactive Charts** -- Animated Recharts visualizations for health scores, severity distributions, and log timelines.
- **Graceful Degradation** -- Full heuristic analysis, cluster map, and log correlation work without an API key. AI features activate when the key is present.

## Safety and Guardrails

Security and input validation are enforced at every layer through a shared `guardrails` module.

| Layer | Protection |
|-------|-----------|
| **Input sanitization** | Strips prompt injection attempts from bundle data before it reaches the AI. Pattern-matched line removal with logging. |
| **Prompt injection detection** | Shared regex engine catches persona hijacking, instruction override, and role-change attempts in both chat and analysis paths. |
| **AI output validation** | Severity values are clamped to `critical/warning/info`. Categories are restricted to a fixed allowlist. HTML tags are stripped. All fields are truncated to prevent payload inflation. |
| **XSS protection** | DOMPurify with an explicit tag allowlist sanitizes all AI-generated content before rendering in the browser. |
| **System prompt persona lock** | The AI system prompt enforces a Kubernetes diagnostics persona. Off-topic and explicit content is rejected before the API call. |
| **Air-gap safe** | The entire heuristic pipeline, cluster map, log correlation, and UI run with zero external calls. The `OPENROUTER_API_KEY` is optional. |

## Quick Start

### Option 1: Docker Compose

```bash
git clone <repo-url> && cd k8s-bundle-analyzer

# Optional: enable AI-powered analysis
export OPENROUTER_API_KEY=sk-or-...

docker compose up --build
```

Open http://localhost:5174

### Option 2: Local Development

Copy the environment template and fill in your keys:

```bash
cp backend/.env.example backend/.env
```

**Using Make** (recommended):

```bash
make dev        # Start backend + frontend
make test       # Run all tests
make lint       # Run all linters
```

**Manual setup:**

**Backend** (Python 3.12+):

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8001
```

**Frontend** (Node 18+):

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5174

> **Note:** API keys are optional. Without them, the tool runs heuristic analysis only -- still useful for the 80% of common failure patterns. AI features (root-cause correlation, chat, preflight generation) activate when OPENROUTER_API_KEY is present. RAG-powered search requires OPENAI_API_KEY.

## Usage

1. **Upload** -- Drag-and-drop or select a `.tar.gz` support bundle
2. **Analyze** -- Click "Analyze Bundle" to run the two-pass pipeline (heuristic, then AI)
3. **Explore** -- Navigate the results across the dashboard views:
   - **Overview** -- Health score, AI-generated summary, top issues at a glance
   - **Issues** -- Detected problems with expandable evidence (log lines, events) and remediation steps
   - **Cluster Map** -- 3D topology showing resource relationships and health status
   - **Log Correlation** -- Cross-source event linking with sparkline timelines
   - **Chat** -- Conversational investigation against the bundle data
4. **Export** -- Generate remediation playbooks, preflight checks, or full reports to share with customers
5. **Compare** -- View analysis history and diff results across bundles

## Architecture

```
                        K8s Bundle Analyzer Pipeline

  Upload (.tar.gz)
     |
     v
  +-----------+     +--------------+     +-------------------+
  |   Parse   |---->|  Guardrails  |---->|    Heuristic      |
  |  Extract  |     |  Sanitize    |     |    15 detectors   |
  +-----------+     +--------------+     +-------------------+
                         |                       |
                         v                       v
                    +--------------+     +-------------------+
                    |  Guardrails  |     |   AI (Claude)     |
                    |  Validate    |<----|   Correlate       |
                    +--------------+     +-------------------+
                         |
     +-------------------+-------------------+
     |                   |                   |
     v                   v                   v
  +----------+   +------------+   +-------------------+
  | Log      |   | Cluster    |   | Playbook + Report |
  | Correlate|   | Map (3D)   |   | + Preflight Gen   |
  +----------+   +------------+   +-------------------+
                        |
                        v
                 +--------------------+
                 | React UI           |
                 | (Error Boundaries, |
                 |  DOMPurify XSS)    |
                 +--------------------+
```

## Testing

The project has 109 tests across backend and frontend.

**Backend** -- 88 tests via pytest:

- Heuristic detector coverage (all 15 detectors)
- Guardrails: injection detection, severity/category validation, HTML stripping, truncation
- Chat safety: prompt injection rejection, explicit content filtering
- AI output validation and sanitization
- API endpoint integration tests

```bash
cd backend && source venv/bin/activate && pytest -v
```

**Frontend** -- 21 tests via vitest:

- ErrorBoundary fault isolation
- DOMPurify XSS sanitization on chat responses
- HealthScore rendering and edge cases
- SeverityBadge styling and label accuracy

```bash
cd frontend && npm test
```

## Generating Test Bundles

You can generate real support bundles from a local Kind cluster with intentionally broken workloads.

**1. Set up a Kind cluster:**

```bash
kind create cluster --name test-bundle
```

**2. Deploy broken workloads:**

```bash
# Working deployment
kubectl create deployment nginx --image=nginx

# Broken: bad image tag
kubectl create deployment broken-image --image=nginx:nonexistent

# Broken: resource exhaustion
kubectl run oom-pod --image=nginx --restart=Never \
  --overrides='{"spec":{"containers":[{"name":"oom","image":"nginx","resources":{"limits":{"memory":"4Mi"}}}]}}'
```

**3. Install the Troubleshoot plugin and generate a bundle:**

```bash
kubectl krew install support-bundle
kubectl support-bundle sample-specs/support-bundle-spec.yaml
```

The generated `.tar.gz` file can be uploaded directly to the analyzer. See `sample-specs/` for the bundle spec configuration.

## Tech Stack

| Layer    | Technology                                              |
|----------|---------------------------------------------------------|
| Frontend | React 18, TypeScript, Tailwind CSS, Recharts            |
| 3D       | Three.js (raw WebGL, OrbitControls)                     |
| Security | DOMPurify (XSS), shared guardrails module               |
| Backend  | Python 3.12, FastAPI, Pydantic, PostgreSQL, SQLAlchemy   |
| AI       | Claude via OpenRouter, OpenAI Embeddings, ChromaDB       |
| Testing  | pytest (backend), vitest (frontend)                     |
| Infra    | Docker, Docker Compose, Nginx                           |

## Project Structure

```
.
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI application entry point
│   │   ├── models.py                # Pydantic data models
│   │   ├── bundle_parser.py         # Support bundle extraction and parsing
│   │   ├── routers/
│   │   │   └── bundles.py           # API endpoints (upload, analyze, chat, export)
│   │   └── analyzers/
│   │       ├── heuristic.py         # 15 pattern-based detectors
│   │       ├── ai_analyzer.py       # Claude-powered root-cause analysis
│   │       ├── chat.py              # Conversational Q&A against bundle data
│   │       ├── log_correlator.py    # Cross-source log correlation
│   │       ├── preflight_generator.py  # Preflight check generation
│   │       └── guardrails.py        # Shared input sanitization + output validation
│   │   ├── rag/
│   │   │   ├── chunker.py            # Bundle content chunking for RAG
│   │   │   ├── retriever.py          # Vector similarity retrieval
│   │   │   └── vector_store.py       # ChromaDB integration
│   ├── tests/                       # pytest suite (88 tests)
│   ├── requirements.txt
│   ├── pyproject.toml            # Ruff linting + pytest config
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── ClusterMap.tsx        # 3D Three.js topology visualization
│   │   │   ├── BundleChat.tsx        # Chat interface with DOMPurify
│   │   │   ├── ClusterHealthGrid.tsx # Interactive health dot grid
│   │   │   ├── HealthScore.tsx       # Score display with trend tracking
│   │   │   ├── LogCorrelationView.tsx # Log linking with sparklines
│   │   │   ├── PlaybookExport.tsx    # Remediation playbook export
│   │   │   ├── PreflightViewer.tsx   # Preflight spec viewer
│   │   │   ├── ErrorBoundary.tsx     # React error boundary
│   │   │   ├── IssueCard.tsx         # Issue detail cards
│   │   │   ├── AIInsightsCard.tsx    # AI analysis summary
│   │   │   └── __tests__/           # vitest suite (21 tests)
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx         # Main dashboard
│   │   │   ├── AnalysisView.tsx      # Analysis results
│   │   │   ├── HistoryView.tsx       # Analysis history
│   │   │   └── CompareView.tsx       # Bundle comparison
│   │   ├── api/                      # API client
│   │   └── types/                    # TypeScript type definitions
│   ├── package.json
│   └── Dockerfile
├── sample-specs/                     # Troubleshoot bundle spec for test generation
├── ARCHITECTURE.md                   # Detailed architecture documentation
├── docker-compose.yml
├── Makefile                         # Developer workflow commands
└── MY_APPROACH_AND_THOUGHTS.md
```

## How It Relates to Troubleshoot.sh

This tool is designed to complement -- not replace -- the existing [Troubleshoot](https://troubleshoot.sh) ecosystem.

- **Consumes the standard bundle format.** Ingests the exact `.tar.gz` output from `kubectl support-bundle`. No custom collection specs, no proprietary formats. Any bundle generated with a standard Troubleshoot spec works out of the box.

- **Extends declarative YAML analyzers with AI correlation.** Troubleshoot's built-in analyzers are great for known-good/known-bad checks. This tool adds cross-resource correlation: linking a pod CrashLoop to an OOM condition on the node to a missing resource quota -- producing a causal narrative rather than independent pass/fail results.

- **Reactive-to-proactive feedback loop.** The preflight generator automatically produces `troubleshoot.sh/v1beta2` Preflight specs from detected issues. A problem found in a support bundle today becomes a preflight check that catches it before deployment tomorrow. The generated specs are valid YAML that can be committed directly to a Troubleshoot preflight configuration.

- **Works without an API key.** The heuristic pipeline, cluster map, log correlation, and full UI run with zero external API calls. This matters for air-gapped environments where bundles are analyzed on isolated networks.

- **Compatible with Enterprise Portal workflows.** Bundles uploaded through the Replicated Enterprise Portal can be downloaded and fed directly into the analyzer for deeper investigation.
