"""Request-local custom requirements. The benchmarked default scorer stays separate."""

import re
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from pipeline.jd_parser import get_jd

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160, strict=True)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, min_length=20, max_length=20000, strict=True)]
Skill = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100, strict=True)]


class CustomJob(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    title: Title
    description: Description
    required_skills: tuple[Skill, ...] = Field(default=(), max_length=50)
    preferred_skills: tuple[Skill, ...] = Field(default=(), max_length=50)
    experience_min: float | None = Field(default=None, ge=0, le=80, allow_inf_nan=False)
    experience_max: float | None = Field(default=None, ge=0, le=80, allow_inf_nan=False)

    @field_validator("experience_min", "experience_max", mode="before")
    @classmethod
    def numeric_years(cls, value):
        if value is not None and type(value) not in (int, float):
            raise ValueError("Enter years as a number between 0 and 80, or omit the bound")
        return value

    @model_validator(mode="after")
    def consistent_requirements(self):
        if not any(c.isalnum() for c in self.title):
            raise ValueError("Enter a descriptive job title containing letters or numbers")
        if (self.experience_min is not None and self.experience_max is not None
                and self.experience_min > self.experience_max):
            raise ValueError("Minimum experience must not exceed maximum experience")
        skills = [normalize(s) for s in (*self.required_skills, *self.preferred_skills)]
        if any(not any(c.isalnum() for c in skill) for skill in skills):
            raise ValueError("Each skill must contain letters or numbers, such as Python or C++")
        if len(skills) != len(set(skills)):
            raise ValueError("List each skill once, across required and preferred skills")
        return self

    def embedding_text(self):
        """Stable job text, including every supplied structured requirement."""
        lines = [self.title, self.description]
        if self.required_skills:
            lines.append("Required skills: " + ", ".join(self.required_skills))
        if self.preferred_skills:
            lines.append("Preferred skills: " + ", ".join(self.preferred_skills))
        if self.experience_min is not None:
            lines.append(f"Minimum experience: {self.experience_min:g} years")
        if self.experience_max is not None:
            lines.append(f"Maximum experience: {self.experience_max:g} years")
        return "\n".join(lines)


def normalize(text):
    return re.sub(r"\s+", " ", text.casefold().replace("-", " ")).strip()


def matches(term, text):
    # No substring matches such as Java in JavaScript, or R in engineer.
    return bool(re.search(r"(?<![\w+#])" + re.escape(normalize(term)) + r"(?![\w+#])", normalize(text)))


CUSTOM_POLICY = (
    "Structured skills are literal, case-insensitive phrase matches in skill tags; "
    "required/preferred coverage uses 75/25 weights, renormalized when one list is empty. "
    "No supplied skills gives a neutral 0.5. Career fit uses the submitted title and "
    "supplied skill phrases in the summary/work descriptions. Experience scores 1 within "
    "the supplied bounds, 0.5 below, 0.7 above; omitted experience, education and location "
    "each score a constant 0.5. No default-role industry or consulting preferences apply. "
    "Description informs semantic retrieval; it is not parsed into extra scoring rules. "
    "Existing behavioral signals, data-consistency checks, final weights and ordering remain."
)


def job_details(job: CustomJob | None):
    if job is not None:
        return {"mode": "custom", **job.model_dump(mode="json"), "scoring_notes": CUSTOM_POLICY}
    jd = get_jd()
    return {"mode": "default", "title": "Senior AI Engineer", "description": jd["raw_text"],
            "required_skills": list(jd["must_have_skills"]),
            "preferred_skills": list(jd["nice_to_have_skills"]),
            "experience_min": jd["experience_min"], "experience_max": jd["experience_max"],
            "scoring_notes": "Built-in Senior AI Engineer scoring and embedding text are unchanged."}


def compute_custom_structured_score(candidate, job: CustomJob):
    tags = [s["name"] for s in candidate.get("skills", [])]
    required = [s for s in job.required_skills if any(matches(s, tag) for tag in tags)]
    preferred = [s for s in job.preferred_skills if any(matches(s, tag) for tag in tags)]
    parts = []
    if job.required_skills:
        parts.append((.75, len(required) / len(job.required_skills)))
    if job.preferred_skills:
        parts.append((.25, len(preferred) / len(job.preferred_skills)))
    skill = sum(w * value for w, value in parts) / sum(w for w, _ in parts) if parts else .5
    # Preserve assessment checks, scoped to skills relevant to this job.
    proficiency = {normalize(s["name"]): s.get("proficiency") for s in candidate.get("skills", [])}
    for name, value in candidate["redrob_signals"].get("skill_assessment_scores", {}).items():
        if (any(matches(s, name) for s in (*required, *preferred))
                and proficiency.get(normalize(name)) in ("expert", "advanced") and value < 40):
            skill *= .85

    profile = candidate["profile"]
    history = candidate.get("career_history", [])
    titles = [profile["current_title"], *[j.get("title", "") for j in history]]
    # Seniority is represented by explicit experience bounds, not inferred title levels.
    words = set(re.findall(r"\w+", normalize(job.title))) - {"senior", "junior", "lead", "principal", "staff", "the", "of"}
    title_score = max((len(words & set(re.findall(r"\w+", normalize(t)))) / len(words)
                       for t in titles), default=0) if words else .5
    terms = (*job.required_skills, *job.preferred_skills)
    narrative = "\n".join([profile.get("summary", ""), *[j.get("description", "") for j in history]])
    career = (.4 * title_score + .6 * sum(matches(s, narrative) for s in terms) / len(terms)
              if terms else title_score)
    years = profile["years_of_experience"]
    if job.experience_min is None and job.experience_max is None:
        experience = .5
    elif job.experience_min is not None and years < job.experience_min:
        experience = .5
    elif job.experience_max is not None and years > job.experience_max:
        experience = .7
    else:
        experience = 1.0
    weighted = skill * .35 + career * .35 + experience * .15 + .5 * .05 + .5 * .10
    return {"structured_score": round(weighted, 4), "skill_score": round(skill, 4),
            "career_score": round(career, 4), "exp_score": experience, "edu_score": .5,
            "loc_score": .5, "must_have_skill_count": len(required),
            "matched_skills": [*required, *preferred]}
