"""Defect injection: does the suite actually catch the risks it claims to?

A green suite only proves that the tests passed. To show that the tests have
defect-finding power, three known defects are injected into the application
one at a time, the suite is re-run, and the failures are recorded. This is a
lightweight form of mutation testing.

Run:  .venv/Scripts/python.exe tools/defect_injection.py
"""
import json
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
REPORT = ROOT / "reports" / "defect-injection.json"

MUTANTS = [
    {
        "id": "M1",
        "risk": "R1 double charge",
        "description": "idempotency lookup always misses - replays are charged again",
        "file": "app/store.py",
        "find": "            record = self.idempotency.get(key)",
        "replace": "            record = None  # injected defect",
    },
    {
        "id": "M2",
        "risk": "R2 incorrect totals",
        "description": "sum check removed - splits no longer have to match the total",
        "file": "app/money.py",
        "find": "    if sum(amounts) != total:",
        "replace": "    if False:",
    },
    {
        "id": "M3",
        "risk": "R3 partial charge",
        "description": "compensation disabled - captured splits stay captured",
        "file": "app/main.py",
        "find": "        compensation = compensate(captured, order_id, payment_id, exc.code)",
        "replace": "        compensation = 'COMPLETED'",
    },
]


def run_suite() -> dict:
    """Run the suite and read the counts from the JUnit report (stable on Windows)."""
    proc = subprocess.run(
        [str(PYTHON), "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=ROOT, capture_output=True, text=True,
    )
    suite = ET.parse(ROOT / "reports" / "junit.xml").getroot()[0].attrib
    total = int(suite["tests"])
    failures = int(suite["failures"]) + int(suite["errors"])
    summary = (f"{total - failures - int(suite['skipped'])} passed, "
               f"{failures} failed in {float(suite['time']):.2f}s")
    failed = re.findall(r"^FAILED (\S+)", proc.stdout, re.MULTILINE)
    return {"summary": summary, "failed_tests": failed}


def main() -> int:
    baseline = run_suite()
    print(f"baseline: {baseline['summary']}")
    if baseline["failed_tests"]:
        print("baseline is not green - fix the suite first")
        return 1

    results = []
    for mutant in MUTANTS:
        target = ROOT / mutant["file"]
        backup = target.with_suffix(target.suffix + ".bak")
        shutil.copy2(target, backup)
        try:
            source = target.read_text(encoding="utf-8")
            if mutant["find"] not in source:
                raise SystemExit(f"{mutant['id']}: anchor not found in {mutant['file']}")
            target.write_text(source.replace(mutant["find"], mutant["replace"]),
                              encoding="utf-8")
            outcome = run_suite()
        finally:
            shutil.move(backup, target)

        caught = bool(outcome["failed_tests"])
        results.append({**{k: mutant[k] for k in ("id", "risk", "description")},
                        "caught": caught,
                        "summary": outcome["summary"],
                        "failing_tests": outcome["failed_tests"]})
        status = "CAUGHT" if caught else "SURVIVED (test gap!)"
        print(f"{mutant['id']} {mutant['risk']}: {status} - {outcome['summary']}")
        for test in outcome["failed_tests"]:
            print(f"    - {test}")

    after = run_suite()
    score = sum(r["caught"] for r in results) / len(results) * 100
    payload = {
        "baseline": baseline["summary"],
        "restored": after["summary"],
        "mutants": results,
        "detection_rate_percent": round(score, 1),
    }
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\ndetection rate: {score:.0f}%   restored: {after['summary']}")
    return 0 if score == 100 else 1


if __name__ == "__main__":
    sys.exit(main())
