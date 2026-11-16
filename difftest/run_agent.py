#!/usr/bin/env python3
"""
DiffTest — reads code that was changed and writes new tests to check that code.

Pattern: Pipeline  (Read -> Write -> Check), looped up to --max-steps times.

  READ   git diff of the target repo + full source of changed files + existing tests
  WRITE  LLM (Claude Sonnet 5.5, 4k max tokens) proposes new pytest tests
  CHECK  rule-based (free):
           1. parses?                       -> else feed syntax error back
           2. runs and passes?              -> failing tests are dropped   (failure mode 1)
           3. asserts something and calls
              changed code?                 -> else dropped as useless     (failure mode 2)
           4. duplicates an existing test?  -> dropped                     (failure mode 3)
         LLM judge (optional, --judge):  is each surviving test actually useful?
  Rejected tests + reasons are fed back into the next WRITE step.
  Kept tests are written to <target>/tests/test_difftest_generated.py,
  which then feeds the repo's normal automated test system.

Example:
  python run_agent.py --target ./test_repo --max-steps 5 --log-file ./logs/baseline.log
  python run_agent.py --target ./test_repo --mock-response ./fixtures/mock_response.md   # offline, no API key
"""
from __future__ import annotations

import argparse
import ast
import difflib
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, asdict
from pathlib import Path

DEFAULT_MODEL = "claude-sonnet-5-5"
DEFAULT_MAX_TOKENS = 4000
OUTPUT_NAME = "test_difftest_generated.py"

SYSTEM_PROMPT = (
    "You are DiffTest, a helper who writes pytest tests. You are given a diff of code that "
    "was just changed, the full current source of the changed files, and the project's existing "
    "tests. Write NEW tests that check the changed code, focusing on difficult cases: edge cases, "
    "boundary values, error handling, and the specific behavior the diff introduced. Do not repeat "
    "what existing tests already check. Do not invent functions, classes, parameters, or modules "
    "that do not exist in the source shown to you. Every test must contain at least one assert or "
    "pytest.raises. Respond with exactly one ```python code block containing a complete test "
    "module (imports at the top, then test functions named test_*), and nothing else."
)

JUDGE_PROMPT = (
    "You are a strict reviewer of unit tests. For each test below, decide if it is USEFUL: it must "
    "check behavior of the changed code that the existing tests do not already check, and its "
    "assertions must be meaningful (not tautologies like `assert True` or `assert x == x`). "
    'Reply with only JSON: {"<test_name>": {"keep": true|false, "reason": "<short>"}, ...}'
)

log = logging.getLogger("difftest")


# --------------------------------------------------------------------------- data

@dataclass
class Candidate:
    name: str
    source: str
    status: str = "pending"          # kept | failed | useless | duplicate | judged_out
    reason: str = ""


@dataclass
class RunReport:
    target: str
    base: str
    model: str
    steps_used: int = 0
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    est_cost_usd: float = 0.0
    changed_files: list = field(default_factory=list)
    kept: list = field(default_factory=list)
    rejected: list = field(default_factory=list)
    output_file: str | None = None
    final_check_passed: bool | None = None
    seconds: float = 0.0


# --------------------------------------------------------------------------- READ

def git(target: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(target), *args],
                          capture_output=True, text=True, check=True).stdout


def is_test_file(p: Path) -> bool:
    return p.name.startswith("test_") or p.name.endswith("_test.py") or "tests" in p.parts


def read_changes(target: Path, base: str) -> tuple[str, dict[str, str]]:
    """Return (diff text, {path: full source}) for changed non-test .py files."""
    diff = git(target, "diff", base, "--", "*.py")
    names = git(target, "diff", "--name-only", base, "--", "*.py").split()
    # include untracked new source files too
    names += git(target, "ls-files", "--others", "--exclude-standard", "--", "*.py").split()
    sources = {}
    for n in dict.fromkeys(names):
        p = target / n
        if p.exists() and not is_test_file(Path(n)):
            sources[n] = p.read_text()
    diff = "\n".join(
        block for block in re.split(r"(?=^diff --git )", diff, flags=re.M)
        if block and not any(is_test_file(Path(t)) for t in re.findall(r"^diff --git a/(\S+)", block, re.M))
    )
    return diff, sources


def read_existing_tests(target: Path) -> dict[str, str]:
    tests = {}
    for p in sorted(target.rglob("*.py")):
        rel = p.relative_to(target)
        if any(part.startswith(".") for part in rel.parts) or p.name == OUTPUT_NAME:
            continue
        if is_test_file(rel):
            tests[str(rel)] = p.read_text()
    return tests


# --------------------------------------------------------------------------- WRITE

