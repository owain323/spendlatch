# Devpost submission sheet (paste-ready)

> Fill top to bottom. Nothing here is invented: every number was produced by
> `python run_checks.py` and every link is live as of 2026-10-21.
> Stop before the final Submit and read it once with the owner.

## Project

- **Name:** SpendLatch
- **Tagline (<= 60 chars):** The authorization boundary for agent spend.
- **Track (primary):** Alexa+ (simulated experience path)
- **Mini challenge:** Open Source

## Links

- **Repo:** https://github.com/owain323/spendlatch
- **Live demo:** https://spendlatch.owain32380.cn
- **MCP endpoint:** https://spendlatch.owain32380.cn/mcp (2025-11-25, Streamable HTTP)
- **Video:** <<VIDEO_URL>> (paste the YouTube/Vimeo link after upload)

## Short description (for the card, ~2 lines)

An agent that proves a saving, proposes one exact action, and stops. A human
approves a signed, single-use mandate; the tool surface executes it once and
records the receipt. Every refusal is recorded too.

## Full description

Use the content of `submission/devpost.md` verbatim. It already carries the
invariants list, the evidence table, and the product feedback set.

## Built with

Python 3.11+, FastAPI, MCP SDK (protocol 2025-11-25) over Streamable HTTP,
vanilla JS, pytest, GitHub Actions, systemd on a Tencent Cloud VPS.

## "Try it" instructions

1. Open the live demo. It opens with the agent already speaking.
2. Click "Check this week" to see three findings with their evidence.
3. Click "Prove the saving", then "Approve (sign)", then "Execute".
4. Click "Attack: replay" and watch the second execution be refused.
5. Click "Attack: CEO says yes". Reported approval is not consent.
6. Open the Decision ledger counter: every decision, including refusals.

## Judge reproduction (zero credentials)

```
git clone https://github.com/owain323/spendlatch && cd spendlatch
pip install -e . pytest pillow
python run_checks.py            # 232 tests, benchmark, probe, mutation, integrity
python tools/verify_proof.py <bundle.json>   # offline verification
```

## Numbers to quote (verified 2026-10-21)

- 232 pytest tests (230 in the gate + 2 wire round-trip)
- sealed benchmark 12/12 public, 14/14 independent, 24/24 derived invariance
- mutation check 12/12 guards killed
- 125 files under the integrity manifest
- cross-surface probe: CROSS_SURFACE_OK (MCP proposes -> handoff -> web
  approves -> MCP executes once -> replay refused)
- real usage run: 10,901 requests across 137 days, 5 months

## Product feedback (already written)

See `submission/devpost.md` section "Product Feedback Set" — four tool groups
plus the Bedrock note marked as manual-smoke-pending. Do not claim a live
Bedrock run that did not happen.

## Friction log

See `friction-log.md` section A. Three Amazon-ecosystem entries with severity,
steps, expected vs actual, workaround and an actionable suggestion.

## Before Submit (checklist)

- [ ] Video URL is public, on YouTube or Vimeo, and in English
- [ ] The cut is 2:37.0 - the rule is "should be less than three (3) minutes",
      and judges are only guaranteed to watch the first three
- [ ] Repo is public with LICENSE visible in the About area
- [ ] Demo link loads from a logged-out browser
- [ ] Track + mini challenge selected
- [ ] Product feedback covers every tool actually used
- [ ] No internal notes, work orders, or discussion documents were published
