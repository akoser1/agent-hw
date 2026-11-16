# Summarizer (offline starter)

Requires Python 3.10+. No API key needed. Optional PDF support: `python -m pip install reportlab`.

Run: `python run_agent.py --target ./test_repo --max-steps 15 --format text --output summary.txt --log-file ./logs/baseline.log`

PDF: `python run_agent.py --target ./test_repo --format pdf --output summary.pdf`

`--max-steps` limits files inspected, not language-model reasoning steps. No code is executed. A nonzero exit code means some files failed or were omitted. Results are deterministic for the same files and Python version.
