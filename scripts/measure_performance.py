"""Local measured CLI runs; no candidate records or rankings are printed/published."""
import argparse
import json
import os
from pathlib import Path
import platform
import shlex
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.demo_data import demo_candidates


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--full-dataset", type=Path, default=ROOT / "candidates.jsonl")
    args = parser.parse_args()
    out = args.output_dir.resolve(); out.mkdir(parents=True, exist_ok=True)
    if (out / "performance.json").exists(): parser.error("Choose a new output directory; performance.json already exists")
    python = str(ROOT / ".venv/bin/python")
    env = dict(os.environ, HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", TOKENIZERS_PARALLELISM="false")
    def run(name, command):
        log = out / f"{name}.log"
        start = time.perf_counter()
        with log.open("x") as handle:
            result = subprocess.run(command, cwd=ROOT, env=env, stdout=handle, stderr=subprocess.STDOUT)
        elapsed = time.perf_counter() - start
        text = log.read_text()
        record = {"command": shlex.join(command), "wall_seconds": round(elapsed, 3), "exit_code": result.returncode,
                  "cache_hits": text.count("Embedding cache hit:"), "cache_misses": text.count("Embedding cache miss:"),
                  "encoding_operations": text.count("Encoding JD...") + text.count("Encoding 50 candidates") + text.count("Encoding 100,000 candidates"),
                  "log": str(log)}
        if result.returncode: raise RuntimeError(f"{name} failed; inspect {log}. No further runs started.")
        return record
    demo = out / "fictional-demo-50.json"
    with demo.open("x") as handle: json.dump(demo_candidates(), handle)
    shared = ["--top-n", "20", "--coarse-n", "500", "--no-llm", "--as-of", "2026-11-13"]
    report = {"hardware": {"cpu": subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], text=True).strip(),
                           "memory_bytes": int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)),
                           "logical_cpus": os.cpu_count(), "os": platform.platform(), "python": platform.python_version()},
              "conditions": {"as_of": "2026-11-13", "claude": False, "top_n_demo": 20, "top_n_full": 100,
                             "coarse_n": 500, "wall_scope": "fresh subprocess startup, imports, model load, CLI ranking, CSV write and cleanup",
                             "network": "HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1", "repeat_count": 1}, "runs": {}}
    # Prime the small demo only; it is safe to encode if not already cached.
    report["runs"]["demo_prime"] = run("demo-prime", [python, "rank.py", "--candidates", str(demo), "--sample", *shared, "--out", str(out / "demo-prime.csv")])
    report["runs"]["demo_warm"] = run("demo-warm", [python, "scripts/warm_cli.py", "--candidates", str(demo), "--sample", *shared, "--out", str(out / "demo-warm.csv")])
    preflight = "from pipeline.loader import load_candidates; from benchmarks.build_review_set import verified_embeddings; verified_embeddings(load_candidates(" + repr(str(args.full_dataset.resolve())) + "))"
    report["runs"]["full_cache_preflight"] = run("full-cache-preflight", [python, "-c", preflight])
    report["runs"]["full_warm"] = run("full-warm", [python, "scripts/warm_cli.py", "--candidates", str(args.full_dataset.resolve()),
        "--top-n", "100", "--coarse-n", "500", "--no-llm", "--as-of", "2026-11-13", "--out", str(out / "full-warm.csv")])
    report["runs"]["full_validation"] = run("full-validation", [python, "validate_submission.py", str(out / "full-warm.csv")])
    report["full_validation"] = "passed"
    (out / "performance.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__": main()
