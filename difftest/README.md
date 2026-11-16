# DiffTest

DiffTest reads code that changed in a git repo and writes new pytest tests for it.
It's a **Pipeline** agent: **Read → Write → Check**, looped up to `--max-steps` times.

| Stage | What happens |
|---|---|
| **Read** | `git diff <base>` on `.py` files, full source of each changed (non-test) file, all existing test files |
| **Write** | Claude Sonnet 5.5 (4k max tokens) returns a pytest module of new tests |
| **Check** (rule-based, free) | 1) parses? 2) imports cleanly? 3) each test passes when run? 4) has a real assert and calls changed code? 5) not a duplicate of an existing test? |
| **Check** (LLM judge, optional `--judge`) | is each surviving test actually useful? |
| **Loop** | rejected tests and their reasons go back into the next Write step |
| **Output** | kept tests → `<target>/tests/test_difftest_generated.py`, re-run together; ready for the normal test system |

### Failure modes handled (template §6)
1. **Tests that don't run**: each test is run with pytest; failing ones are dropped and their error is fed back. Import/collection errors are fed back too.
2. **Tests that run but are useless**: dropped if they have no assert, only `assert True` / `x == x`, or never call a function/class from the changed files. `--judge` adds an LLM check.
3. **Repeats of existing tests**: each test body is normalized (comments, whitespace and name removed; values kept) and compared with every existing test. At or above `--dup-threshold` (0.95) similarity, it's dropped.

## Setup
```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
bash ../reset_testbed.sh       # builds ../test_repo (shared testbed) with a pending change to test
```

## Run
```bash
# offline, reproducible, no API key (canned LLM reply that exercises every failure mode)
python run_agent.py --target ../test_repo --mock-response fixtures/mock_response.md --log-file ./logs/mock.log

# real run
python run_agent.py --target ../test_repo --max-steps 5 --log-file ./logs/baseline.log --report ./logs/baseline.json

# with the LLM judge
python run_agent.py --target ../test_repo --judge --log-file ./logs/judge.log
```
Run `bash ../reset_testbed.sh` before each run to reset the testbed. All commands run from inside `difftest/`.

## Options
| Flag | Default | Meaning |
|---|---|---|
| `--target` | required | git repo to work on |
| `--base` | `HEAD` | git ref to diff against (`HEAD` = uncommitted changes) |
| `--max-steps` | 5 | max Write→Check loops (one generation LLM call per step) |
| `--target-tests` | 5 | stop early once this many tests are kept |
| `--model` / `--max-tokens` | `claude-sonnet-5-5` / 4000 | |
| `--judge` | off | add the LLM-judge usefulness check |
| `--dup-threshold` | 0.95 | duplicate similarity cutoff |
| `--price-in` / `--price-out` | 3 / 15 | USD per 1M tokens, used only for the cost estimate in the report |
| `--mock-response` | | canned reply file; single offline step |
| `--log-file` / `--report` | | full log / JSON summary (kept, rejected + reasons, tokens, cost, time) |

Exit code: `0` = OK, `1` = the final generated file failed when re-run, `2` = bad target.

## Limits
- Python + pytest repos only.
- A passing test only means the test matches what the code does *now*. If the change introduced a bug, DiffTest can lock it in. Review generated tests before committing them.
- The usefulness rules are heuristics; `--judge` catches more but adds cost.
