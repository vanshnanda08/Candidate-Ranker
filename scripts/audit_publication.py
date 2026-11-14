"""Audit the exact proposed Git snapshot without printing sensitive values.

This is a focused release-content check, not a complete secret detector or a
permission grant. Only the deterministic fictional sample is allowed as data.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.demo_data import demo_candidates


def proposed_paths():
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    new = subprocess.check_output(["git", "ls-files", "--others", "--exclude-standard", "-z"], cwd=ROOT).decode().split("\0")
    return sorted(set(tracked + new) - {""})


def audit():
    findings = []
    paths = proposed_paths()
    private_path = re.compile(r"/(?:Users|home)/[A-Za-z0-9_.-]+/|[A-Z]:\\Users\\[^\\]+\\")
    credential = re.compile(r"(?:sk-ant-|sk-|gh[pousr]_|github_pat_|hf_)[A-Za-z0-9_-]{24,}|(?:AKIA|ASIA)[A-Z0-9]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
    literal_key = re.compile(r"(?i)(?:api_key|secret|password|access_token)\s*[:=]\s*['\"][A-Za-z0-9_+/=-]{20,}['\"]")
    for relative in paths:
        path = ROOT / relative
        if path.is_symlink() or not path.is_file():
            findings.append({"path": relative, "kind": "symlink or missing file"}); continue
        if any(part in {"cache", ".venv", "venv", ".model-cache", "node_modules", "dist", "uploads", "outputs", "redrob-ranker"} for part in path.relative_to(ROOT).parts):
            findings.append({"path": relative, "kind": "local/generated directory"})
        if path.suffix in {".csv", ".npy", ".npz", ".gz", ".zip", ".jsonl", ".pyc"} or path.name.startswith(".env"):
            findings.append({"path": relative, "kind": "data/cache/environment artifact"})
        if path.name in {"manifest.json", "private_rankings.json", "reviewer.csv", "reviewer_labeled.csv", "submission.csv"}:
            findings.append({"path": relative, "kind": "private/generated artifact"})
        try: content = path.read_text(encoding="utf-8")
        except UnicodeError: continue
        for number, line in enumerate(content.splitlines(), 1):
            if private_path.search(line): findings.append({"path": relative, "line": number, "kind": "private absolute path"})
            if credential.search(line) or literal_key.search(line): findings.append({"path": relative, "line": number, "kind": "credential pattern; value redacted"})
        if path.suffix == ".json":
            try: value = json.loads(content)
            except ValueError: continue
            if isinstance(value, list) and any(isinstance(row, dict) and "candidate_id" in row for row in value):
                if relative != "sample_candidates.json" or value != demo_candidates():
                    findings.append({"path": relative, "kind": "unexpected candidate records"})
    sample = json.loads((ROOT / "sample_candidates.json").read_text())
    if sample != demo_candidates(): findings.append({"path": "sample_candidates.json", "kind": "fictional sample differs from generator"})
    forbidden_images = ["assets/ranking.png", "assets/dashboard.png", "assets/dashBoard.png"]
    for name in forbidden_images:
        if name in paths: findings.append({"path": name, "kind": "legacy screenshot"})
    return {"scope": "exact tracked plus proposed nonignored snapshot files", "files_checked": len(paths),
            "fictional_sample_count": len(sample), "findings": findings,
            "files": [{"path": name, "sha256": hashlib.sha256((ROOT / name).read_bytes()).hexdigest()} for name in paths],
            "permission_status": "see PUBLICATION_STATUS.md for permission scope", "sensitive_values_printed": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    report = audit()
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key != "files"}, indent=2))
    return bool(report["findings"])


if __name__ == "__main__":
    raise SystemExit(main())
