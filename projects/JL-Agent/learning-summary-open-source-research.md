# 简历生成助手 — Open-Source Landscape Study
## Resume Generation & Agent-Based Job-Search/Interview Applications

> **Purpose**: Knowledge-transfer document for the upcoming 简历生成助手 development. It summarizes mature, high-visibility, and highly-discussed open-source projects related to **resume generation**, **resume–JD tailoring**, and **agent-based interview/job-search applications**, extracting technical architectures, implementation patterns, best practices, and actionable recommendations.
>
> **Research date**: 2026-08-06 ｜ **Data sources**: GitHub API (star counts verified), official READMEs, third-party write-ups (see [Sources](#9-sources-and-references)). Star counts are snapshots and will drift.
>
> **Related lineage**: This study builds on the prior analysis of the author's own [MS-Agent / MS-Agent-Lite](https://github.com/LI-PG1/MS-Agent) (fixed-pipeline, local-first, resume+JD → 8-part interview-prep HTML). 简历生成助手 should consciously borrow what works from both MS-Agent and the ecosystem below.

---

## 1. Executive Summary

| Project | Stars | License | Category | Stack (core) | Relevance to 简历生成助手 |
|---|---|---|---|---|---|
| [santifer/career-ops](https://github.com/santifer/career-ops) | ~63,000 | MIT | **Agentic job-search pipeline** (runs inside AI coding CLIs) | Claude Code skills / Node.js / Playwright / Go TUI | Highest-visibility reference for "agent that runs your whole job search"; human-in-the-loop design |
| [srbhr/Resume-Matcher](https://github.com/srbhr/Resume-Matcher) | ~28,000 | Apache-2.0 | Resume tailoring / matching / scoring | FastAPI, Next.js 16 + React 19, LiteLLM (100+ LLMs incl. local Ollama), TinyDB, Playwright PDF | Resume↔JD matching, scoring, keyword gap analysis; multi-provider LLM gateway |
| [AmruthPillai/Reactive-Resume](https://github.com/AmruthPillai/Reactive-Resume) | ~13k–20k | MIT | Resume **builder** (design + export) | TanStack Start (React 19), PostgreSQL+Drizzle, ORPC, Better Auth, Tailwind, client-side PDF | Template system, drag-and-drop builder UX, self-hosting, import/export formats |
| [xitanggg/open-resume](https://github.com/xitanggg/open-resume) | ~8,800 | AGPL-3.0 | Resume builder + **parser** (100% client-side) | Next.js 13, React, Redux Toolkit, Tailwind, PDF.js, react-pdf | **Local-first privacy pattern** (no server at all); PDF import→structured data; ATS-friendliness |
| [zzzlip/langgraph-AI-interview-agent](https://github.com/zzzlip/langgraph-AI-interview-agent) | ~60 | — | Full interview-assist platform (China Software Cup) | Java platform + Python worker, LangGraph + LlamaIndex, RAG, SSE, MinIO/RabbitMQ | Resume eval/optimization, algorithm testing (Codeforces), mock interview, multimodal analysis |
| [Kiyra-gjx/Interview-Agent](https://github.com/Kiyra-gjx/Interview-Agent) (fork of [Snailclimb/interview-guide](https://github.com/Snailclimb/interview-guide)) | ~4 | AGPL-3.0 | **Agent runtime** over interview business | Java 21, Spring Boot 4, Spring AI 2, PostgreSQL+pgvector, Redis Stream, MinIO | Session/turn/trace/memory/guardrail/approval runtime; RAG with evidence; eval harness |
| [Ranjit2111/AI-Interview-Agent](https://github.com/Ranjit2111/AI-Interview-Agent) | mid | — | Multi-agent **mock interview** with coaching | React+Vite, FastAPI, LangGraph/LangChain, TTS/STT, Docker | Interactive mock-interview loop, performance analysis, adaptive follow-ups |
| [Priyanshu7439/AI-Multi-Agent-Interview-Preparation-Platform](https://github.com/Priyanshu7439/AI-Multi-Agent-Interview-Preparation-Platform) | early | — | Multi-agent interview prep (RAG) | FastAPI, LangGraph, LangChain, Gemini, ChromaDB | Gap analysis → tailored questions → mock interview → evaluation, clean-architecture monolith |
| [speedyapply/JobSpy](https://github.com/speedyapply/JobSpy) | ~3,300 | MIT | Job **discovery** (scraping) library | Python | Programmatic job search across LinkedIn/Indeed/Glassdoor/Google — ToS-sensitive, use with care |
| [Gsync/jobsync](https://github.com/Gsync/jobsync) | ~560 | MIT | Self-hosted job-app **tracker** + AI review | — | Application CRM + AI resume review; data-location caution |
| [LingyiChen-AI/JadeAI](https://github.com/LingyiChen-AI/JadeAI) | ~1,200 | Apache-2.0 | AI resume builder + optimizer | — | Templates + parsing + optimization + JD match + Docker deploy |

**Headline takeaways**
1. The market is bifurcated: **"builders/design tools"** (Reactive-Resume, OpenResume) vs **"agentic pipelines"** (career-ops, Resume-Matcher, interview agents). MS-Agent/简历生成助手 occupy the underserved middle: *content generation from resume+JD with quality gates*.
2. The most successful (career-ops: 63k stars in ~4 months) project proves **"agentic ≠ autonomous"** — its manifesto is *filter, never spray-and-pray; AI recommends, human decides*.
3. **Privacy/local-first is a durable differentiator**: OpenResume runs 100% in-browser; Resume-Matcher supports fully local Ollama; career-ops runs inside your local AI CLI. This validates MS-Agent's core positioning.
4. Every serious project has a **quality/verification story**: Resume-Matcher has resume scoring + keyword analysis; career-ops has an A–G structured evaluation rubric + posting-legitimacy (ghost-job) check; interview agents have staged eval harnesses (fixed eval sets, benchmarks, regression). MS-Agent's verify/check gates are ahead of most, but there is room to formalize eval sets (see §8).

---

## 2. Scope & Method

- **Search targets**: GitHub repositories with `resume generator`, `resume-ai`, `ai-resume`, `interview agent`, `interview preparation`, `job search agent` topics/keywords; filtered for high stars, activity, and community discussion (Discord, Product Hunt, press).
- **Shortlist criteria**: (a) mature/highly-starred (≥1k stars) where possible; (b) small but architecturally instructive projects included deliberately (LangGraph/Java interview agents, voice coach); (c) relevance to the MS-Agent/简历生成助手 product direction (resume+JD → interview-prep content, agentic orchestration, local-first).
- **Data collected**: star counts & activity via GitHub REST API; README/architecture docs via raw file fetch; third-party evaluations (press, blog, topic pages) via web search.
- **Limitations**: only public metadata + READMEs were analyzed (not full source trees); star counts are dated snapshots; the GitHub MCP tools were unavailable (network fetch failed), so GitHub API/WebFetch was used instead.

---

## 3. Project Deep-Dives

### 3.1 career-ops (santifer) — ~63,000★, MIT, JavaScript — the "agentic pipeline" benchmark

**What it is**: Turns any AI coding CLI (Claude Code, Codex, OpenCode, Antigravity, Qwen, Kimi, Grok Build) into a full job-search command center. Written by a person who claims to have evaluated 740+ listings, generated 100+ tailored CVs, and landed a Head-of-Applied-AI role with it. Built with Claude Code.

**Core features**
- **Auto-Pipeline**: paste a job URL → full evaluation + tailored PDF + tracker entry.
- **A–G Evaluation rubric**: blocks A–F scored across 5 weighted dimensions (role summary, CV match, level strategy, comp research, personalization, interview prep STAR+R) plus **Block G: posting-legitimacy check** (flags scams/ghost jobs) and a Work-Auth blocker signal.
- **Interview Story Bank**: accumulates STAR+Reflection master stories reusable for any behavioral question.
- **ATS-optimized PDF generation** (Space Grotesk + DM Sans) via HTML + Playwright; cover letters with keyword mirroring and a draft-in-chat approval gate.
- **Portal Scanner**: 100+ pre-configured companies (Anthropic, OpenAI, n8n…) across Ashby/Greenhouse/Lever/Wellfound.
- **Batch processing** with headless CLI workers; **Dashboard TUI** (Go + Bubble Tea); plugin system (Gmail, Notion, Apify), disabled by default.
- **Human-in-the-Loop is explicit**: "the system never submits an application — you always have the final call."

**Architecture insight (why it matters)**
- It is **not** an open-loop autonomous agent. It is a **library of deterministic "modes" (markdown skill files) + evaluation prompts + Playwright tooling** that an AI CLI executes step-by-step. The "agent" is the coding CLI; career-ops is the discipline layer (rubrics, templates, tracker, integrity checks).
- *Lesson for 简历生成助手*: the highest-velocity open-source pattern right now is **skill/mode files that an agent CLI reads and executes**, not bespoke agent runtimes. This validates MS-Agent's "deterministic CLI > open-loop agent" decision and suggests a cheap extension path: expose 简历生成助手 capabilities as skill files for AI CLIs.

### 3.2 Resume-Matcher (srbhr) — ~28,000★, Apache-2.0, TypeScript+Python — the "resume↔JD engine"

**What it is**: "The #1 AI Harness for Building Resumes, PDFs, Cover Letters & more, locally with 100+ LLMs support."

**Core features**
- Master resume → per-JD tailored resume (upload PDF/DOCX, paste JD).
- **Resume Scoring & Keyword Highlighting**: match score vs JD, keyword gaps, improvement suggestions.
- Resume Builder (edit suggested content, add/remove/reorder sections via drag-drop, multiple templates), Cover Letter Generator, **Interview Preparation** (structured, resume-grounded prep; on-demand or automatic).
- PDF export via Playwright headless Chromium; i18n UI (EN/ES/中文/JP/PT) and multi-language content generation.

**Architecture**
- Backend: **FastAPI (Python 3.13), LiteLLM** (100+ LLMs: Ollama local, OpenAI, Anthropic, Gemini, OpenRouter, DeepSeek). Frontend: **Next.js 16 + React 19 + Tailwind 4**. DB: **TinyDB (JSON file)**. PDF: headless Chromium via Playwright. Docker images published for amd64/arm64.

**Key patterns**
- **Master-resume → tailoring** is the industry-standard data model (vs. generating from scratch each time). MS-Agent's "upload resume as authoritative source" is a variant; adding a "master facts" store would enable reuse.
- **LiteLLM as a gateway** replaces hand-rolled multi-provider fallback (MS-Agent hand-rolls this in `llm_gateway.js` — fine for 4 deps, but LiteLLM is the ecosystem-proven alternative if scope grows).
- Scoring is explicitly directional ("ATS-style scores are directional, not truth — do not keyword-stuff or invent experience").

### 3.3 Reactive-Resume (AmruthPillai) — ~13k–20k★, MIT, TypeScript — the "builder/design tool" benchmark

**What it is**: A free, open-source resume builder focused on *creating, updating, and sharing*; privacy-first (no tracking/ads), self-hostable, with AI integration (OpenAI, Gemini, Claude).

**Features**: real-time preview; export PDF/JSON/DOCX; drag-and-drop sections; custom sections; rich text editor; 14+ named templates (A4/Letter, custom colors/fonts/spacing via structured style rules); shareable links; JSON-Resume import; dark mode; passkey/2FA; **client-side PDF generation via @react-pdf/renderer since v5.1** (no Browserless/Chromium dependency).

**Architecture**: monorepo (apps/web, apps/api, apps/print); TanStack Start (React 19 + Vite); PostgreSQL + Drizzle ORM; **ORPC (type-safe RPC)**; Better Auth; Zustand + TanStack Query; Tailwind; Base UI + shadcn-style.

**Key patterns**
- **Template/design-as-data**: "Structured Style Rules" let sections and text be styled by rules — the same philosophy as MS-Agent's `templates/skeleton.html` + components, taken to a data-driven level.
- **Zero external print service** (client-side PDF) directly matches MS-Agent's "single self-contained HTML, no build step" ethos and removes the biggest infra pain (PDF rendering).
- Self-hosting via `docker compose` (PostgreSQL + optional SeaweedFS).

### 3.4 OpenResume (xitanggg) — ~8,800★, AGPL-3.0, TypeScript — the "pure local-first" benchmark

**What it is**: Resume builder + resume **parser**, with a stated goal of free access to modern professional resume design.

**Features**: real-time PDF preview while typing; modern ATS-friendly design (U.S. best practices, works with Greenhouse/Lever); **privacy focus — runs entirely in the browser, no sign-up, no data leaves the browser, works offline**; **import from existing resume PDF** (parse → structured data → redesign in seconds); resume **parser** for ATS readability checks.

**Architecture**: Next.js 13 static; React + Redux Toolkit + Tailwind; PDF.js for parsing; react-pdf for rendering; 4 page routes (`/`, `/resume-import`, `/resume-builder`, `/resume-parser`); resume parser algorithm documented in depth.

**Key patterns**
- **100% client-side processing** is the ultimate privacy story — no server, no keys, works offline. Directly validates MS-Agent's local-first positioning and suggests a stretch goal: a fully client-side 简历生成助手 mode for parsing.
- **PDF import → structured JSON** is a killer UX (resume redesign in seconds); MS-Agent already parses PDF/DOCX/TXT/MD, but OpenResume shows the *restructure* path, not just text extraction.
- Caveat: AGPL-3.0 — not a code-copy candidate, but a great pattern reference.

### 3.5 langgraph-AI-interview-agent (zzzlip) — ~60★ — the "full interview-assist platform"

A China Software Cup A3 competition project: **Java platform layer + Python AI Worker (LangGraph + LlamaIndex) + static frontend + Docker Compose** (MySQL/Redis/RabbitMQ/MinIO). Features: resume **evaluation** (5-dimension scoring: future potential, education, stack-match, experience-match, structure; downloadable report + radar chart), resume **optimization** (structural analysis, empty/verbose wording fixes, keyword gaps — "keeps real experience, no fabricated business results"), **algorithm testing** (task generation + Codeforces question sourcing + async submission checking), **mock interview** (multi-type questions, follow-up decisions, stage state, in-task memory compression, final report), **multimodal analysis** (ASR/video via DashScope), question bank + reports stored in MinIO.

**Architecture insight**: split "platform (auth/tasks/files/messaging)" from "worker (AI logic)" with **RabbitMQ command/feedback channels + MinIO object store + SQLite idempotency** — a production-grade async long-task architecture. SSE feeds the frontend. API keys never appear in responses/SSE/logs; user-level key config supported.

**Lesson for 简历生成助手**: when generation is long (minutes), an **async task queue + idempotent consumers + object storage** beats an in-process task map (MS-Agent's current approach: in-memory Map + 30-min TTL). Not needed for v1, but the migration path is clear.

### 3.6 Interview-Agent (Kiyra-gjx) / upstream interview-guide (Snailclimb) — ~4★, AGPL-3.0

A fork of Snailclimb's well-known interview platform, rebuilt around a genuine **Agent runtime**: session/turn/message/step-trace/terminal state; **domain tools** (resume profiling, KB RAG search, interview history, gap analysis, follow-up planning); **memory/context budget + snapshots**; **guardrails/approval (risk levels, runtime approval, safe degradation)**; **trace/evals** (fixed eval sets, regression samples, benchmarks); Workbench + Trace Explorer UI. Stack: Java 21, Spring Boot 4, **Spring AI 2**, PostgreSQL + **pgvector**, Redis Stream async tasks, MinIO; React 18 + TS + Vite frontend; Apache Tika/iText for parsing/reports.

**Key patterns (the most advanced of the interview-agent group)**
- **Resume-as-tool**: resume profiling is a *tool the agent calls*, not just pipeline input.
- **RAG with evidence**: KB search is a first-class tool; roadmap explicitly includes *chunk source evidence* and *injection-safety* evaluations (Stage 7).
- **Eval-driven agent development**: Gradle tasks like `agentStage2Eval`, `agentStage5Benchmark`, `agentStage5RecoveryEval` — fixed scenarios for success/degradation/failure-recovery paths.
- AGPL-3.0: strong copyleft; use as reference, not dependency.

### 3.7 Other notable projects (brief)

- **Ranjit2111/AI-Interview-Agent**: multi-agent mock interview with real-time coaching, adaptive follow-ups, performance analysis; React+Vite SPA + FastAPI backend + Docker; 151 commits — a good small-scale reference for interactive loops and TTS/STT integration.
- **Priyanshu7439/AI-Multi-Agent-Interview-Preparation-Platform**: clean-architecture FastAPI + LangGraph + ChromaDB + Gemini; resume+JD → RAG gap analysis → tailored questions → simulated interview → evaluation; includes a security audit report. Small, but shows the canonical "multi-agent interview" pipeline in one repo.
- **casuro/interview-prep-voice-ai**: LiveKit Agents + OpenAI Realtime API voice coach for STAR behavioral practice; sub-100ms voice loop. Shows the "voice mock interview" future direction.
- **JobSpy** (~3.3k★, MIT): programmatic job discovery across LinkedIn/Indeed/Glassdoor/Google; brittle and ToS-sensitive — treat as optional data source, not core.
- **jobsync** (~560★, MIT): self-hosted job-application tracker + AI resume review; the "CRM layer" idea (track every application, resume version, response rate).
- **JadeAI** (~1.2k★, Apache-2.0): AI resume builder with templates, parsing, optimization, JD match analysis, Docker deploy.

---

## 4. Cross-Cutting Technical Patterns (What the Mature Projects Share)

1. **Master-facts → per-JD tailoring** (Resume-Matcher, career-ops): keep a canonical resume/facts store; tailor per JD. MS-Agent already treats the uploaded resume as authoritative; formalize a "facts/number-ledger" schema.
2. **Human-in-the-loop by design** (career-ops manifesto): agent evaluates/recommends; user decides/acts. Auto-apply is explicitly anti-pattern. MS-Agent's "审核 WARN + 人工复核" aligns; the P2 "auto-regenerate on WARN" must remain toggleable.
3. **Structured evaluation rubrics** (career-ops A–G, Resume-Matcher scoring, zzzlip 5-dimension resume scoring): quality is driven by *fixed, weighted rubrics with explicit reasoning*, not vibes. MS-Agent's runCheck is a manual-pass; a rubric-scored report (1–5 per dimension) would be a step-change.
4. **Verification & anti-fabrication gates** (all): no project fabricates content for the user; rules like "keep real experience, no fixed templates that fake business results" (zzzlip) and "ATS scores are directional, don't keyword-stuff" (Resume-Matcher) echo MS-Agent's 参与边界卡 + 数字口径红线.
5. **Multi-provider LLM gateways** (Resume-Matcher via LiteLLM; MS-Agent hand-rolled; zzzlip per-user keys): provider-agnostic access + graceful fallback is table stakes; supporting **local models (Ollama)** is a differentiator for privacy-minded users.
6. **Async long-task architecture** (zzzlip: RabbitMQ+MinIO+SQLite idempotency; Kiyra-gjx: Redis Stream): long generations should be decoupled from the request thread with idempotency and object storage. MS-Agent's in-process approach is fine at small scale.
7. **PDF is the export king** (all builders): generated via headless Chromium (Playwright) or fully client-side (react-pdf). MS-Agent outputs HTML; adding PDF export (v5.1-style client-side rendering) is a high-value, low-risk feature.
8. **RAG with evidence, not vibes** (Kiyra-gjx Stage 7, zzzlip): vector search is used as a *tool with chunk-level source citations*; evaluation includes injection-safety. MS-Agent's earlier decision to skip vector DB is still correct at current data volumes, but evidence-citation (which source URL backed a fact) is the pattern to adopt — cf. MS-Agent v0.4.9 联网核实协议.
9. **Eval-driven development** (Kiyra-gjx eval stages, zzzlip TDD specs): fixed scenario sets + regression benchmarks for agent behavior. MS-Agent has manual test reports; codifying an automated eval harness is the single most impactful engineering upgrade available.
10. **LLM-as-a-service CLIs / skill files** (career-ops): the fastest-growing distribution model is "skill/mode files for AI coding CLIs" instead of bespoke runtimes. Cheap for 简历生成助手 to adopt as an additional entry point.

---

## 5. Architecture Comparison Matrix

| Dimension | career-ops | Resume-Matcher | Reactive-Resume | OpenResume | zzzlip (interview) | Kiyra-gjx (interview) | MS-Agent (baseline) |
|---|---|---|---|---|---|---|---|
| **Orchestration** | AI coding CLI + mode/skill files | Web app (FastAPI + Next.js) | Web app (TanStack Start) | Static web app (Next.js SSG) | Java platform + Python worker (MQ) | Java runtime + agent loop | Fixed pipeline (Node, no framework) |
| **Agent type** | Agentic (skill-driven, HITL) | Deterministic web flows + LLM | None (design tool + AI assist) | None | LangGraph workflows | True agent runtime (tools/guardrails/trace) | Fixed pipeline (deterministic) |
| **LLM access** | via AI CLI (Claude/Codex/etc.) | LiteLLM (100+ incl. Ollama) | OpenAI/Gemini/Claude | none (no LLM) | DeepSeek/DashScope/Codeforces | Spring AI (Bailian/qwen) | Hand-rolled gateway, cap filter + fallback |
| **Storage** | Local files (CV.md, tracker) | TinyDB (JSON) | PostgreSQL + Drizzle | Browser (none) | MySQL/Redis/MinIO | PostgreSQL + pgvector + Redis + MinIO | Local filesystem (md/JSON) |
| **PDF** | HTML + Playwright | Playwright headless Chromium | Client-side @react-pdf | Client-side react-pdf | — (report export) | iText | HTML only (printable) |
| **Async** | Batch CLI workers | sync HTTP | sync HTTP | n/a | RabbitMQ + idempotent consumers | Redis Stream | in-process Map + TTL |
| **Quality gates** | A–G rubric, ghost-job check | scoring + keyword analysis | n/a | ATS parser check | 5-dim scoring + report | eval stages + benchmark | verify (9 checks) + LLM check (PASS/WARN) |
| **Security focus** | never auto-submits | local/Ollama option | self-host, no tracking | 100% client-side | key never in logs/SSE | guardrails + approval | SSRF/path-traversal/key-mask/injection defense |

---

## 6. Feature Comparison Matrix (user-visible)

| Capability | career-ops | Resume-Matcher | Reactive-Resume | OpenResume | MS-Agent (baseline) | 简历生成助手 target |
|---|---|---|---|---|---|---|
| Resume parsing (PDF/DOCX/TXT/MD) | CV.md input | ✅ | import JSON-Resume | ✅ PDF import→structure | ✅ + OCR for scans | ✅ (keep + add PDF-import-to-structure) |
| JD input (paste/URL) | ✅ paste | ✅ paste | — | — | ✅ paste + URL fetch | ✅ |
| Per-JD tailoring | ✅ tailored CV | ✅ master→tailored | — | — | ✅ resume+JD → 8-part prep | ✅ (content engine) |
| Match scoring / gap analysis | ✅ A–F fit score | ✅ score + keyword gaps | — | — | ⚠ partial (审核 only) | ✅ rubric-scored report (1–5/dim) |
| Interview prep content | ✅ STAR+R, story bank | ✅ prep tab | — | — | ✅ 8-part HTML | ✅ (core) |
| Mock interview / practice loop | ✅ practice sessions | — | — | — | — | ⚠ roadmap (interactive loop) |
| Question bank / algorithm drill | — | — | — | — | ✅ 05 面经题库 | ✅ + Codeforces-style external sourcing |
| Application tracking | ✅ tracker + integrity | — | — | — | — | ⚠ optional CRM layer |
| Job discovery (portals) | ✅ scanner (Ashby/Greenhouse/Lever) | — | — | — | ⚠ JD URL fetch only | ⚠ optional (JobSpy-like, ToS-aware) |
| Cover letter / emails | ✅ + approval gate | ✅ | — | — | — | ⚠ optional |
| Negotiation / offer tools | ✅ scripts + offer prep | — | — | — | — | — |
| Privacy / local-first | ✅ local CLI | ✅ local/Ollama option | ✅ self-host | ✅ 100% browser | ✅ local-only | ✅ (core differentiator) |
| PDF export | ✅ | ✅ | ✅ | ✅ | ❌ HTML only | ✅ client-side renderer |
| Eval / verification | integrity checks | scoring | — | ATS check | verify+check | ✅ automated eval harness |
| Voice interface | — | — | — | — | — | ⚠ stretch (LiveKit/Realtime) |

Legend: ✅ has it ｜ ⚠ partial/roadmap ｜ ❌ absent ｜ — not applicable

---

## 7. Key Findings & Lessons (Condensed)

1. **The winning formula is "content + gates", not "chat"**: the highest-star projects convert resume+JD into *structured, scored, downloadable artifacts* with explicit anti-fabrication rules — exactly MS-Agent's model. 简历生成助手 should deepen the *scoring/eval* side, which is the weakest link today.
2. **Local-first is a defensible moat**: OpenResume (no server), Resume-Matcher (Ollama), career-ops (local CLI) all monetize trust. Keep MS-Agent's "data stays local" story; consider an Ollama/local-model path for 简历生成助手.
3. **Rubrics beat vibes**: adopt career-ops' A–G (weighted dimensions + legitimacy block) and zzzlip's 5-dimension scoring as templates for a **简历生成助手 fit report** (e.g., 简历-JD 匹配度、项目深度、技术栈对齐、表达结构、风险项), each with evidence and suggestions.
4. **HITL is a brand asset**: career-ops' "never submits" is marketing gold. 简历生成助手 should surface "what the AI changed, why, and what you must review" (diff-style audit trail).
5. **Async + idempotency when tasks get long**: monitor task duration; migrate from in-process Map to queue+object-store when generation runs grow.
6. **PDF export via client-side renderer** (React-pdf / @react-pdf/renderer) removes the single biggest infra headache and matches "no build step / single artifact" philosophy.
7. **Agent CLIs are the new distribution channel**: publishing 简历生成助手 as Claude Code/Codex skill files (like career-ops' modes) is a cheap, high-visibility extension of the current web/CLI entry points.
8. **Evidence-cited RAG**: adopt MS-Agent's 联网核实协议 evolution — every time-sensitive/claimed fact should carry a source citation and appear in a verification checklist (career-ops' ghost-job block and Kiyra-gjx's chunk-evidence stage both point here).
9. **Eval harness as the #1 engineering upgrade**: port the "fixed scenario set + regression" pattern (Kiyra-gjx Gradle eval stages) into a `tests/` + golden-output harness for 简历生成助手's pipeline.
10. **License hygiene**: Reactive-Resume/OpenResume/JadeAI examples show license choice shapes adoption (MIT/Apache-2.0 permissive vs AGPL copyleft). MS-Agent uses PolyForm Noncommercial; if 简历生成助手 aims for community adoption, consider MIT/Apache-2.0.

---

## 8. Actionable Recommendations for 简历生成助手

### 8.1 Adopt now (low effort, high value)
- **Fit report (rubric scoring)**: extend the current 审核 (PASS/WARN) into a per-dimension 1–5 scored report (resume–JD match, project depth, stack alignment, structure, risk list) with evidence citations — modeled on career-ops A–G + zzzlip 5-dim.
- **Diff-style audit trail**: record each AI change (added/changed number, reworded bullet) in a reviewable diff so users see exactly what was generated vs their resume (HITL trust).
- **PDF export (client-side)**: add `@react-pdf/renderer`-style or print-CSS based export of the 8-part HTML artifact.
- **Local-model path**: add an Ollama-compatible provider option alongside OpenAI-compatible APIs (multi-provider gateway already exists; LiteLLM-style abstraction keeps it clean).
- **Evidence-cited verification checklist**: formalize MS-Agent v0.4.9's 【待联网核实】 into a structured "source evidence" section in outputs (title + URL + extraction date per claim).

### 8.2 Plan next (medium effort)
- **Automated eval harness**: golden-output scenarios for the pipeline (parse → generate → build → verify → check), runnable via `npm test`-style commands; regression on structure markers (like verify.js section whitelist) extended to content-quality evals.
- **Async task architecture**: when generation volume grows, move from in-process Map to a queue (e.g., Node worker threads or a message queue) + idempotent consumers + object storage, mirroring zzzlip/Kiyra-gjx patterns (adapted to Node).
- **Skill-file distribution**: publish 简历生成助手 as Claude Code/Codex skill files (mode-style markdown) so the pipeline is callable from AI CLIs — the career-ops distribution model.

### 8.3 Evaluate later (strategic)
- **Interactive mock interview** (text now, voice via LiveKit/OpenAI Realtime later) built on the generated 02/03/05 content — the natural next product surface beyond static materials.
- **Application tracking / job discovery** (jobsync + JobSpy patterns) only if the product moves from "interview prep" to "job search command center"; keep ToS/privacy caution.
- **Fully client-side mode** (OpenResume pattern) as a zero-install, zero-key experience for parsing/preview, with the LLM parts remaining optional.

### 8.4 Explicit non-goals to keep (learned from MS-Agent + ecosystem)
- No open-loop autonomous agents / auto-apply (career-ops manifesto; MS-Agent fixed-pipeline decision).
- No fabrication: all numbers/projects must trace to the user's resume or cited sources.
- No vendor lock-in: provider-agnostic LLM access (local + cloud).
- Keep "no build step" and single-artifact output if at all possible.

---

## 9. Sources and References

- [santifer/career-ops README](https://github.com/santifer/career-ops) — 63,018★ (GitHub API 2026-08-06); MIT; also [career-ops.org manifesto](https://career-ops.org/manifesto)
- [srbhr/Resume-Matcher README](https://github.com/srbhr/Resume-Matcher) — 28,043★; Apache-2.0; [resumematcher.fyi](https://resumematcher.fyi)
- [AmruthPillai/Reactive-Resume README](https://github.com/AmruthPillai/Reactive-Resume) — 12,766★ per GitHub API snapshot (third-party sources cite 18k+); MIT; [rxresu.me](https://rxresu.me)
- [xitanggg/open-resume README](https://github.com/xitanggg/open-resume) — 8,803★; AGPL-3.0; [open-resume.com](https://open-resume.com)
- [zzzlip/langgraph-AI-interview-agent](https://github.com/zzzlip/langgraph-AI-interview-agent) — ~58★; Java+Python, LangGraph+LlamaIndex
- [Kiyra-gjx/Interview-Agent](https://github.com/Kiyra-gjx/Interview-Agent) — ~4★; AGPL-3.0; upstream [Snailclimb/interview-guide](https://github.com/Snailclimb/interview-guide)
- [Ranjit2111/AI-Interview-Agent](https://github.com/Ranjit2111/AI-Interview-Agent) — multi-agent mock interview
- [Priyanshu7439/AI-Multi-Agent-Interview-Preparation-Platform](https://github.com/Priyanshu7439/AI-Multi-Agent-Interview-Preparation-Platform) — FastAPI+LangGraph+ChromaDB
- [speedyapply/JobSpy](https://github.com/speedyapply/JobSpy) — ~3.3k★, MIT
- [Gsync/jobsync](https://github.com/Gsync/jobsync) — ~560★, MIT
- [LingyiChen-AI/JadeAI](https://github.com/LingyiChen-AI/JadeAI) — ~1.2k★, Apache-2.0
- [casuro/interview-prep-voice-ai](https://github.com/casuro/interview-prep-voice-ai) — LiveKit + OpenAI Realtime voice coach
- Third-party landscape write-up: *AI Job Search: Tools, Workflows, and Repos That Actually Help* (builtwithjon.com, 2026-05) — star counts & project list cross-check
- CSDN review of Reactive-Resume (2024-01) — 18k+ star citation
- Author's own baseline: [MS-Agent](https://github.com/LI-PG1/MS-Agent) / [MS-Agent-Lite](https://github.com/LI-PG1/MS-Agent-Lite) analysis (prior session, v0.4.9)

---

*Document end. Next step: 简历生成助手 requirements definition (awaiting user confirmation/requirements).*
