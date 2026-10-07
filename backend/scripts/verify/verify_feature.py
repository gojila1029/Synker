"""Deterministic final gate for harness-orchestrator runs.

Exit codes: 0=PASS, 1=FAIL, 2=NOT_APPLICABLE, 3=BLOCKED
"""
import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", required=True)
    parser.add_argument("--feature", required=True)
    parser.add_argument("--requirements", required=True)
    parser.add_argument("--continue-on-fail", action="store_true")
    args = parser.parse_args()

    repo_root = Path(__file__).parent.parent.parent
    state_path = repo_root / ".claude" / "runtime" / "orchestration-state.json"
    last_evidence_path = repo_root / ".claude" / "runtime" / "last-evidence.json"
    evidence_dir = repo_root / args.evidence_dir
    requirements_path = repo_root / args.requirements

    findings: list[str] = []
    gate_results: dict[str, str] = {}
    overall = "PASS"

    if not state_path.exists():
        print("ERROR: orchestration-state.json not found")
        return 3

    with open(state_path) as f:
        state = json.load(f)

    for gate in ["validator", "regression", "independent_review"]:
        status = state.get(gate, {}).get("status", "PENDING")
        gate_results[gate] = status
        if status != "PASS":
            findings.append(f"GATE {gate}: {status} (required: PASS)")
            overall = "FAIL"

    if not evidence_dir.exists():
        findings.append(f"Evidence directory missing: {args.evidence_dir}")
        overall = "FAIL"
    else:
        ev_files = list(evidence_dir.glob("*.md"))
        gate_results["evidence_files"] = str(len(ev_files))

    gate_results["contract"] = "FOUND" if requirements_path.exists() else "MISSING"
    if not requirements_path.exists():
        overall = "FAIL"

    print(f"Feature: {args.feature}")
    for k, v in gate_results.items():
        print(f"  {k}: {v}")
    if findings:
        print("FINDINGS:")
        for f in findings:
            print(f"  - {f}")
    print(f"OVERALL: {overall}")

    last_evidence_path.parent.mkdir(parents=True, exist_ok=True)
    with open(last_evidence_path, "w") as f:
        json.dump({"run_id": state.get("run_id"), "feature": args.feature,
                   "overall": overall, "gates": gate_results, "findings": findings}, f, indent=2)

    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
