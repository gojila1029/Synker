#!/usr/bin/env python3
"""
verify_feature -- full verification orchestrator.

Gate order:
  verify_static -> verify_tests -> verify_api
  -> verify_database -> verify_e2e -> verify_regression

Flags:
  --continue-on-fail     run all gates even after a failure
  --skip-api             skip API startup gate
  --skip-e2e             skip E2E gate
  --evidence-dir <path>  capture each gate's output to this directory
                         and generate a verification report after all gates run
  --feature <name>       feature name for the report (used with --evidence-dir)
  --requirements <path>  requirements file for the report

Exit codes: 0=all PASS  1=one or more FAIL  2=only skips/N-A  3=BLOCKED
"""
from __future__ import annotations
import sys, os, subprocess, json
from datetime import datetime

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)
from _common import Status, EXIT, repo_root, print_header

GATES: list[tuple[str, str, str]] = [
    # (label,            script,               log_filename)
    ("Static Analysis",  "verify_static.py",   "static-check.log"),
    ("Tests",            "verify_tests.py",    "tests-unit.log"),
    ("API Startup",      "verify_api.py",      "api-results.log"),
    ("Database",         "verify_database.py", "database-results.log"),
    ("E2E",              "verify_e2e.py",      "e2e-results.log"),
    ("Regression",       "verify_regression.py", "regression-results.log"),
]

_BLOCKING = {Status.FAIL}


def _rc_to_status(rc: int) -> Status:
    if rc == 0: return Status.PASS
    if rc == 1: return Status.FAIL
    if rc == 2: return Status.NOT_APPLICABLE
    if rc == 3: return Status.BLOCKED
    return Status.FAIL


def _run_gate(script: str, evidence_dir: str | None, log_file: str) -> tuple[Status, str]:
    path = os.path.join(_SCRIPT_DIR, script)

    if evidence_dir:
        # Capture output so we can save it to evidence + still show it
        result = subprocess.run(
            [sys.executable, path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        combined = result.stdout
        if result.stderr.strip():
            combined += "\n--- stderr ---\n" + result.stderr
        # Stream to console
        print(combined, end="", flush=True)
        # Save to evidence file
        log_path = os.path.join(evidence_dir, log_file)
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(combined)
        return _rc_to_status(result.returncode), combined
    else:
        result = subprocess.run([sys.executable, path])
        return _rc_to_status(result.returncode), ""


def _badge(status: Status) -> str:
    R = "\033[0m"; G = "\033[32m"; RED = "\033[31m"; Y = "\033[33m"
    colour = {
        Status.PASS:           G,
        Status.FAIL:           RED,
        Status.SKIPPED:        Y,
        Status.BLOCKED:        Y,
        Status.NOT_APPLICABLE: Y,
    }.get(status, R)
    if sys.stdout.isatty():
        return f"{colour}{status.value:<15}{R}"
    return f"{status.value:<15}"


def main() -> int:
    args = sys.argv[1:]
    continue_on_fail = "--continue-on-fail" in args
    skip_api  = "--skip-api"  in args
    skip_e2e  = "--skip-e2e"  in args

    # Parse --evidence-dir, --feature, --requirements
    evidence_dir: str | None = None
    feature = "(unspecified)"
    requirements: str | None = None

    for i, arg in enumerate(args):
        if arg == "--evidence-dir" and i + 1 < len(args):
            evidence_dir = os.path.abspath(args[i + 1])
        if arg == "--feature" and i + 1 < len(args):
            feature = args[i + 1]
        if arg == "--requirements" and i + 1 < len(args):
            requirements = args[i + 1]

    if evidence_dir:
        os.makedirs(evidence_dir, exist_ok=True)
        print(f"\n  Evidence dir: {evidence_dir}")

    print_header("verify_feature -- full verification pipeline")

    results:      dict[str, Status] = {}
    stopped_early = False
    run_dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for label, script, log_file in GATES:
        if skip_api and script == "verify_api.py":
            results[label] = Status.NOT_APPLICABLE
            if evidence_dir:
                with open(os.path.join(evidence_dir, log_file), "w") as f:
                    f.write("SKIPPED -- --skip-api flag was set\n")
            continue
        if skip_e2e and script == "verify_e2e.py":
            results[label] = Status.NOT_APPLICABLE
            if evidence_dir:
                with open(os.path.join(evidence_dir, log_file), "w") as f:
                    f.write("SKIPPED -- --skip-e2e flag was set\n")
            continue

        sep = "=" * 62
        print(f"\n{sep}\n  Gate: {label}\n{sep}")

        status, _ = _run_gate(script, evidence_dir, log_file)
        results[label] = status

        if status in _BLOCKING and not continue_on_fail:
            print(f"\n  [{status.value}] stopping pipeline (use --continue-on-fail to run all gates)")
            stopped_early = True
            break

    # Write meta.json to evidence dir
    if evidence_dir:
        meta = {
            "run_id":   os.path.basename(evidence_dir),
            "feature":  feature,
            "datetime": run_dt,
            "gates": {
                label: {"status": status.value}
                for label, status in results.items()
            },
        }
        with open(os.path.join(evidence_dir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

    # Summary table
    bar = "=" * 62
    print(f"\n{bar}")
    print("VERIFICATION SUMMARY")
    print(bar)
    for label, status in results.items():
        print(f"  {label:<22} {_badge(status)}")
    for label, _, _lf in GATES:
        if label not in results:
            print(f"  {label:<22} {'NOT_RUN':<15}  (stopped early)")
    print(bar)

    any_fail    = any(s == Status.FAIL    for s in results.values())
    any_blocked = any(s == Status.BLOCKED for s in results.values())
    all_na_skip = all(s in (Status.NOT_APPLICABLE, Status.SKIPPED) for s in results.values())

    if any_fail or stopped_early:
        final = Status.FAIL
    elif any_blocked:
        final = Status.BLOCKED
    elif all_na_skip:
        final = Status.NOT_APPLICABLE
    else:
        final = Status.PASS

    print(f"\n  FINAL STATUS: {_badge(final)}")
    print(bar)

    # Generate report if evidence dir is set
    if evidence_dir:
        print(f"\n  Generating verification report...")
        gen_cmd = [
            sys.executable,
            os.path.join(_SCRIPT_DIR, "generate_report.py"),
            "--evidence-dir", evidence_dir,
            "--feature", feature,
        ]
        if requirements:
            gen_cmd += ["--requirements", requirements]
        subprocess.run(gen_cmd)

        # Write last-evidence.json for verification-gate.mjs to read
        runtime_dir = os.path.join(repo_root(), ".claude", "runtime")
        os.makedirs(runtime_dir, exist_ok=True)
        run_id = os.path.basename(evidence_dir)
        report_path = os.path.join(repo_root(), "verification", "reports", f"{run_id}.md")
        last_evidence = {
            "run_id": run_id,
            "evidence_dir": evidence_dir,
            "report_path": report_path,
            "final_status": final.value,
            "datetime": run_dt,
            "gates": {
                label: {"status": status.value}
                for label, status in results.items()
            },
        }
        with open(os.path.join(runtime_dir, "last-evidence.json"), "w", encoding="utf-8") as f:
            json.dump(last_evidence, f, indent=2)
        print(f"  Last-evidence written: {os.path.join(runtime_dir, 'last-evidence.json')}")

    return EXIT[final]


if __name__ == "__main__":
    sys.exit(main())
