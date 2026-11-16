# agent-hw

Two agents and one shared testbed they both run against.

| Folder | What it is |
|---|---|
| `summarizer/` | **Summarizer**: reads every `.py` file and writes a static summary (offline, no API key) |
| `difftest/` | **DiffTest** (Student 15 - Maddie Perez): reads the git diff and writes new pytest tests for the changed code |
| `testbed/` | Source for the shared testbed: `baseline/` (initial code + tests) and `change/` (an edit to calculator.py and greeter.py) |
| `reset_testbed.sh` | Rebuilds `test_repo/` from `testbed/` using git |

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

cd summarizer
python run_agent.py --target ../test_repo --max-steps 15 --format text --output summary.txt --log-file ./logs/baseline.log
cd ..

cd difftest
export ANTHROPIC_API_KEY=...        # or add --mock-response fixtures/mock_response.md to run offline
python run_agent.py --target ../test_repo --max-steps 5 --log-file ./logs/baseline.log --report ./logs/baseline.json
cd ..
```
Each agent's own README lists its options.
