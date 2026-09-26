# Andrew Barnes

Finance analyst (FP&A) who writes code. Most of my open-source time goes to Bitcoin and Lightning payments, AI inference infrastructure, and the Python tooling in between. I like bugs that only show up on one platform, after a restart, or halfway through a message.

<a href="https://bortlesboat.github.io/#motion-study"><img src="https://bortlesboat.github.io/reel/reel.gif" alt="Proof of Work: a 15-second motion study rendered frame by frame in canvas code" width="100%"></a>

**Proof of Work**, a 15-second motion study drawn frame by frame in canvas code. [Watch it render live](https://bortlesboat.github.io/reel/) · [1080p60 with sound](https://bortlesboat.github.io/reel/reel-1080.mp4)

## Selected work

| Project | Change | What was hard about it |
| --- | --- | --- |
| [NSA Ghidra](https://github.com/NationalSecurityAgency/ghidra/pull/9642) | PyGhidra: keep bean properties out of script globals iteration | With no program open, JPype bean properties like `firstFunction` throw on read, so iterating script globals (and interpreter completion) broke. Took a second round after maintainer review to cover the no-program case. |
| [vLLM](https://github.com/vllm-project/vllm/pulls?q=author%3ABortlesboat+is%3Amerged) | ROCm fixes, incl. a `cu_seqlens_q` off-by-one in AITER speculative decode ([#39120](https://github.com/vllm-project/vllm/pull/39120)) and config registration before tokenizer init ([#40299](https://github.com/vllm-project/vllm/pull/40299)) | Six merged. Most were found by reading AMD kernel paths against the backend they were supposed to match. |
| [Mesh-LLM](https://github.com/Mesh-LLM/mesh-llm/pulls?q=author%3ABortlesboat+is%3Amerged) | Owner keystore and signed+encrypted message primitives ([#156](https://github.com/Mesh-LLM/mesh-llm/pull/156)), then a run of Windows fixes | Nine merged in a fast-moving Rust distributed-inference project; I mostly own Windows breakage there now. |
| [rust-lightning](https://github.com/lightningdevkit/rust-lightning/pull/4470) | Expose current dust exposure in `ChannelDetails` | Operators can now watch how close a channel is to its dust limit, counting commitment fees as well as dust HTLCs. |
| [rust-bitcoin](https://github.com/rust-bitcoin/rust-bitcoin/pull/5781) | `From<Infallible>` for 31 public error types | Small idea, wide surface: `units`, `primitives` and `consensus_encoding` all had to line up so generic `?` code compiles. |
| [HoloViz Panel](https://github.com/holoviz/panel/pull/8758) | Fix nested Plotly array loss across clients | Reusing a figure dropped nested array data for the second client. Binary serialization was mutating containers that shallow copies still shared. |
| [LiveKit Agents](https://github.com/livekit/agents/pull/6568) | Forward provider events through session restarts | Provider-specific realtime events were lost every time the fallback wrapper swapped its child session. |
| [ordinals/ord](https://github.com/ordinals/ord/pull/4558) | Warn when exporting addresses without the address index | Replaced a hard error with a warning, following maintainer direction from an earlier PR. |

## In review

- **Bitcoin Core** [#36190](https://github.com/bitcoin/bitcoin/pull/36190): tests that the `bitcoin` wrapper reports child exit status correctly on Windows. Code-review ACKed; waiting on a dependency.
- **x402** [#1873](https://github.com/x402-foundation/x402/pull/1873): request-bound Lightning upfront payments for the Python SDK, with replay protection that holds across restarts.
- **NEAR** [near-sdk-rs #1638](https://github.com/near/near-sdk-rs/pull/1638): ABI generation failed to link on Windows MSVC hosts for about two years.

## What I'm working on

- **x402 + Lightning in Python.** Payment verification, settlement and replay handling. Notes: [x402-work.md](x402-work.md).
- **Bitcoin research.** What a private-payment wallet has to keep so it can still recover and spend after a service disappears. Reproducible experiments and their limits: [bitcoin-research](bitcoin-research/README.md).
- **[Wallet policy kit](https://bortlesboat.github.io/Bortlesboat/).** Try the Python-only checks for coin-pool separation, or reproduce payments and saved-wallet restarts on regtest. [Report a trial or wallet use case](https://github.com/Bortlesboat/Bortlesboat/issues/new?template=wallet-policy-trial.yml).
- **Mesh-LLM on Windows.**

## Things I maintain

- [bitcoin-mcp](https://github.com/Bortlesboat/bitcoin-mcp): MCP server that gives agents Bitcoin node, mempool and fee context. 50 tools, 180 tests.
- [Satoshi API](https://github.com/Bortlesboat/bitcoin-api): self-hostable fee-intelligence API behind bitcoin-mcp, with optional x402 payments. The public hosted instance is paused.
- [qlib-options](https://github.com/Bortlesboat/qlib-options): options snapshot and factor pipeline for Microsoft qlib.

## Finance side

The day job is FP&A. The overlap shows up in [OpenBB](https://github.com/OpenBB-finance/OpenBB/pulls?q=author%3ABortlesboat+is%3Apr) and qlib work, variance-commentary tooling, and a lot of Python that turns messy finance data into something a person can sign off on. [Case studies](case-studies.md).

## Full record

231 merged pull requests to 152 repositories outside my account since March 2026, every month through September. [Dated list and search method](github-contributions.md#verified-contribution-pattern) · [raw JSON](oss-contributions.json) · [portfolio](github-portfolio.md)

[Site](https://bortlesboat.github.io) · [X @BTCOrangeCoin](https://x.com/BTCOrangeCoin)