class LLM:
    def __init__(self, model: str, max_tokens: int, mock_response: Path | None):
        self.model, self.max_tokens, self.mock = model, max_tokens, mock_response
        self.calls = self.input_tokens = self.output_tokens = 0
        if not mock_response:
            if not os.environ.get("ANTHROPIC_API_KEY"):
                sys.exit("ANTHROPIC_API_KEY is not set (or pass --mock-response for an offline run).")
            import anthropic
            self.client = anthropic.Anthropic()

    def ask(self, system: str, user: str) -> str:
        self.calls += 1
        if self.mock:
            log.info("WRITE  using mock response from %s", self.mock)
            return self.mock.read_text()
        resp = self.client.messages.create(
            model=self.model, max_tokens=self.max_tokens, system=system,
            messages=[{"role": "user", "content": user}],
        )
        self.input_tokens += resp.usage.input_tokens
        self.output_tokens += resp.usage.output_tokens
        log.info("LLM    %d in / %d out tokens", resp.usage.input_tokens, resp.usage.output_tokens)
        return "".join(b.text for b in resp.content if b.type == "text")


def build_prompt(diff: str, sources: dict, tests: dict, feedback: str) -> str:
    parts = ["## Diff of changed code\n```diff\n" + diff + "\n```"]
    for path, src in sources.items():
        parts.append(f"## Current source: {path}\n```python\n{src}\n```")
    if tests:
        for path, src in tests.items():
            parts.append(f"## Existing test file: {path}\n```python\n{src}\n```")
    else:
        parts.append("## Existing tests\n(none)")
    parts.append("## Import note\nTests run from the repository root with it on sys.path, so "
                 "import modules by their path relative to the root (e.g. `from pkg.mod import f`).")
    if feedback:
        parts.append("## Feedback on your previous attempt\n" + feedback)
    return "\n\n".join(parts)


def extract_code(text: str) -> str:
    m = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.S)
    return (m.group(1) if m else text).strip() + "\n"


# --------------------------------------------------------------------------- CHECK

def split_module(code: str) -> tuple[str, list[Candidate]]:
    """Split a test module into (header: imports/fixtures/helpers, [test functions])."""
    tree = ast.parse(code)
    lines = code.splitlines(keepends=True)
    header, cands = [], []
    for node in tree.body:
        start = (node.decorator_list[0].lineno if getattr(node, "decorator_list", None) else node.lineno) - 1
        seg = "".join(lines[start:node.end_lineno])
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
            cands.append(Candidate(node.name, seg))
        else:
            header.append(seg)
    return "".join(header), cands


def run_pytest(target: Path, test_file: Path, timeout: int) -> dict[str, tuple[str, str]]:
    """Run one test file; return {test_name: (outcome, message)}."""
    with tempfile.TemporaryDirectory() as td:
        xml = Path(td) / "r.xml"
        cmd = [sys.executable, "-m", "pytest", str(test_file), "-q", "-p", "no:cacheprovider",
               f"--junitxml={xml}", "--rootdir", str(target)]
        try:
            proc = subprocess.run(cmd, cwd=target, capture_output=True, text=True, timeout=timeout,
                                  env={**os.environ, "PYTHONPATH": str(target)})
        except subprocess.TimeoutExpired:
            return {"__module__": ("error", f"pytest timed out after {timeout}s")}
        if not xml.exists():
            return {"__module__": ("error", (proc.stdout + proc.stderr)[-1500:])}
        results = {}
        for tc in ET.parse(xml).iter("testcase"):
            name = tc.get("name").split("[")[0]
            if not tc.get("classname"):              # pytest reports collection errors as a fake testcase
                bad = tc.find("error")
                msg = (bad.text or bad.get("message") or "") if bad is not None else ""
                return {"__module__": ("error", msg[-1500:] or (proc.stdout + proc.stderr)[-1500:])}
            bad = tc.find("failure") if tc.find("failure") is not None else tc.find("error")
            if bad is not None:
                results[name] = ("failed", (bad.get("message") or bad.text or "")[:400])
            elif tc.find("skipped") is not None:
                results[name] = ("failed", "skipped")
            else:
                results.setdefault(name, ("passed", ""))
        if not results:   # collection error (e.g. bad import)
            results["__module__"] = ("error", (proc.stdout + proc.stderr)[-1500:])
        return results


def defined_names(sources: dict) -> set[str]:
    names = set()
    for src in sources.values():
        try:
            for n in ast.walk(ast.parse(src)):
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    names.add(n.name)
        except SyntaxError:
            pass
    return names


