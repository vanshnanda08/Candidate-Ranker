"""
FastAPI backend for the Redrob Intelligent Candidate Ranker.

Wraps the existing scoring pipeline (pipeline/) behind a REST API so the
React frontend can drive it instead of Streamlit. Ranking is shared with
the CLI in pipeline/ranking.py.

Run with: uvicorn server:app --reload --port 8000
"""

from datetime import date

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from pipeline.jd_parser import get_jd
from pipeline.encoder import load_model
from pipeline.ranking import (CandidateInputError, RerankingError, load_ranking_input,
                              rank_candidates)
from pipeline.dates import parse_as_of
from pipeline.llm_reranker import generate_reasoning
from pipeline.custom_job import CustomJob, job_details
from pipeline.datasets import resolve_dataset, store_upload, MAX_UPLOAD_BYTES
import json
from pathlib import Path

app = FastAPI(title="Redrob Candidate Ranker API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_model = None


def get_model():
    global _model
    if _model is None:
        _model = load_model()
    return _model


def get_candidates(data_path: str, is_sample: bool) -> list[dict]:
    try:
        return load_ranking_input(data_path, is_sample)
    except FileNotFoundError:
        raise HTTPException(404, f"Candidates file not found: {data_path}")
    except CandidateInputError as exc:
        raise HTTPException(400, str(exc)) from exc


class RankRequest(BaseModel):
    dataset_id: str | None = Field(default=None, max_length=100)
    data_path: str = "sample_candidates.json"
    is_sample: bool = True
    top_n: int = Field(default=20, gt=0, strict=True)
    use_llm: bool = False
    llm_n: int = Field(default=30, ge=0, strict=True)
    coarse_n: int = Field(default=500, gt=0, strict=True)
    as_of: date | None = Field(default=None, description="Scoring date in YYYY-MM-DD format; defaults to local date")
    job: CustomJob | None = Field(default=None, description="Custom requirements; omit or null for the built-in job")

    @field_validator("as_of", mode="before")
    @classmethod
    def validate_as_of(cls, value):
        if value is None or type(value) is date:
            return value
        return parse_as_of(value)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/jd")
def api_jd():
    return get_jd()


@app.post("/api/rank")
def api_rank(req: RankRequest):
    dataset = None
    if req.dataset_id is not None:
        candidates, dataset = selected_dataset(req.dataset_id)
    else:
        candidates = get_candidates(req.data_path, req.is_sample)

    try:
        top = rank_candidates(candidates, top_n=req.top_n, coarse_n=req.coarse_n,
                              llm_n=req.llm_n, use_llm=req.use_llm,
                              model_factory=get_model, as_of=req.as_of, job=req.job)
    except CandidateInputError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RerankingError as exc:
        raise HTTPException(500, str(exc)) from exc

    results = []
    for s in top:
        c = s["candidate"]
        p = c["profile"]
        results.append({
            "candidate_id": c["candidate_id"],
            "rank": s["rank"],
            "display_score": s["display_score"],
            "name": p["anonymized_name"],
            "headline": p["headline"],
            "current_title": p["current_title"],
            "years_of_experience": p["years_of_experience"],
            "location": p["location"],
            "current_company": p["current_company"],
            "current_industry": p["current_industry"],
            "current_company_size": p["current_company_size"],
            "semantic_score": s["semantic_score"],
            "structured": s["structured"],
            "behavioral": s["behavioral"],
            "honeypot_penalty": s["honeypot_penalty"],
            "honeypot_flags": s["honeypot_flags"],
            "reasoning": generate_reasoning(c, s["structured"], **({"job": req.job} if req.job is not None else {})),
        })

    honeypots_in_top = sum(1 for r in results if r["honeypot_penalty"] < 0.2)

    return {
        **({"dataset": dataset} if dataset is not None else {}),
        "job": job_details(req.job),
        "total_candidates": len(candidates),
        "top_n": len(top),
        "honeypots_in_top": honeypots_in_top,
        "top_score": results[0]["display_score"] if results else 0,
        "results": results,
    }


def selected_dataset(dataset_id):
    try:
        return resolve_dataset(dataset_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, "Dataset not found. Select the demo or upload the file again.") from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(400, "Stored dataset is unavailable or invalid; upload the file again.") from exc


@app.get("/api/datasets/{dataset_id}")
def dataset_info(dataset_id: str):
    return selected_dataset(dataset_id)[1]


@app.post("/api/datasets")
async def upload_dataset(file: UploadFile = File(...)):
    try:
        if not (file.filename or "").lower().endswith(".json"):
            raise HTTPException(422, "Choose a .json file containing an array of candidate profiles")
        raw = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(raw) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "JSON upload exceeds the 10 MiB limit")
        try:
            return store_upload(raw, file.filename)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except OSError as exc:
            raise HTTPException(503, "Could not store this upload locally. Check available disk space and dataset-directory permissions.") from exc
    finally:
        await file.close()


@app.get("/api/benchmarks")
def benchmark_aggregates():
    return json.loads((Path(__file__).parent / "data/phase4b_aggregate.json").read_text())
