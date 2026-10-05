# Contributing to SpendLatch

This project makes a specific claim: every statement in the documentation
can be checked against the code, and one command checks all of it.

    python run_checks.py

If that command is green, the claim holds. Everything below exists to keep
it that way.

---

## What the checks are for

Each gate below exists because it caught something real. None of them is
decoration, and each one was verified by breaking the thing it guards and
watching it fail.

| Gate | What it stops |
|---|---|
| compile check | a broken gate script that looks like a passing gate |
| pytest | ordinary regressions |
| sealed benchmark | analysis drifting away from its evidence |
| MCP roundtrip | the wire protocol breaking, not just the functions |
| integrity manifest | uncommitted or altered source |
| evidence freshness | evidence describing older code than it claims |
| test count | the documented number drifting from the measured one |
| submission copy | the judge-facing text naming things that do not exist |
| mutation check | a guard that has quietly stopped being enforced |

`tools/mutation_check.py` runs separately, before a commit. It disables one
guard at a time in a throwaway copy of the repository and requires the suite
to go red. Ten guards, ten kills. A new guard must be registered there, or
it is not covered.

---

## Rules that were learned the hard way

**1. A test that passes when the guard is removed does not prove the guard.**
*(Three of ours did, 2026-10-05: the cap test tripped the proof-hash check first; the ledger-trim test was caught by the status field; `test_mcp_surface_cannot_approve` called the actions layer and never the MCP surface it was named after.)*
Three of ours did. One was satisfied by an earlier check firing first
instead of the one it claimed to test. One asserted on the newest receipt
when it meant a specific one. One was named after a surface it never
called. Register new guards in the mutation check, or the claim is unproven.

**2. A mutation that changes nothing is not a kill.** Replacing a condition
with `if False:` when the body was already unreachable leaves the suite
green and reads as a strong result. The mutation check now verifies the
pattern applies and that the baseline is green before it trusts a result.

**3. "All green" is not "covered."** Two of our gates were broken while every
other gate was green — a syntax error in the mutation script, and a
generated file whose content had not changed. A gate that cannot fail is
decoration; one that cries wolf gets switched off. Both are worse than
having written the check.

**3a. A mutation that lands nowhere is not a kill.**
*(2026-10-05, twice: once with `MCP_ROUNDTRIP_OK` as an anchor — a string that does not
exist in the file — reported as "the gate is strong"; and once with `Rust` and `178` as
anchors in a copy that mentions neither, reported as "three checks missed". Both times
the suite was simply never exercised.)* This is the subtlest
version of the rule above, and two of us produced it separately. A check
written against a string that does not exist in the file — a log anchor,
a forbidden word, a stale count — applies nothing, the suite stays green,
and the result reads as proof that the gate is strong. What it proves is
that the gate was never exercised.

So a mutation result is only evidence when all three of these hold:

1. the failure was injected on a real anchor,
2. the injection verifiably landed,
3. the gate went from red to green once the code was correct.

Step 2 is the one that gets skipped, and skipping it is how a broken check
gets reported as a strong one. Concretely, before trusting a mutation
result:

```bash
grep -c "the_anchor_you_injected" <the file>   # confirms it landed
```

`tools/mutation_check.py` now refuses a replacement that reproduces its own
anchor, and reports it as unproven rather than as a kill. Keep that
behaviour if you extend the mutation list.

**3b. Judge each mutation on its own.**
*(2026-10-05: four failures injected in one run, the gate went red, and the output named
two of them. "The gate failed" was read as "the gate caught four".)* Injecting four failures at once and
seeing the gate go red proves that *at least one* of the four was caught.
It says nothing about the other three, and the number of problems in the
output is the only thing that tells them apart. Two of us read "the gate
failed" as "the gate caught all four" — in each case the output named two
of the four and the other two had never been exercised.

So: inject one, run, read the output, restore. Then the next. A mutation
you did not watch fail is not evidence about that mutation.

---

## What these gates do not catch

Written down because a check that claims to cover everything is worth
less than one that says where it stops.

| Gate | Decides by | Verified against | Cannot catch |
|---|---|---|---|
| compile check | Python syntax | — | syntax in non-Python files |
| pytest | the suite passes | 178 tests | whether a test proves anything |
| mutation check | disabling a guard turns the suite red | 10 guards | nothing in principle — this is the strongest gate here |
| evidence freshness | commit order; recomputation for derived artifacts | 7 artifacts | whether the evidence's content is true |
| test count | one measured number, compared to every doc | 178 | whether the number means anything |
| submission copy | tool-ish tokens, edit distance, sentence context | 7 planted failures | prose that names nothing checkable |

The honest summary: these gates prove that the documentation matches the
code and that the guards are enforced. They do not prove the guards are
the right guards, that the tests are the right tests, or that the product
solves a problem worth solving.

**4. A gate that rewrites a file can delete half of it.**
*(2026-10-05: the test-count gate regenerated its own evidence file with the number alone,
removing the notes that explained why two counts were both correct.)* The test-count gate
regenerated its own file with the number alone and silently removed the
notes explaining why two different counts are both correct. Files a tool
owns must be written whole, every time.

**5. The document a judge reads is the one most likely to drift.**
*(2026-10-05: the submission copy lived on a desktop, outside every gate, for weeks, with
two tool names that do not exist in the code.)* The
submission copy lived outside the repository for weeks while every gate
passed, and it named two tools that do not exist. It is now tracked, and
`tools/check_submission.py` fails the build when it names an unregistered
tool, a mangled one, a stack the repository does not contain, an
authenticated session, or a stale test count.

**6. Say what a check does not prove.** The evidence freshness gate mixes
two rules: commit order for artifacts where the commit really must follow
the code, and recomputation for artifacts that are a pure function of it.
The second exists because a derived metric that does not change produces
no commit, so a timestamp rule would report it stale forever with no way
out. Both rules are written down in `docs/THREAT-MODEL.md`, and
`docs/evidence/test-count.txt` explains why two counts are both correct.

**7. A limitation written down is worth more than one discovered.** The
approval session in this demo is issued without a credential check. That is
`L1` in the threat model, it is named in the MCP surface description an
agent reads first, and it is the honest answer to "can I trust this?" —
which is a better first impression than a claim that turns out to be
wrong when someone curls the endpoint.

---

## Before you commit

```bash
python run_checks.py            # all gates
python tools/mutation_check.py  # the guards still bite
```

If you added or moved a guard, add it to the mutation list in the same
commit. If you changed a test name, check that the threat model still
points at something real.
