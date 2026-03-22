# My Approach & Thoughts

## The Problem

ISV developers receive opaque tar.gz archives from customers they can't SSH into. They manually grep through logs, cross-reference events with pod states, and try to reconstruct what went wrong — often spending hours on issues that turn out to be a misconfigured value.

## My Approach

I built a full-stack analysis platform that treats support bundles as first-class data objects, not just log dumps.

**Parser (25+ resource types):** The bundle parser handles multiple troubleshoot.sh layouts — namespace-level lists, individual resource files, nested pod logs, and YAML variants. It extracts pods, deployments, StatefulSets, DaemonSets, jobs, ingresses, HPAs, RBAC, events, and logs into a unified data model. When resource files are missing, it synthesizes context from events and logs. It also imports the bundle's own `analysis.json` findings.

**26 Heuristic Detectors:** Pattern-matching detectors catch CrashLoopBackOff, OOMKilled, ImagePullBackOff, pending pods, node pressure, certificate expiration, DNS failures, connection errors, RBAC violations, service selector mismatches, ingress misconfigurations, missing resource limits, HPA scaling issues, stuck StatefulSet rollouts, failed jobs, init container failures, and troubleshoot.sh bundled analysis results. Each produces structured issues with evidence, remediation steps, and kubectl commands.

**AI Root Cause Analysis:** Heuristic findings are sent to an LLM with rich cluster context — degraded workloads, pod ownership chains, ingress routes, HPA concerns — for deeper analysis. It identifies cascading failures, correlates issues across components, and generates actionable insights that pattern matching alone can't find.

**RAG-Enhanced Chat:** Bundle data is chunked and embedded into a vector store. Users ask natural language questions and get answers grounded in actual bundle evidence with source citations.

## What Makes This Interesting

**Preflight Spec Generation:** Detected issues are converted into troubleshoot.sh `v1beta2` preflight specs. An ISV gives these to customers to run *before* problems escalate — closing the loop from diagnosis to prevention. Directly useful to Replicated's ecosystem.

**Live Analysis Progress:** Analysis streams via SSE — users watch each step in real-time (parsing → detectors → AI → topology) instead of staring at a spinner.

**Content-Hash Caching:** Identical bundles return cached results instantly via SHA-256 hash matching.

**3D Cluster Topology:** Interactive Three.js visualization of the full resource graph with ownership edges, health-based coloring (failing resources glow red), and search/fullscreen/inspect.

## Thoughts on the Domain

The most interesting aspect is that support bundles are *snapshots* — you see the aftermath, not the sequence of events. The real challenge isn't detecting that a pod is crashing (that's obvious), but reconstructing *why* — tracing from a service with no endpoints, to a missing label, to a deployment that was updated with the wrong selector. AI excels here because it can reason about relationships that span multiple resource types and namespaces simultaneously.

The next frontier is connecting bundles to the vendor's known architecture. If the ISV knows their app needs Redis, the analyzer should immediately check for Redis health without being told — turning generic K8s analysis into application-aware diagnostics.
