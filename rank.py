"""
Main entry point for the Redrob Intelligent Candidate Ranker.

Usage:
    python rank.py --candidates candidates.jsonl.gz --out submission.csv
    python rank.py --candidates candidates.jsonl.gz --out submission.csv --no-llm
    python rank.py --candidates sample_candidates.json --out submission.csv --sample
"""

import argparse
import csv
import time

from pipeline.ranking import (CandidateInputError, RerankingError, load_ranking_input,
                              rank_candidates, compute_final_score)
from pipeline.llm_reranker import generate_reasoning
from pipeline.dates import parse_as_of


def positive_integer(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def nonnegative_integer(value):
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be a non-negative integer")
    return number


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Redrob Candidate Ranker")
    parser.add_argument("--candidates", required=True, help="Path to candidates.jsonl.gz or sample_candidates.json")
    parser.add_argument("--out", default="submission.csv", help="Output CSV path")
    parser.add_argument("--top-n", type=positive_integer, default=100, help="Number of candidates to output")
    parser.add_argument("--coarse-n", type=positive_integer, default=500, help="Candidates to pass from coarse to fine ranking")
    parser.add_argument("--llm-n", type=nonnegative_integer, default=200, help="Candidates to pass to LLM re-ranker")
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM re-ranking (faster, no API key needed)")
    parser.add_argument("--no-cache", action="store_true", help="Recompute embeddings even if cache exists")
    parser.add_argument("--as-of", type=parse_as_of, default=None, metavar="YYYY-MM-DD",
                        help="Scoring date (default: local date at the start of the run)")
    parser.add_argument("--sample", action="store_true", help="Load from JSON array (sample_candidates.json)")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    start = time.perf_counter()
    try:
        candidates = load_ranking_input(args.candidates, args.sample)
        print(f"Loaded {len(candidates):,} candidates")
        top = rank_candidates(candidates, top_n=args.top_n, coarse_n=args.coarse_n,
                              llm_n=args.llm_n, use_llm=not args.no_llm,
                              cache=not args.no_cache, as_of=args.as_of)
    except (FileNotFoundError, CandidateInputError, RerankingError) as exc:
        raise SystemExit(f"Error: {exc}") from exc

    with open(args.out, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["candidate_id", "rank", "score", "reasoning"])
        for row in top:
            writer.writerow([row["candidate"]["candidate_id"], row["rank"], row["display_score"],
                             generate_reasoning(row["candidate"], row["structured"])])
    print(f"Done in {time.perf_counter() - start:.1f}s. Output: {args.out}")
    if top:
        profile = top[0]["candidate"]["profile"]
        print(f"Top candidate: {profile['current_title']} ({profile['years_of_experience']}yrs)")
    honeypots = sum(row["honeypot_penalty"] < 0.2 for row in top)
    print(f"Honeypot candidates in top {len(top)}: {honeypots} "
          f"({'OK' if honeypots <= 10 else 'WARNING: exceeds limit!'})")


if __name__ == "__main__":
    main()
