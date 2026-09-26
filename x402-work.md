# x402 payments: protocol and tooling work

I contribute Python payment tooling and tests to the x402 Foundation repository. The work focuses on request integrity, payment approval, and settlement behavior that application developers can verify.

Status checked September 25, 2026. Open drafts are work in review, not merged contributions.

## Merged contributions

| Contribution | What changed | Merged |
| --- | --- | --- |
| [Python MCP server tests, #1733](https://github.com/x402-foundation/x402/pull/1733) | Test coverage for the synchronous MCP server module. | March 30, 2026 |
| [Facilitator key separation, #1937](https://github.com/x402-foundation/x402/pull/1937) | Clarified which keys belong to the client, resource server and facilitator examples. | April 11, 2026 |

## Current drafts

| Contribution | Evidence and scope |
| --- | --- |
| [Python Lightning payments, #1873](https://github.com/x402-foundation/x402/pull/1873) | Implements the accepted `lnbtc` BOLT11 upfront scheme with HTTP/MCP request binding and persistent atomic replay protection. 105 focused tests and a live LND regtest run cover published vectors, invalid proofs, request substitution, concurrent replay, restart persistence and the clock-skew boundary. |
| [Python MCP payment errors, #1876](https://github.com/x402-foundation/x402/pull/1876) | Handles the real MCP SDK exception format through payment approval hooks and a bounded paid retry. Local CI-equivalent run: 2,450 passed, 71 integration tests skipped. |
| [Python facilitator HTTP server, #1908](https://github.com/x402-foundation/x402/pull/1908) | FastAPI wrapper for sync/async facilitators, with v1/v2 validation and 44 passing focused tests. |
| [Dynamic routes and settlement timing, #2006](https://github.com/x402-foundation/x402/pull/2006) | Explains authorization, upfront and escrow flows, including why a successful handler or signature check alone is not a settlement guarantee. |

The Lightning work also passed an end-to-end regtest run against two LND 0.21.3 nodes: real invoices bound to the request, real channel payments, settlement before the handler, and replay rejection across a restart. Other node implementations, testnet and mainnet are not yet tested, and no real-money payment is claimed. The Lightning extra currently uses Python 3.10–3.13 because of its native dependency's Python 3.14 build limitation.

## Tools and examples

- [x402 Seller Testkit](https://github.com/Bortlesboat/x402-seller-testkit): seller challenge validation, malformed-payment rejection and a deterministic local mock paid path. Its basic EVM profile currently covers the challenge path.
- [Express](https://github.com/Bortlesboat/x402-express-starter), [FastAPI](https://github.com/Bortlesboat/x402-fastapi-starter) and [Next.js](https://github.com/Bortlesboat/x402-nextjs-starter) starters: require an explicitly configured facilitator and recipient. The former Satoshi hosted facilitator is paused.

This complements my finance work: understanding when a payment is authorized, settled or recoverable helps with spend controls, reconciliation and the economics of paid agent tools.
