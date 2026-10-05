# Test Map — what the suite actually protects

Written because "197 tests pass" answers nothing. A count is not a
description. This file maps every test file to the behavior it protects and
to the way it fails when that behavior breaks.

## The numbers, and what they mean

| Layer | Lines | Role |
|---|---|---|
| Product kernel (`mcp_server/` + `agent/` + `web/`) | 4,509 | the thing being built |
| Verification (`tests/`) | 2,175 | 164 collected pytest cases |
| Quality gates (`tools/` + `benchmarks/`) | 2,175 | what keeps the above honest |

The verification layer is roughly the same size as the kernel **on purpose**:
the product moves money under a mandate, and the guard code is the product.
Tests are NOT more than the kernel; they are about 47% of it.

## File by file

| Test file | Cases | Protects | How it fails |
|---|---|---|---|
| `test_actions.py` | 34 | The mandate lifecycle: propose / approve / execute, signature, expiry, single-use, scope binding, the approval card's six-row promises | Forged, expired, replayed, over-cap, drifted and tampered mandates execute; a card promise drifts from the receipt |
| `test_authorization_invariants.py` | 10 | I1-I7 end to end over the real HTTP route: no-session approval, no-mandate execution, replay, cap immutability, real expiry fixtures, cross-session binding, secret containment | Any refusal that the UI could trigger but the server would not |
| `test_attacks.py` | 8 | The five demo attack endpoints: each refusal must come from the guard the attack targets | An attack refused "for some reason" instead of its own guard; a refusal that never reaches the ledger |
| `test_boundaries.py` | 14 | Threat-model rows: swapped adapters under valid signatures, refusal-shaped utterances, spend denial, consumption-claim survival, proof bundles | The named boundary stops holding |
| `test_api.py` | 16 | The web surface: opening, chat routes, session memory, cross-session "Welcome back" | The HTTP contract drifts from what the UI sends |
| `test_ledger.py` | 11 | Hash-chained decision ledger: append, verify, challenge, suppression | Silence or tampering goes undetected |
| `test_tools.py` | 44 | The analysis layer: detection, evidence, thresholds, unit economics | Analysis drifts from its documented behavior |
| `test_planner.py` | 12 | The optional LLM planner boundary: intents are parsed, never authorized | The planner gains authority it must not have |
| `test_store.py` | 7 | Persistence: atomic writes, corruption fail-closed, session registry caps | State loss becomes silent |
| `test_benchmark.py` | 5 | The sealed benchmark machinery itself | A benchmark that cannot fail |
| `test_crossfoot.py` | 3 | Cost cross-footing (lines always reconcile) | Totals that no longer cross-foot |
| `test_verify.py` | 4 | Offline proof-bundle verification | A bundle that verifies without matching state |
| `test_seam.py` | 1 | The execute->record seam: a crash after the adapter ran must not re-arm the mandate | A double execution after a crash |
| `test_mcp_roundtrip.py` | 2 | The real wire: protocol negotiation, tool listing, full loop, refusal over the wire, MCP Apps resource | Protocol drift a mock would hide |

## Why the suite cannot quietly rot

1. **The mutation gate** (`tools/mutation_check.py`): deletes each of 12
   guards one at a time and requires the suite to go red. A vacuous test
   cannot survive this - "the suite stays green without the guard" is
   reported as an unproven guard, not a kill.
2. **The count gate**: one measured number, and every document that quotes a
   different one fails.
3. Two tests were flagged by a crude no-assertion scan; both were inspected
   by hand and both assert (the scanner cannot see assertions behind nested
   function definitions). The scan itself is not a gate - the mutation gate
   is.

## Known hole

`web/app.js` (~1,500 lines of frontend logic) has **no automated tests** -
it is exercised by the browser-driven walkthrough documented in
`docs/evidence/` screenshots, but not by CI. The DOM is thin on purpose
(render the card the backend sends), and the backend contract has its own
tests, but this remains the least-tested surface in the repo and is the
first place new work should go.
