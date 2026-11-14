"""Bounded JSON upload validation and local content-addressed dataset storage."""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StringConstraints, ValidationError
from pipeline.demo_data import demo_candidates

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_PROFILES = 5000
DATASET_DIR = Path(os.environ.get("TALENTLENS_DATASET_DIR", Path.home() / ".local/share/talentlens-datasets"))
Text = Annotated[str, StringConstraints(strict=True, max_length=100000)]
Name = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=200)]
Number = Annotated[float, Field(strict=True, allow_inf_nan=False)]
Nonnegative = Annotated[Number, Field(ge=0)]
Rate = Annotated[Number, Field(ge=0, le=1)]
Score = Annotated[Number, Field(ge=0, le=100)]


class Record(BaseModel):
    model_config = ConfigDict(extra="allow", allow_inf_nan=False, validate_default=True)


class Profile(Record):
    anonymized_name: Text
    headline: Text
    summary: Text
    current_title: Name
    location: Text
    current_company: Text
    current_industry: Text
    current_company_size: Text
    country: Text = ""
    years_of_experience: Annotated[Number, Field(ge=0, le=80)]


class Skill(Record):
    name: Name
    proficiency: Text = "intermediate"
    endorsements: Nonnegative = 0
    duration_months: Nonnegative = 0


class Career(Record):
    title: Text
    company: Text
    company_size: Text
    description: Text
    start_date: Text
    end_date: Text | None = None
    duration_months: Nonnegative | str = 0


class Education(Record):
    degree: Text
    field_of_study: Text
    institution: Text
    tier: Text = "unknown"
    start_year: int | str | None = None
    end_year: int | str | None = None


class Certification(Record):
    name: Text


class Signals(Record):
    skill_assessment_scores: dict[Name, Score] = Field(default_factory=dict)
    open_to_work_flag: StrictBool = False
    last_active_date: Text | None = None
    recruiter_response_rate: Rate = 0
    avg_response_time_hours: Nonnegative = 999
    interview_completion_rate: Rate = .5
    offer_acceptance_rate: Annotated[Number, Field(ge=-1, le=1)] = -1
    notice_period_days: Nonnegative = 60
    profile_views_received_30d: Nonnegative = 0
    saved_by_recruiters_30d: Nonnegative = 0
    search_appearance_30d: Nonnegative = 0
    github_activity_score: Annotated[Number, Field(ge=-1, le=100)] = -1
    profile_completeness_score: Score = 50
    endorsements_received: Nonnegative = 0
    connection_count: Nonnegative = 0
    verified_email: StrictBool = False
    verified_phone: StrictBool = False
    linkedin_connected: StrictBool = False
    willing_to_relocate: StrictBool = False


class Candidate(Record):
    candidate_id: Name
    profile: Profile
    redrob_signals: Signals = Field(default_factory=Signals)
    skills: list[Skill] = Field(default_factory=list, max_length=500)
    career_history: list[Career] = Field(default_factory=list, max_length=500)
    education: list[Education] = Field(default_factory=list, max_length=100)
    certifications: list[Certification] = Field(default_factory=list, max_length=100)


def canonical(rows):
    return json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def validate_rows(rows):
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_PROFILES:
        raise ValueError(f"Upload a JSON array containing 1–{MAX_PROFILES} candidate objects")
    result, seen = [], set()
    for index, row in enumerate(rows, 1):
        try:
            # Keep explicitly supplied input values intact; optional missing fields get safe defaults.
            parsed = Candidate.model_validate(row)
            if parsed.candidate_id in seen:
                raise ValueError(f"Profile {index}: candidate_id must be unique")
            seen.add(parsed.candidate_id)
            result.append(parsed.model_dump(mode="json"))
        except ValidationError as exc:
            issue = exc.errors(include_input=False)[0]
            location = ".".join(map(str, issue["loc"]))
            raise ValueError(f"Profile {index}, {location}: {issue['msg']}") from exc
    return result


def metadata(rows, dataset_id, label):
    return {"dataset_id": dataset_id, "fingerprint": hashlib.sha256(canonical(rows)).hexdigest(),
            "label": label, "profile_count": len(rows), "kind": "demo" if dataset_id == "demo" else "upload"}


def parse_upload(raw):
    def bad_constant(value):
        raise ValueError("JSON numbers must be finite")
    def finite_float(value):
        number = float(value)
        if not math.isfinite(number): raise ValueError("JSON numbers must be finite")
        return number
    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result: raise ValueError("Duplicate JSON object keys are not supported")
            result[key] = value
        return result
    try:
        return validate_rows(json.loads(raw.decode("utf-8-sig"), parse_constant=bad_constant,
                                       parse_float=finite_float, object_pairs_hook=unique_keys))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Upload a valid UTF-8 JSON file containing an array of candidate objects") from exc


def store_upload(raw, filename):
    if len(raw) > MAX_UPLOAD_BYTES:
        raise OverflowError("JSON upload exceeds the 10 MiB limit")
    rows = parse_upload(raw)
    contents = canonical(rows)
    digest = hashlib.sha256(contents).hexdigest()
    dataset_id = "upload_" + digest
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    path = DATASET_DIR / f"{dataset_id}.json"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=DATASET_DIR, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(contents); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None: temporary.unlink(missing_ok=True)
    return metadata(rows, dataset_id, Path(filename or "upload.json").name[:200])


def resolve_dataset(dataset_id):
    if dataset_id == "demo":
        rows = validate_rows(demo_candidates())
        return rows, metadata(rows, "demo", "Fictional demo (50 profiles)")
    if not re.fullmatch(r"upload_[0-9a-f]{64}", dataset_id):
        raise FileNotFoundError("Unknown dataset identifier; choose the demo or upload a JSON file")
    path = DATASET_DIR / f"{dataset_id}.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    if hashlib.sha256(canonical(rows)).hexdigest() != dataset_id.removeprefix("upload_"):
        raise ValueError("Stored dataset integrity check failed; upload the file again")
    return rows, metadata(rows, dataset_id, "Uploaded JSON " + dataset_id[-8:])
