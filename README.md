# agent-hw

Two agents and one shared testbed they both run against.

| Folder | What it is |
|---|---|
| `summarizer/` | **Summarizer**: reads every `.py` file and writes a static summary (offline, no API key) |
| `difftest/` | **DiffTest** (Student 15 - Maddie Perez): reads the git diff and writes new pytest tests for the changed code |
| `testbed/` | Source for the shared testbed: `baseline/` (initial code + tests) and `change/` (an edit to calculator.py and greeter.py) |
| `reset_testbed.sh` | Rebuilds `test_repo/` from `testbed/` using git |
| `run_experiments.sh` | Part 3: baseline, iterative and adversarial runs of both agents |
| `experiments/` | Adversarial input files, offline replies, and results |
| `FINDINGS.md` | Part 3/4 notes: what broke, what we changed, before/after |

## The shared testbed
```bash
bash reset_testbed.sh               # test_repo/ = baseline commit + uncommitted change
bash reset_testbed.sh --no-change   # test_repo/ = baseline commit only
```
`test_repo/` is a small git repo with `calculator.py`, `greeter.py` and `tests/`. The change adds `mean`, `percent_of`, a type check in `divide`, and whitespace/empty-name handling plus an `excited` option in `Greeter.greet`. The Summarizer summarizes all of it; DiffTest writes tests for the change. `test_repo/` is generated, so it isn't committed. Run the reset script before every run.

## Run each agent
```bash
pip install -r difftest/requirements.txt
bash reset_testbed.sh

python3 summarizer/run_agent.py --target ./test_repo --output ./summarizer/summary.txt --log-file ./summarizer/logs/baseline.log

python3 difftest/run_agent.py --target ./test_repo --mock-response ./difftest/fixtures/mock_response.md --log-file ./difftest/logs/baseline.log --report ./difftest/logs/baseline.json
```
Each agent's own README lists its options.

## Part 3: experiments
```bash
export ANTHROPIC_API_KEY=...
bash run_experiments.sh --label v2           # real runs
bash run_experiments.sh --mock --label v2    # offline (DiffTest uses saved replies)
```
Runs both agents through:
1. **Baseline:** fresh testbed.
2. **Iterative:** no reset; each agent re-runs on top of its first pass.
3. **Adversarial:** decoy file, misleading docstring, syntax error, 1.2 MB file, helper named like a test, a bug injected into `percent_of`, and tight `--max-steps`.

If `python3` on your machine doesn't have pytest, put `PYTHON=python` in front of the command.

Everything is saved to `experiments/results/<label>/`, and `SUMMARY.txt` gives the one-line result of each run. To compare with the agents before the Part 4 changes, check out the Part 3 commit and run with `--label v1`.
