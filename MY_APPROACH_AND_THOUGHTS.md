# My Approach and Thoughts

I built a support bundle analyzer that treats heuristic detection and AI correlation as complementary passes, not competing approaches. The key insight: the hard part of bundle analysis isn't finding problems -- it's connecting them into a causal story an ISV engineer can act on.

## Two-Pass Analysis

The heuristic layer runs first: 15 detectors for CrashLoopBackOff, OOMKilled, image pull failures, node pressure, DNS issues, and other well-characterized failure modes. Many ISV customers run air-gapped clusters where external API calls are a non-starter. Deterministic detectors catch ~80% of common issues instantly, with zero external dependencies. The AI pass then receives these findings alongside summarized cluster state and does what rules cannot: correlate a frontend timeout with a backend ImagePullBackOff with a node memory pressure condition, producing a single causal chain instead of three separate alerts.

## The ISV Workflow Gap

ISV support engineers don't fix clusters -- they tell customers what to fix. This changes everything about what the tool outputs. A list of detected issues is necessary but insufficient. The analyzer generates shareable remediation playbooks with specific commands tied to evidence, and automatically produces Troubleshoot preflight checks from detected failures. Diagnosis leads to remediation leads to prevention.

## Chat as Investigation Tool

Static reports answer predetermined questions. Real support investigations are exploratory -- "why can't the frontend reach the API server?" Bundle chat lets the engineer interrogate the data conversationally, getting evidence-backed answers grounded in actual log lines. This is where AI adds genuine value over grep: synthesizing across dozens of files to answer a specific question with cited evidence.

## AI Safety

The guardrails are architectural, not afterthought. Input sanitization strips injection attempts from bundle data before it reaches the LLM. The system prompt is persona-locked. Output validation enforces allowed severity/category values, strips HTML, truncates unbounded responses. DOMPurify prevents XSS through AI output. 109 tests cover heuristic detection, guardrail patterns, output validation, and chat safety. The philosophy: test the constraints around the AI, not the AI's specific answers.

## What I'd Build Next

The scaling bottleneck is context. Large production bundles (100MB+) overwhelm any LLM context window, so a RAG pipeline with chunked log embeddings is the natural next step. Local LLM support via Ollama would make AI viable in air-gapped environments. The production architecture would use multi-step agentic analysis -- separate agents for triage, deep-dive, correlation, and remediation -- replacing the single-shot prompt with tool-calling agents that query specific logs on demand. Finally, deeper integration with Troubleshoot's ecosystem -- ingesting analyzer outcomes from `analysis.json`, contributing findings back as custom analyzer specs, and integrating with the Enterprise Portal bundle upload workflow -- would position this as a natural extension of the support toolchain.

Support bundles contain everything needed to diagnose a problem, but the signal is buried under megabytes of nominal state. The real challenge is not extraction -- it is narrative.
