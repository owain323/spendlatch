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

**3a. A mutation that lands nowhere is not a kill.** This is the subtlest
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

**4. A gate that rewrites a file can delete half of it.** The test-count gate
regenerated its own file with the number alone and silently removed the
notes explaining why two different counts are both correct. Files a tool
owns must be written whole, every time.

**5. The document a judge reads is the one most likely to drift.** The
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
