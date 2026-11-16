#!/usr/bin/env bash
# Part 3: runs both agents through Baseline, Iterative and Adversarial runs and saves everything.
#
#   bash run_experiments.sh                 real DiffTest runs (needs ANTHROPIC_API_KEY)
#   bash run_experiments.sh --mock          DiffTest uses saved replies (offline, free)
#   bash run_experiments.sh --label v2      save results under experiments/results/v2 (default: v1)
#
# Results: experiments/results/<label>/  (logs, summaries, JSON reports, generated tests, SUMMARY.txt)
set -uo pipefail
cd "$(dirname "$0")"

MOCK=0; LABEL=v1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --mock) MOCK=1 ;;
    --label) LABEL="$2"; shift ;;
    *) echo "unknown option $1"; exit 2 ;;
  esac
  shift
done
if [[ $MOCK -eq 0 && -z "${ANTHROPIC_API_KEY:-}" ]]; then
  echo "ANTHROPIC_API_KEY is not set. Export it, or run with --mock."; exit 2
fi

PY=${PYTHON:-python3}
R=experiments/results/$LABEL
rm -rf "$R" && mkdir -p "$R"
GEN=test_repo/tests/test_difftest_generated.py
SUM="$R/SUMMARY.txt"
note() { echo "$*" | tee -a "$SUM"; }
count_tests() { [[ -f "$1" ]] && grep -c '^def test' "$1" || echo 0; }

summarizer() {  # name, extra args...
  local name=$1; shift
  $PY summarizer/run_agent.py --target test_repo --format text \
      --output "$R/summarizer_$name.txt" --log-file "$R/summarizer_$name.log" "$@" > "$R/summarizer_$name.stdout" 2>&1
  local code=$?
  note "  summarizer/$name: exit $code | $(sed -n 2p "$R/summarizer_$name.txt" 2>/dev/null)"
}

difftest() {  # name, mock fixture, extra args...
  local name=$1 fixture=$2; shift 2
  local mockarg=()
  [[ $MOCK -eq 1 ]] && mockarg=(--mock-response "$fixture")
  $PY difftest/run_agent.py --target test_repo "${mockarg[@]}" \
      --log-file "$R/difftest_$name.log" --report "$R/difftest_$name.json" "$@" > /dev/null 2>&1
  local code=$?
  [[ -f $GEN ]] && cp "$GEN" "$R/difftest_${name}_tests.py"
  note "  difftest/$name: exit $code | kept $(grep -c 'CHECK  KEEP' "$R/difftest_$name.log") | dropped $(grep -c 'CHECK  DROP' "$R/difftest_$name.log") | tests in output file: $(count_tests $GEN)"
}

pytest_all() {
  ( cd test_repo && $PY -m pytest -q -p no:cacheprovider 2>&1 | tail -1 )
}

note "DiffTest + Summarizer experiments — label=$LABEL mock=$MOCK — $(date)"

# ------------------------------------------------------------------ 1. BASELINE
note ""; note "== 1. BASELINE (fresh testbed) =="
bash reset_testbed.sh > /dev/null
summarizer baseline --max-steps 15
difftest baseline difftest/fixtures/mock_response.md --max-steps 5
note "  full test suite after baseline: $(pytest_all)"

# ------------------------------------------------------------------ 2. ITERATIVE
note ""; note "== 2. ITERATIVE (no reset: each agent re-runs on its own first-pass output) =="
before=$(count_tests $GEN)
summarizer iterative --max-steps 15
difftest iterative experiments/fixtures/iterative_reply.md --max-steps 5
after=$(count_tests $GEN)
diff "$R/summarizer_baseline.txt" "$R/summarizer_iterative.txt" > "$R/summarizer_iterative.diff"
note "  summarizer output changed between passes: $([[ -s $R/summarizer_iterative.diff ]] && echo "yes (see summarizer_iterative.diff)" || echo no)"
note "  difftest generated tests: $before before -> $after after$([[ $after -lt $before ]] && echo '   <-- REGRESSION: earlier tests were lost')"
note "  full test suite after iterative: $(pytest_all)"

# ------------------------------------------------------------------ 3. ADVERSARIAL
note ""; note "== 3. ADVERSARIAL (decoy, misleading docstring, syntax error, oversized file, ambiguous file name, injected bug, tight max-steps) =="
bash reset_testbed.sh > /dev/null
cp experiments/adversarial/*.py test_repo/
$PY -c "print('x = 1\n' * 200000, end='')" > test_repo/huge.py                     # 1.2 MB
sed -i.bak 's/\* 100, 1)/* 10, 1)/' test_repo/calculator.py && rm -f test_repo/calculator.py.bak   # bug: percent_of off by 10x
summarizer adversarial_tight --max-steps 3
note "  summarizer with --max-steps 3 analyzed: $(grep '^File:' "$R/summarizer_adversarial_tight.txt" | sed 's/File: //' | tr '\n' ' ')"
summarizer adversarial_full --max-steps 50
note "  summarizer repeats the misleading docstring for safe_div: $(grep -q 'returning 0 when b is zero' "$R/summarizer_adversarial_full.txt" && echo yes || echo no)"
note "  summarizer flags the mismatch: $(grep -qi 'warning' "$R/summarizer_adversarial_full.txt" && echo yes || echo no)"
rm -f test_repo/huge.py                                                                  # keep the API prompt affordable
$PY -c "print(''.join(f'def decoy_{i}(x):\n    \"\"\"Decoy {i}.\"\"\"\n    return x + {i}\n\n' for i in range(400)))" > test_repo/big_decoy.py
difftest adversarial experiments/fixtures/adversarial_reply.md --max-steps 1
note "  difftest kept a test that locks in the injected bug: $(grep -q 'KEEP.*buggy\|== 5.0' "$R/difftest_adversarial_tests.py" 2>/dev/null && echo yes || echo 'no / check log')"
note "  difftest set aside tests as possible bugs for review: $(grep -o 'SUSPECT [0-9]* test' "$R/difftest_adversarial.log" | grep -o '[0-9]*' || echo 0)"
[[ -f test_repo/tests/difftest_suspects.py ]] && cp test_repo/tests/difftest_suspects.py "$R/difftest_adversarial_suspects.py"
note "  difftest treated test_utils.py (real code) as a test file: $(grep -q 'test_utils.py' "$R/difftest_adversarial.log" && echo no || echo yes)"

note ""; note "Results saved in $R/"
bash reset_testbed.sh > /dev/null