def usefulness_problem(c: Candidate, changed_names: set[str]) -> str | None:
    fn = ast.parse(textwrap.dedent(c.source)).body[0]
    nodes = list(ast.walk(fn))
    has_assert = any(isinstance(n, ast.Assert) for n in nodes) or "raises" in c.source
    if not has_assert:
        return "no assert / pytest.raises"
    for n in nodes:
        if isinstance(n, ast.Assert) and isinstance(n.test, ast.Constant) and n.test.value:
            return "trivial assert (assert True)"
        if (isinstance(n, ast.Assert) and isinstance(n.test, ast.Compare) and len(n.test.comparators) == 1
                and ast.dump(n.test.left) == ast.dump(n.test.comparators[0])):
            return "tautological assert (x == x)"
    called = {n.func.id if isinstance(n.func, ast.Name) else getattr(n.func, "attr", None)
              for n in nodes if isinstance(n, ast.Call)}
    if changed_names and not (called & changed_names):
        return "does not call any function/class from the changed files"
    return None


def normalize(src: str) -> str:
    """Test body re-printed from its AST (comments/whitespace/name stripped, values kept)."""
    fn = ast.parse(textwrap.dedent(src)).body[0]
    return "\n".join(ast.unparse(s) for s in fn.body)


def existing_test_bodies(tests: dict) -> dict[str, str]:
    out = {}
    for path, src in tests.items():
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for n in ast.walk(tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test"):
                out[f"{path}::{n.name}"] = "\n".join(ast.unparse(s) for s in n.body)
    return out


def duplicate_of(c: Candidate, existing: dict[str, str], threshold: float) -> str | None:
    mine = normalize(c.source)
    for name, body in existing.items():
        if difflib.SequenceMatcher(None, mine, body, autojunk=False).ratio() >= threshold:
            return name
    return None


def judge(llm: LLM, diff: str, cands: list[Candidate]) -> dict:
    user = ("## Diff\n```diff\n" + diff + "\n```\n\n## Tests to review\n" +
            "\n\n".join(f"```python\n{c.source}```" for c in cands))
    raw = llm.ask(JUDGE_PROMPT, user)
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        return json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        log.warning("JUDGE  returned non-JSON; keeping all tests")
        return {}


# --------------------------------------------------------------------------- pipeline

def run(args) -> RunReport:
    t0 = time.time()
    target = Path(args.target).resolve()
    report = RunReport(str(target), args.base, args.model)

    # ---------------- READ
    diff, sources = read_changes(target, args.base)
    if not sources:
        log.info("READ   no changed source files vs %s — nothing to do", args.base)
        return report
    tests = read_existing_tests(target)
    report.changed_files = list(sources)
    changed_names = defined_names(sources)
    existing = existing_test_bodies(tests)
    log.info("READ   %d changed file(s): %s", len(sources), ", ".join(sources))
    log.info("READ   %d existing test file(s), %d existing tests", len(tests), len(existing))

    llm = LLM(args.model, args.max_tokens, Path(args.mock_response) if args.mock_response else None)
    out_dir = target / "tests"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / OUTPUT_NAME

    kept: dict[str, Candidate] = {}
    header = ""
    feedback = ""
    seen_names: set[str] = set()

    for step in range(1, args.max_steps + 1):
        report.steps_used = step
        log.info("---- step %d/%d ----", step, args.max_steps)

        # ---------------- WRITE
        if kept:
            feedback += ("\nAlready accepted (do not repeat): " + ", ".join(kept) + "\n")
        reply = llm.ask(SYSTEM_PROMPT, build_prompt(diff, sources, tests, feedback))
        code = extract_code(reply)
        feedback = ""

        # ---------------- CHECK 1: parses
        try:
            new_header, cands = split_module(code)
        except SyntaxError as e:
            feedback = f"Your module had a syntax error: {e}. Return valid Python."
            log.info("CHECK  syntax error: %s", e)
            continue
        cands = [c for c in cands if c.name not in kept and c.name not in seen_names]
        seen_names |= {c.name for c in cands}
        if not cands:
            feedback = "You returned no new test_* functions."
            log.info("CHECK  no new test functions")
            continue
        step_header = new_header if new_header.strip() else header
        log.info("WRITE  %d candidate test(s): %s", len(cands), ", ".join(c.name for c in cands))

        # ---------------- CHECK 2: runs and passes (failure mode 1)
        trial = out_dir / f"_difftest_trial_{os.getpid()}.py"
        trial.write_text(step_header + "\n\n" + "\n\n".join(c.source for c in cands))
        try:
            results = run_pytest(target, trial, args.timeout)
        finally:
            trial.unlink(missing_ok=True)
        if "__module__" in results:
            msg = results["__module__"][1]
            feedback = f"The test module failed to import/collect:\n{msg}\nFix the imports."
            log.info("CHECK  module error:\n%s", textwrap.indent(msg, "         "))
            continue
        for c in cands:
            outcome, msg = results.get(c.name, ("failed", "not collected"))
            if outcome != "passed":
                c.status, c.reason = "failed", msg.strip().splitlines()[0] if msg.strip() else outcome

        # ---------------- CHECK 3: useful (failure mode 2)
        for c in cands:
            if c.status == "pending" and (p := usefulness_problem(c, changed_names)):
                c.status, c.reason = "useless", p

        # ---------------- CHECK 4: not a duplicate (failure mode 3)
        for c in cands:
            if c.status == "pending" and (d := duplicate_of(c, existing, args.dup_threshold)):
                c.status, c.reason = "duplicate", f"duplicates {d}"

        # ---------------- CHECK 5: LLM judge (optional)
        survivors = [c for c in cands if c.status == "pending"]
        if args.judge and survivors and not args.mock_response:
            verdicts = judge(llm, diff, survivors)
            for c in survivors:
                v = verdicts.get(c.name, {})
                if v.get("keep") is False:
                    c.status, c.reason = "judged_out", v.get("reason", "judge: not useful")

        if any(c.status == "pending" for c in cands):
            header = merge_headers(header, step_header) if header else step_header
        for c in cands:
            if c.status == "pending":
                c.status = "kept"
                kept[c.name] = c
                existing[f"generated::{c.name}"] = normalize(c.source)   # later steps can't repeat it
                log.info("CHECK  KEEP   %s", c.name)
            else:
                report.rejected.append({"name": c.name, "status": c.status, "reason": c.reason, "step": step})
                log.info("CHECK  DROP   %-40s [%s] %s", c.name, c.status, c.reason)

        rejected = [c for c in cands if c.status != "kept"]
        if rejected:
            feedback = "These tests were rejected; do not resend them as-is:\n" + "\n".join(
                f"- {c.name}: {c.status} — {c.reason}" for c in rejected)

        if len(kept) >= args.target_tests:
            log.info("STOP   reached %d kept tests", len(kept))
            break
        if args.mock_response:
            log.info("STOP   mock mode runs a single step")
            break

    report.llm_calls = llm.calls
    report.input_tokens, report.output_tokens = llm.input_tokens, llm.output_tokens
    report.est_cost_usd = round(llm.input_tokens / 1e6 * args.price_in + llm.output_tokens / 1e6 * args.price_out, 4)

    # ---------------- final: write kept tests and re-run them together (feeds the test system)
    if kept:
        out_file.write_text(
            '"""Tests generated by DiffTest for changes vs ' + args.base + '. Review before committing."""\n'
            + header.strip() + "\n\n\n" + "\n\n".join(c.source.rstrip() + "\n" for c in kept.values()))
        final = run_pytest(target, out_file, args.timeout)
        report.final_check_passed = all(o == "passed" for o, _ in final.values()) and "__module__" not in final
        report.output_file = str(out_file)
        report.kept = list(kept)
        log.info("OUTPUT %d test(s) -> %s (final run %s)", len(kept), out_file,
                 "PASSED" if report.final_check_passed else "FAILED")
    else:
        log.info("OUTPUT no tests survived the checks")

    report.seconds = round(time.time() - t0, 2)
    return report


def merge_headers(a: str, b: str) -> str:
    seen = set(a.splitlines())
    return a.rstrip() + "\n" + "\n".join(l for l in b.splitlines() if l not in seen) + "\n"


# --------------------------------------------------------------------------- CLI

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="difftest", description="DiffTest: write new tests for changed code.")
    ap.add_argument("--target", required=True, help="path to a git repository")
    ap.add_argument("--base", default="HEAD", help="git ref to diff against (default: HEAD = uncommitted changes)")
    ap.add_argument("--max-steps", type=int, default=5, help="max Write->Check loops (LLM generation calls)")
    ap.add_argument("--target-tests", type=int, default=5, help="stop early once this many tests are kept")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    ap.add_argument("--judge", action="store_true", help="also run the LLM-judge usefulness check")
    ap.add_argument("--dup-threshold", type=float, default=0.95, help="similarity of normalized test bodies (values included) at/above which a test is a duplicate")
    ap.add_argument("--timeout", type=int, default=120, help="pytest timeout in seconds")
    ap.add_argument("--price-in", type=float, default=3.0, help="USD per 1M input tokens (for cost estimate)")
    ap.add_argument("--price-out", type=float, default=15.0, help="USD per 1M output tokens (for cost estimate)")
    ap.add_argument("--mock-response", help="file with a canned LLM reply; runs offline with no API key")
    ap.add_argument("--log-file", help="write the full run log here")
    ap.add_argument("--report", help="write a JSON run report here")
    args = ap.parse_args(argv)

    handlers = [logging.StreamHandler(sys.stdout)]
    if args.log_file:
        Path(args.log_file).parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(args.log_file, mode="w"))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S", handlers=handlers)

    if not (Path(args.target) / ".git").exists():
        log.error("--target must be a git repository: %s", args.target)
        return 2

    report = run(args)
    summary = json.dumps(asdict(report), indent=2)
    log.info("REPORT\n%s", summary)
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(summary)
    if report.final_check_passed is False:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
