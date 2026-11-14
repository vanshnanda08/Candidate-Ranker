"""Deterministic fictional public demo; separate from the legacy benchmark sample."""
from copy import deepcopy


def fictional(cid, title, years, skills, description):
    return {"candidate_id": cid, "profile": {
        "anonymized_name": cid, "headline": title, "summary": description,
        "current_title": title, "years_of_experience": years, "location": "Fictional City",
        "country": "Fictional Country", "current_company": "Example Studio",
        "current_industry": "Software", "current_company_size": "51-200"},
        "skills": [{"name": s, "proficiency": "advanced", "endorsements": 0, "duration_months": 24} for s in skills],
        "career_history": [{"title": title, "company": "Example Studio", "company_size": "51-200",
                            "description": description, "start_date": "2024-01-01", "end_date": None,
                            "duration_months": 24}], "education": [], "certifications": [],
        "redrob_signals": {"last_active_date": "2026-11-13"}}


def four_candidates():
    return [fictional("F-BACKEND", "Backend Engineer", 8, ["Java", "PostgreSQL", "Docker"],
                      "Built Java services with PostgreSQL and Docker deployment."),
            fictional("F-DATA", "Data Engineer", 5, ["PostgreSQL", "SQL", "Docker"],
                      "Built SQL pipelines using PostgreSQL and Docker for customers."),
            fictional("F-DESIGN", "Brand Designer", 6, ["Figma", "Illustrator"],
                      "Designed visual identities in Figma and Illustrator for customers."),
            fictional("F-JUNIOR", "Frontend Engineer", 2, ["JavaScript", "React", "CSS"],
                      "Implemented customer-facing React and JavaScript interfaces.")]


def demo_candidates():
    templates = four_candidates() + [fictional("F-AI", "Senior AI Engineer", 7,
        ["Python", "FAISS", "embeddings", "retrieval", "ranking", "evaluation", "a/b testing"],
        "Implemented production Python embedding retrieval with FAISS, ranking evaluation and A/B testing.")]
    result = []
    for i in range(50):
        row = deepcopy(templates[i % len(templates)])
        row["candidate_id"] = f"DEMO_{i + 1:03d}"
        row["profile"]["anonymized_name"] = f"Fictional profile {i + 1:02d}"
        result.append(row)
    return result
