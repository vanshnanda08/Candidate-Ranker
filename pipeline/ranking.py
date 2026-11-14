"""Shared CLI/API ranking, with deterministic shortlist and export ordering."""

from datetime import date

from tqdm import tqdm

from pipeline.encoder import load_model, encode_candidates, encode_jd, cosine_similarities
from pipeline.loader import load_candidates, load_sample
from pipeline.jd_parser import get_jd_text_for_embedding
from pipeline.feature_scorer import compute_structured_score
from pipeline.behavioral import score_behavioral
from pipeline.honeypot import evaluate_honeypot
from pipeline.llm_reranker import rerank_batch
from pipeline.custom_job import CustomJob, compute_custom_structured_score


class CandidateInputError(ValueError):
    """The supplied dataset is not a valid candidate collection."""


class RerankingError(RuntimeError):
    """Claude integration failed outside its normal batch fallback."""


def load_ranking_input(path, is_sample):
    """Reload records each call, retaining the Phase 2A same-path edit behavior."""
    try:
        candidates = load_sample(path) if is_sample else load_candidates(path)
    except FileNotFoundError:
        raise
    except (OSError, ValueError, EOFError) as exc:
        raise CandidateInputError(f"Cannot read candidates from {path}: {exc}") from exc
    seen = set()
    for index, candidate in enumerate(candidates, 1):
        if not isinstance(candidate, dict):
            raise CandidateInputError(f"Record {index}: expected a candidate object")
        cid = candidate.get("candidate_id")
        if not isinstance(cid, str) or not cid:
            raise CandidateInputError(f"Record {index}: candidate_id must be a non-empty string")
        if cid in seen:
            raise CandidateInputError(f"Record {index}: duplicate candidate_id {cid}")
        seen.add(cid)
        for field in ("profile", "redrob_signals"):
            if not isinstance(candidate.get(field), dict):
                raise CandidateInputError(f"Candidate {cid}: {field} must be an object")
        profile = candidate["profile"]
        for field in ("anonymized_name", "headline", "summary", "current_title",
                      "location", "current_company", "current_industry", "current_company_size"):
            if not isinstance(profile.get(field), str):
                raise CandidateInputError(f"Candidate {cid}: profile.{field} must be a string")
        if type(profile.get("years_of_experience")) not in (int, float):
            raise CandidateInputError(f"Candidate {cid}: profile.years_of_experience must be numeric")
        for field in ("skills", "career_history", "education", "certifications"):
            values = candidate.get(field, [])
            if not isinstance(values, list) or not all(isinstance(v, dict) for v in values):
                raise CandidateInputError(f"Candidate {cid}: {field} must be an array of objects")
    return candidates


def validate_limits(top_n, coarse_n, llm_n):
    for name, value, minimum in (("top_n", top_n, 1), ("coarse_n", coarse_n, 1),
                                 ("llm_n", llm_n, 0)):
        if type(value) is not int or value < minimum:
            requirement = "positive" if minimum else "non-negative"
            raise ValueError(f"{name} must be a {requirement} integer")


def select_shortlist(candidates, similarities, coarse_n):
    """Resolve semantic ties before the cutoff, independent of input order."""
    indices = sorted(range(len(candidates)),
                     key=lambda i: (-float(similarities[i]), candidates[i]["candidate_id"]))
    return [(candidates[i], float(similarities[i])) for i in indices[:coarse_n]]


def compute_final_score(semantic_score, structured, behavioral, hp_penalty):
    base = (float(semantic_score) * 0.30
            + structured["structured_score"] * 0.40
            + behavioral["behavioral_score"] * 0.20
            + structured["skill_score"] * 0.05
            + structured["career_score"] * 0.05)
    return round(base * hp_penalty, 6)


def _raw_order(row):
    return (-row["final_score"], row["candidate"]["candidate_id"])


def select_and_normalize(scored, top_n):
    """Choose membership using raw scores, then resolve rounded display ties.

    Display ordering never promotes an unselected row across the raw cutoff.
    """
    top = [dict(row) for row in sorted(scored, key=_raw_order)[:top_n]]
    if not top:
        return []
    minimum = min(row["final_score"] for row in top)
    maximum = max(row["final_score"] for row in top)
    score_range = maximum - minimum if maximum > minimum else 1.0
    for row in top:
        row["display_score"] = round(0.20 + (row["final_score"] - minimum)
                                     / score_range * 0.79, 4)
    top.sort(key=lambda row: (-row["display_score"], row["candidate"]["candidate_id"]))
    for rank, row in enumerate(top, 1):
        row["rank"] = rank
    return top


def rank_candidates(candidates, *, top_n=20, coarse_n=500, llm_n=200,
                    use_llm=False, cache=True, model_factory=None, as_of: date | None = None,
                    job: CustomJob | None = None):
    validate_limits(top_n, coarse_n, llm_n)
    run_date = as_of if as_of is not None else date.today()
    print(f"Ranking as of {run_date.isoformat()}")
    if not candidates:
        return []  # Empty input must not load the embedding model or Claude.
    model = (model_factory or load_model)()
    try:
        jd_vec = encode_jd(job.embedding_text() if job is not None else get_jd_text_for_embedding(),
                           model, cache=cache)
        vectors = encode_candidates(candidates, model, cache=cache)
    except (KeyError, TypeError, AttributeError) as exc:
        raise CandidateInputError(f"Malformed candidate data while encoding: {exc}") from exc
    shortlist = select_shortlist(candidates, cosine_similarities(jd_vec, vectors), coarse_n)
    scored = []
    for candidate, similarity in tqdm(shortlist, desc="Scoring"):
        try:
            structured = (compute_custom_structured_score(candidate, job) if job is not None
                          else compute_structured_score(candidate))
            behavioral = score_behavioral(candidate, as_of=run_date)
            hp, flags = evaluate_honeypot(candidate, as_of=run_date)
        except (KeyError, TypeError, AttributeError, ValueError) as exc:
            raise CandidateInputError(f"Malformed candidate {candidate['candidate_id']}: {exc}") from exc
        scored.append({"candidate": candidate, "semantic_score": round(similarity, 4),
                       "structured": structured, "behavioral": behavioral,
                       "honeypot_penalty": round(hp, 4), "honeypot_flags": flags,
                       "final_score": compute_final_score(similarity, structured, behavioral, hp)})
    scored.sort(key=_raw_order)
    if use_llm and llm_n:
        pool = scored[:llm_n]
        # Give Claude isolated records with the precomputed score for its fallback.
        llm_candidates = [dict(row["candidate"], final_score=row["final_score"]) for row in pool]
        print(f"LLM re-ranking {len(pool)} candidates with Claude...")
        try:
            reranked = rerank_batch(llm_candidates, batch_size=5, **({"job": job} if job is not None else {}))
        except Exception as exc:
            raise RerankingError(f"LLM re-ranking failed: {exc}") from exc
        by_id = {candidate["candidate_id"]: candidate for candidate in reranked}
        for row in pool:
            result = by_id.get(row["candidate"]["candidate_id"], {})
            if "llm_score" in result:
                row["llm_score"] = result["llm_score"]
                row["final_score"] = round(row["final_score"] * 0.60 + result["llm_score"] * 0.40, 6)
                row["candidate"] = dict(row["candidate"], llm_reasoning=result.get("llm_reasoning", ""))
    else:
        print("Skipping LLM re-ranking")
    return select_and_normalize(scored, top_n)
