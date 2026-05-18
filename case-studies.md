# Bortlesboat Case Studies

These are public-safe proof summaries for roles or grants that value Bitcoin infrastructure, agent tooling, financial automation, and practical open-source execution.

## Current Hackathon Build: AgentOps Ledger

**Problem:** Enterprise teams cannot safely hand agents real tools, paid APIs, or approval-gated workflows without knowing what the agent did on the way to the final answer.

**Implementation:** Built AgentOps Ledger in the public `x402-insights` repo as a flight recorder for enterprise agents: TypeScript SDK helpers, Express/SQLite run ledger, dashboard, deterministic vendor-risk demo data, audit JSON export, x402-style payment events, and a Splunk HEC adapter.

**Tests:** SDK, server, and Splunk HEC adapter smoke tests pass; static hosted-demo verifier checks metadata, proof links, and case-study coverage; Playwright screenshots verify desktop and mobile rendering.

**Evidence:** [Hosted case study](https://bortlesboat.github.io/x402-insights/case-study.html), [repository](https://github.com/Bortlesboat/x402-insights), [hosted demo](https://bortlesboat.github.io/x402-insights/), [release](https://github.com/Bortlesboat/x402-insights/releases/tag/agentops-ledger-2026-05-18), [architecture](https://github.com/Bortlesboat/x402-insights/blob/main/ARCHITECTURE.md), [Splunk HEC proof](https://github.com/Bortlesboat/x402-insights/blob/main/docs/hackathon/splunk-hec-proof.md).

**Result:** A polished, public 2026 enterprise-agent hackathon artifact that turns tool calls, approval gates, retries, errors, x402 payments, and final outcomes into inspectable run evidence.

**Relevance:** Strong proof for enterprise-agent infrastructure, agent observability, x402 payments, Splunk telemetry, and hackathon/grant credibility. Submissions and prize outcomes are tracked separately and only claimed after confirmation.

## 1. Satoshi API: Bitcoin Fee Intelligence

**Problem:** Bitcoin users and agent builders get raw fee estimates, but they need send/wait guidance that saves money and can be called from software.

**Implementation:** Built a FastAPI service around Bitcoin node data, fee/mempool analysis, paid x402 routes, public docs, and an admin/operator layer.

**Tests:** Public repo advertises 725 tests; local focused scans show hundreds of pytest cases across API, auth, analytics, admin, and x402 surfaces.

**Evidence:** [Repository](https://github.com/Bortlesboat/bitcoin-api), [live site](https://bitcoinsapi.com), [x402 auth-layer PR](https://github.com/Bortlesboat/bitcoin-api/pull/25).

**Result:** A live, open-source Bitcoin API that turns protocol data into practical fee decisions and gives the rest of the portfolio a real seller surface.

**Relevance:** Strongest anchor for Bitcoin infrastructure roles, grants, and paid API credibility.

## 2. bitcoin-mcp: Bitcoin Context For AI Agents

**Problem:** AI agents need reliable Bitcoin context without scraping block explorers or hand-wiring RPC calls.

**Implementation:** Built a Python MCP server with fee, mempool, block, transaction, mining, price, and supply tools; packaged it for one-command setup.

**Tests:** 126 tests and a GitHub Actions test badge in the public README.

**Evidence:** [Repository](https://github.com/Bortlesboat/bitcoin-mcp), [README](https://github.com/Bortlesboat/bitcoin-mcp#readme).

**Result:** 49 MCP tools, 6 prompts, 8 resources, PyPI distribution, and zero-config setup for common agent clients.

**Relevance:** Clear proof for agent infrastructure, MCP, Bitcoin developer tooling, and grant proposals around open agent access to financial data.

## 3. x402 Operator Lab And Payable MCP

**Problem:** x402 demos often stop at a toy 402 response. Operators need to understand facilitator roles, wallet separation, SIWX reuse, discovery metadata, and MCP payment behavior.

**Implementation:** Built a local x402 lab with seller, self-hosted facilitator, SIWX auth/reuse, Base Sepolia settlement, public discovery metadata, and payable MCP tools.

**Tests:** TypeScript test suite covers walletless trials, SIWX storage, MCP auth/reuse, facilitator clients, growth telemetry, and public page contracts.

**Evidence:** [x402 Foundation PR #1733](https://github.com/x402-foundation/x402/pull/1733), [Satoshi API x402 route](https://github.com/Bortlesboat/bitcoin-api), [x402 discovery surface](https://x402.bitcoinsapi.com/llms.txt).

**Result:** Practical proof that agent payments can be tested as an operator workflow, not just a protocol diagram.

**Relevance:** Strong grant and ecosystem story for x402, MCP monetization, and agent payment safety.

## 4. x402 Upstream Contributions

**Problem:** Protocol maintainers need focused tests and docs that clarify edge cases without expanding scope.

**Implementation:** Reworked x402 PR feedback into narrower sync-server tests, signed commits, and contributed docs around facilitator key separation.

**Tests:** PR #1733 added missing sync server edge-case coverage; PR #1937 clarified operational role boundaries in examples/docs.

**Evidence:** [Merged x402 Foundation PR #1733](https://github.com/x402-foundation/x402/pull/1733), [merged PR #1937](https://github.com/x402-foundation/x402/pull/1937), [open x402 author history](https://github.com/x402-foundation/x402/pulls?q=author%3ABortlesboat+is%3Apr).

**Result:** Two merged x402 Foundation contributions plus a queue of open protocol/operator follow-ups.

**Relevance:** Demonstrates maintainer-responsive contribution style in a high-signal payments ecosystem.

## 5. mesh-llm: Distributed Inference Reliability

**Problem:** Mesh inference needs security primitives, predictable startup behavior, and labels users can trust when debugging capacity.

**Implementation:** Contributed owner keystore and signed/encrypted message primitives, model-size-aware launch health timing, and clearer capacity labels.

**Tests:** PRs included Rust unit/integration coverage or focused build validation appropriate to each change.

**Evidence:** [PR #156](https://github.com/Mesh-LLM/mesh-llm/pull/156), [PR #210](https://github.com/Mesh-LLM/mesh-llm/pull/210), [PR #222](https://github.com/Mesh-LLM/mesh-llm/pull/222).

**Result:** Three merged PRs in a distributed LLM infrastructure project, including security and operator UX work.

**Relevance:** Supports senior AI infrastructure roles where reliability, security, and maintainer taste matter.

## 6. OpenViking: Cross-Platform Agent Context Reliability

**Problem:** Agent context systems need to work on Windows as well as Unix-like environments; stale PID locks and console input bugs break local operator trust.

**Implementation:** Fixed stale PID lock handling and TUI console input behavior, then added a smaller WinError 11 process-liveness fix.

**Tests:** PRs were narrow and reviewable, with changes limited to the Windows process-lock and console paths.

**Evidence:** [PR #790](https://github.com/volcengine/OpenViking/pull/790), [PR #854](https://github.com/volcengine/OpenViking/pull/854).

**Result:** Two merged OpenViking reliability fixes in a fast-moving agent context database.

**Relevance:** Good proof for agent infrastructure and cross-platform engineering roles.

## 7. qlib-options: Options Data For Quant Research

**Problem:** Microsoft qlib users can model equity data, but options-chain snapshots and derived options factors are not a clean one-command workflow.

**Implementation:** Built a Python package that collects Yahoo Finance options-chain snapshots, derives ATM IV and put/call factors, normalizes to the US trading calendar, and exports qlib-compatible binary features.

**Tests:** 25 focused unit tests cover CLI behavior, factors, symbol handling, and qlib binary export modes.

**Evidence:** [Repository](https://github.com/Bortlesboat/qlib-options), [upstream qlib issue context](https://github.com/microsoft/qlib/issues/2162).

**Result:** A small finance infrastructure package with an explicit limitation boundary: snapshot-only collection, no fake historical backfill.

**Relevance:** Strongest quant/FP&A bridge artifact because it turns financial domain knowledge into reusable tooling.

## 8. Finance Dashboard: Private FP&A Automation

**Problem:** Personal finance, custody, statements, receipts, and investment records can sprawl across portals, emails, PDFs, and CSV exports.

**Implementation:** Built a Streamlit and SQLite dashboard with spending, cash flow, budget, net worth, statement, import, categorization, custody, and finance-intake surfaces.

**Tests:** 126 local pytest cases cover import helpers, categorization, domain types, Gmail intake, posting, reporting, matching, and legacy cleanup.

**Evidence:** Sanitized case study only. The repo and data include private financial records and are intentionally not linked publicly.

**Result:** A working local finance control plane that demonstrates applied FP&A automation without exposing private data.

**Relevance:** Useful for $150K+ finance automation, analytics engineering, and FP&A systems roles.

## 9. KarpathyTalk: Agent-Readable Markdown Social App

**Problem:** Builder communities often lock posts behind opaque UI surfaces, while agents and humans need simple read access to durable markdown.

**Implementation:** Built a Go and SQLite social app with GitHub login, markdown posts, replies, reposts, profile feeds, JSON APIs, RSS, and raw markdown endpoints.

**Tests:** Schema-backed app structure, live deployment notes, and a narrow local branch for hashtag filtering.

**Evidence:** [Repository](https://github.com/Bortlesboat/KarpathyTalk).

**Result:** A small public app that treats markdown as the source of truth and keeps data accessible to humans and LLM agents.

**Relevance:** Supports agent-native product engineering and low-complexity web systems credibility.

## 10. Selected Upstream PRs: Small Patches In Serious Repos

**Problem:** High-quality open source depends on focused fixes that respect project style and reduce future maintenance cost.

**Implementation:** Contributed small, reviewable patches across Bitcoin/Lightning, Python, finance, and AI infrastructure projects.

**Tests:** Most merged PRs are test, docs, or reliability patches with narrow validation surfaces.

**Evidence:** [rust-lightning #4470](https://github.com/lightningdevkit/rust-lightning/pull/4470), [rust-bitcoin #5781](https://github.com/rust-bitcoin/rust-bitcoin/pull/5781), [CPython #145538](https://github.com/python/cpython/pull/145538), [OpenBB PRs](https://github.com/OpenBB-finance/OpenBB/pulls?q=author%3ABortlesboat+is%3Apr), [statsmodels #9773](https://github.com/statsmodels/statsmodels/pull/9773).

**Result:** Merged work in respected ecosystems, showing the ability to enter unfamiliar codebases and leave a useful patch behind.

**Relevance:** Reinforces senior-role credibility: debugging, tests, docs, and maintainability across domains.
