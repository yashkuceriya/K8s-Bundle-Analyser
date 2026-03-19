# My Approach and Thoughts

I built a support bundle analyzer that treats heuristic detection and AI correlation as complementary passes, not competing approaches. The key insight: the hard part of bundle analysis isn't finding problems -- it's connecting them into a causal story an ISV engineer can act on.

## Two-Pass Analysis

The heuristic layer runs first: 15+ detectors for CrashLoopBackOff, OOMKilled, image pull failures, node pressure, DNS issues, and other well-characterized failure modes. This matters beyond speed. Many ISV customers run air-gapped clusters where external API calls are a non-starter. Deterministic detectors catch roughly 80% of common issues instantly, with zero external dependencies. The AI pass then receives these findings alongside summarized cluster state and does what rules cannot: correlate a frontend timeout with a backend ImagePullBackOff with a node memory pressure condition, producing a single causal chain instead of three separate alerts.

## The ISV Workflow Gap

Here is the insight that shaped the tool's design: ISV support engineers don't fix clusters -- they tell customers what to fix. This changes everything about what the tool needs to output. A list of detected issues is necessary but insufficient. The analyzer generates shareable remediation playbooks with specific commands tied to specific evidence, and automatically produces preflight checks from detected failures. This closes the full loop: diagnosis leads to remediation guidance leads to prevention. The customer gets a concrete action plan, not a diagnostic dump.

## Chat as Investigation Tool

Static analysis reports answer predetermined questions. But real support investigations are exploratory -- "why can't the frontend reach the API server?" or "what changed in the last hour before the crash?" Bundle chat lets the engineer interrogate the data conversationally, getting evidence-backed answers grounded in actual log lines and events. This is where AI adds genuine value over grep: synthesizing across dozens of files to answer a specific question with cited evidence.

## Production Hardening and AI Safety

AI in production requires defense in depth. The guardrails aren't an afterthought -- they're architectural. Input sanitization strips prompt injection attempts from bundle data before it reaches the LLM. The system prompt is persona-locked. Output validation enforces allowed severity/category values, strips HTML, and truncates to prevent unbounded responses. On the frontend, DOMPurify with an explicit tag allowlist prevents XSS through AI output. These layers are independently testable: 109 tests cover heuristic detection, guardrail patterns (parametrized with 10+ injection vectors), output validation, chat safety, and API integration. The testing philosophy is: test the constraints around the AI, not the AI's specific answers. Non-deterministic outputs can't have deterministic assertions, but the safety envelope around them can.

## What I'd Build Next

The immediate scaling bottleneck is context. Large production bundles (100MB+) overwhelm any LLM context window, so a RAG pipeline with chunked log embeddings and per-issue targeted retrieval is the natural next step. Local LLM support via Ollama or vLLM would make the AI pass viable in air-gapped environments. The production architecture would use LangGraph for multi-step agentic analysis -- separate agents for triage, deep-dive, correlation, and remediation -- replacing the single-shot prompt with tool-calling agents that query specific logs and resources on demand. Cluster topology belongs in a graph database like Neo4j, where Cypher queries can trace causal chains across resource relationships and enable cross-bundle pattern matching to surface systemic vendor-specific failures. Finally, deeper integration with Troubleshoot's ecosystem -- ingesting existing analyzer outcomes from `analysis.json`, contributing findings back as custom analyzer specs, and integrating with the Enterprise Portal's bundle upload workflow -- would position this as a natural extension of the CSDL support toolchain.

## Closing

Support bundles are a strange artifact: they contain everything needed to diagnose a problem, but the signal is buried under megabytes of nominal state. The real challenge is not extraction -- it is narrative. Turning scattered symptoms into a coherent story of what went wrong, why, and what to do about it.
