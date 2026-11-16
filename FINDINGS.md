# Findings: Part 3 (using the agents) and Part 4 (tweaks)

For DiffTest, v1 = the agent as first built and v2 = after the Part 4 tweaks.
The numbers below come from `bash run_experiments.sh --mock`: the Summarizer runs for real (it's offline), and DiffTest uses the saved replies in `difftest/fixtures/` and `experiments/fixtures/`.
**TODO:** add the numbers from a real run (`bash run_experiments.sh --label v2`, with an API key) before submitting.

## Summarizer

"Original" = the first Summarizer commit. "Improved" = our partner's update ("improved summarizer" commit).

| Run | Original | Improved |
|---|---|---|
| Baseline | 4/4 files summarized, exit 0 | same |
| Iterative | Deterministic: the only change between passes is DiffTest's new test file showing up | same |
| Adversarial: syntax error, 1.2 MB file | Handled without crashing, but the error lines **didn't say which file failed** | Each error names its file, and it recovers partial info from broken files (clearly labeled "unverified") |
| Adversarial: `--max-steps 3` with a decoy `aaa_decoy.py` | Spent the budget alphabetically: decoy, broken file, calculator. **greeter.py skipped** | Same: still alphabetical |
| Adversarial: misleading docstring (`safe_div` says "returns 0 when b is zero"; the code just divides) | **Repeated the docstring as fact** | Same |
| Nested function (`outer` → `hidden_helper`) | Not mentioned | Same |

**Effective at:** fast, free and deterministic, never runs code, fails safely (exit 1 and "INCOMPLETE" instead of guessing).
**Weak at:** it only reports what the code *says*. Docstrings are taken at face value, and "Observed" only notes structure (has an if, has a loop), not behavior.
**Possible next tweaks:** order files by how often other files import them (so `--max-steps` covers the important code first), and warn when a docstring promises special-case behavior ("returns 0 when…") but the function has no if/try/raise.

## DiffTest

| Run | v1 | v2 |
|---|---|---|
| Baseline | 7 kept, 3 dropped (failing, useless, duplicate), all 11 tests pass | 6 kept: the deliberately wrong `== 33.33` test contradicts a correct one, so both go to the suspects file (see trade-off) |
| Iterative (re-run without reset) | **Regression: 7 tests → 1.** The second pass overwrote the first pass's file | 6 → 7: earlier tests kept, new test added, re-proposed names skipped |
| Adversarial: bug injected into `percent_of` (×10 instead of ×100) | **Locked in the bug:** kept `assert percent_of(1, 2) == 5.0` and dropped the correct `== 50.0` as "failed" | Neither kept; both saved to `tests/difftest_suspects.py` as a possible bug for a human to check |
| Adversarial: real helper named `test_utils.py` | Treated as a test file, so its code was never tested | Treated as source code and tested |
| Adversarial: `--max-steps 1` + 400-function decoy file | Ran in one step; the decoy only inflates the prompt (cost) | same; see the real-run token counts |
| Manual: one test with an infinite loop | **Whole batch timed out; good tests lost too** | Re-runs each test alone; drops only the hanging test |

**Effective at:** the rule-based checks are free and caught every planted bad test (fails, `assert True`, copy of an existing test).
**Weak at:** "passes" only means the test matches what the code does *now*. If the change has a bug, a passing test can lock it in. v2 only catches this when the model writes two tests that disagree. A single wrong-but-passing test still gets through, which is why the README says to review generated tests and why the prompt now asks for expectations taken from docstrings and intent.
**Trade-off we accepted:** when two tests disagree, DiffTest can't tell which one is right, so it keeps neither. That cost one correct test in the baseline. We chose to send both to a human rather than risk keeping the wrong one.
**Safety note:** DiffTest runs code written by the model. Only run it on a testbed like this one.

## Ideas we didn't build
- Use `--judge` to compare each test's expectation against the docstring (catches single wrong-but-passing tests; costs one more call).
- Mutation check: make a small change to the code and confirm the new tests fail. That proves a test actually checks something.
- Summarizer: compare docstrings against simple facts in the code (which exceptions it raises, constants it returns), not just whether it has any checks.
