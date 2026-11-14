"""Custom jobs: fictional profiles, offline encoders and stubbed Claude only."""
import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import numpy as np
from pydantic import ValidationError

import server
from pipeline import encoder, ranking, llm_reranker
from pipeline.custom_job import CustomJob, compute_custom_structured_score, matches
from pipeline.jd_parser import get_jd
from test_embedding_cache import FakeEncoder


class EqualSemanticEncoder(FakeEncoder):
    """Hold semantics equal so the fixture isolates explicit structured criteria."""
    def encode(self, texts, **kwargs):
        self.calls.append(list(texts))
        return np.full((len(texts), self.dimension), 1 / np.sqrt(self.dimension), dtype=np.float32)


BACKEND = dict(title="Backend Engineer", description="Build reliable Java services backed by PostgreSQL.",
               required_skills=["Java", "PostgreSQL"], preferred_skills=["Docker"],
               experience_min=3, experience_max=10)
DESIGN = dict(title="Brand Designer", description="Design visual identities and accessible brand assets.",
              required_skills=["Figma", "Illustrator"], preferred_skills=[],
              experience_min=3, experience_max=10)


def fictional(cid, title, skills, description):
    return dict(candidate_id=cid, profile=dict(anonymized_name=cid, headline=title, summary=description,
        current_title=title, years_of_experience=6, location="Fictional City", country="Fictional Country",
        current_company="Example Studio", current_industry="Design", current_company_size="51-200"),
        skills=[dict(name=s, proficiency="advanced", endorsements=0, duration_months=40) for s in skills],
        career_history=[dict(title=title, company="Example Studio", company_size="51-200", description=description,
                             start_date="2020-01-01", end_date=None, duration_months=72)],
        education=[], certifications=[], redrob_signals=dict(last_active_date="2026-11-13"))


class CustomJobTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.cache = patch.object(encoder, "CACHE_DIR", self.directory / "cache")
        self.cache.start(); self.addCleanup(self.cache.stop)
        self.model = EqualSemanticEncoder()
        self.model_patch = patch.object(server, "get_model", return_value=self.model)
        self.model_patch.start(); self.addCleanup(self.model_patch.stop)
        self.candidates = [fictional("F-BACKEND", "Backend Engineer", ["Java", "PostgreSQL", "Docker"],
                                      "Implemented Java services with PostgreSQL and Docker deployment."),
                           fictional("F-DESIGN", "Brand Designer", ["Figma", "Illustrator"],
                                      "Designed visual identities in Figma and Illustrator for customers.")]
        self.path = self.directory / "fictional.json"
        self.path.write_text(json.dumps(self.candidates))
        self.client = TestClient(server.app)

    def request(self, job=None, **overrides):
        return self.client.post("/api/rank", json=dict(data_path=str(self.path), job=job,
            is_sample=True, top_n=2, use_llm=False, as_of="2026-11-13", **overrides))

    def test_two_jobs_change_ranking_for_explicit_requirements(self):
        for job, expected in [(BACKEND, "F-BACKEND"), (DESIGN, "F-DESIGN")]:
            response = self.request(job)
            self.assertEqual(response.status_code, 200, response.text)
            data = response.json()
            self.assertEqual(data["job"]["title"], job["title"])
            first = data["results"][0]
            self.assertEqual(first["candidate_id"], expected)
            self.assertEqual(first["structured"]["skill_score"], 1)
            self.assertEqual(data["results"][1]["structured"]["skill_score"], 0)
            self.assertTrue(set(first["structured"]["matched_skills"]) <= set(job["required_skills"] + job["preferred_skills"]))
            self.assertIn(job["title"], first["reasoning"])

    def test_consecutive_custom_default_requests_are_isolated(self):
        jd = copy.deepcopy(get_jd())
        first = self.request().json()
        self.request(DESIGN)
        self.request(BACKEND)
        self.assertEqual(self.request().json(), first)
        self.assertEqual(get_jd(), jd)
        self.assertEqual(self.client.get("/api/jd").json(), jd)

    def test_concurrent_jobs_are_isolated(self):
        jobs = [BACKEND, DESIGN, BACKEND, DESIGN]
        with ThreadPoolExecutor(max_workers=4) as pool:
            responses = list(pool.map(self.request, jobs))
        for job, response in zip(jobs, responses):
            self.assertEqual(response.status_code, 200, response.text)
            data = response.json()
            self.assertEqual(data["job"]["title"], job["title"])
            self.assertEqual(data["results"][0]["candidate_id"], "F-BACKEND" if job == BACKEND else "F-DESIGN")

    def test_candidate_cache_reused_and_jobs_have_distinct_jd_entries(self):
        self.request(BACKEND)
        self.assertEqual(len(self.model.calls), 2)  # One JD and one candidate encode.
        self.request(BACKEND)
        self.assertEqual(len(self.model.calls), 2)
        self.request(DESIGN)
        self.assertEqual(len(self.model.calls), 3)  # New JD only.
        self.request(dict(BACKEND, required_skills=["Go"]))
        self.assertEqual(len(self.model.calls), 4)  # Structured edits also change job text.
        self.request(dict(BACKEND, description=BACKEND["description"] + " Own APIs."))
        self.assertEqual(len(self.model.calls), 5)
        self.assertEqual(len(list((self.directory / "cache").glob("candidates_*.npy"))), 1)
        self.assertEqual(len(list((self.directory / "cache").glob("jd_*.npy"))), 4)

    def test_no_cache_bypasses_reads_and_writes_for_custom_jobs(self):
        ranking.rank_candidates(self.candidates, job=CustomJob(**BACKEND), model_factory=lambda:self.model,
                                as_of=date(2026, 11, 13), cache=False)
        self.assertEqual(len(self.model.calls), 2)
        self.assertFalse((self.directory / "cache").exists())

    def test_invalid_custom_inputs_rejected_before_dataset_read(self):
        invalid = [{}, dict(BACKEND, title="  "), dict(BACKEND, title=42), dict(BACKEND, title="---"),
                   dict(BACKEND, description="brief"), dict(BACKEND, required_skills="Java"),
                   dict(BACKEND, required_skills=[""]), dict(BACKEND, required_skills=["---"]), dict(BACKEND, required_skills=[42]),
                   dict(BACKEND, required_skills=["Java", "java"]),
                   dict(BACKEND, preferred_skills=["Java"]), dict(BACKEND, experience_min=-1),
                   dict(BACKEND, experience_min=True), dict(BACKEND, experience_min="3"),
                   dict(BACKEND, experience_min=11), dict(BACKEND, experience_max=81),
                   dict(BACKEND, location="Pune"), dict(BACKEND, required_skills=[str(i) for i in range(51)])]
        with patch.object(server, "get_candidates", side_effect=AssertionError("Dataset read before validation")):
            for job in invalid:
                with self.subTest(job=job):
                    response = self.request(job)
                    self.assertEqual(response.status_code, 422, response.text)
                    self.assertIn("job", response.json()["detail"][0]["loc"])
        for value in (float("nan"), float("inf")):
            with self.assertRaises(ValidationError):
                CustomJob(**dict(BACKEND, experience_min=value))

    def test_custom_config_immutable_and_metadata_cannot_mutate_default(self):
        job = CustomJob(**BACKEND)
        with self.assertRaises(ValidationError):
            job.title = "changed"
        self.assertIsInstance(job.required_skills, tuple)
        details = server.job_details(None)
        details["required_skills"].clear()
        self.assertTrue(get_jd()["must_have_skills"])

    def test_omitted_criteria_are_neutral_and_do_not_inherit_ai_preferences(self):
        job = CustomJob(title="Brand Designer", description=DESIGN["description"])
        candidate = copy.deepcopy(self.candidates[1])
        score = compute_custom_structured_score(candidate, job)
        for field in ("skill_score", "exp_score", "edu_score", "loc_score"):
            self.assertEqual(score[field], .5)
        changed = copy.deepcopy(candidate)
        changed["profile"].update(current_company="TCS", location="Pune", years_of_experience=22)
        changed["career_history"][0].update(company="Infosys", company_size="10001+")
        changed["education"] = [dict(tier="tier_1", field_of_study="Computer Science")]
        self.assertEqual(compute_custom_structured_score(changed, job), score)

    def test_one_sided_experience_and_range_edges(self):
        for bounds, expected in [({}, .5), ({"experience_min":6}, 1), ({"experience_min":7}, .5),
                                 ({"experience_max":6}, 1), ({"experience_max":5}, .7),
                                 ({"experience_min":6,"experience_max":6}, 1)]:
            job = CustomJob(title=DESIGN["title"], description=DESIGN["description"], **bounds)
            self.assertEqual(compute_custom_structured_score(self.candidates[0], job)["exp_score"], expected)

    def test_skill_matching_weights_empty_lists_and_boundaries(self):
        candidate = self.candidates[0]
        for required, preferred, expected in [(["Java"], [], 1), ([], ["Java"], 1),
            (["Java"], ["Figma"], .75), (["Figma"], ["Java"], .25), ([], [], .5)]:
            job = CustomJob(title="Engineer", description=BACKEND["description"],
                            required_skills=required, preferred_skills=preferred)
            self.assertEqual(compute_custom_structured_score(candidate, job)["skill_score"], expected)
        self.assertFalse(matches("Java", "JavaScript"))
        self.assertFalse(matches("R", "Engineer"))
        self.assertFalse(matches("C", "C++"))
        self.assertTrue(matches("C++", "Advanced C++"))
        self.assertTrue(matches("A/B testing", "A/B Testing"))

    def test_unrelated_assessments_do_not_change_custom_skill_score(self):
        candidate = copy.deepcopy(self.candidates[1])
        candidate["skills"].append(dict(name="Python", proficiency="expert"))
        candidate["redrob_signals"]["skill_assessment_scores"] = {"Python":10}
        job = CustomJob(**DESIGN)
        self.assertEqual(compute_custom_structured_score(candidate, job)["skill_score"], 1)
        candidate["redrob_signals"]["skill_assessment_scores"]["Figma"] = 10
        self.assertEqual(compute_custom_structured_score(candidate, job)["skill_score"], .85)

    def test_empty_custom_result_without_model(self):
        self.path.write_text("[]")
        with patch.object(server, "get_model", side_effect=AssertionError("Model loaded")):
            response = self.request(DESIGN)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"], [])
        self.assertEqual(response.json()["job"]["title"], DESIGN["title"])

    def test_custom_claude_prompt_blend_and_fallback(self):
        calls = []
        def create(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(content=[SimpleNamespace(text=json.dumps([
                dict(candidate_id=c["candidate_id"], score=80, reasoning="Fictional job-specific reason")
                for c in self.candidates]))])
        client = SimpleNamespace(messages=SimpleNamespace(create=create))
        job = CustomJob(**DESIGN)
        kwargs = dict(top_n=2, job=job, model_factory=lambda:self.model, as_of=date(2026,11,13))
        base = ranking.rank_candidates(self.candidates, **kwargs)
        with patch.object(llm_reranker, "get_client", return_value=client):
            actual = ranking.rank_candidates(self.candidates, **kwargs, use_llm=True, llm_n=2)
        by_id = {r["candidate"]["candidate_id"]:r["final_score"] for r in base}
        for row in actual:
            self.assertEqual(row["final_score"], round(by_id[row["candidate"]["candidate_id"]] * .6 + .8 * .4, 6))
        self.assertEqual(calls[0]["system"], llm_reranker.CUSTOM_SYSTEM_PROMPT)
        self.assertIn(job.embedding_text(), calls[0]["messages"][0]["content"])
        self.assertNotIn("Senior AI Engineer", calls[0]["messages"][0]["content"])
        with patch.object(llm_reranker, "get_client", return_value=client):
            llm_reranker.rerank_batch(copy.deepcopy(self.candidates))
        self.assertEqual(calls[-1]["system"], llm_reranker.SYSTEM_PROMPT)
        self.assertIn(llm_reranker.JD_RAW, calls[-1]["messages"][0]["content"])
        with patch.object(client.messages, "create", side_effect=RuntimeError("offline fallback")), \
             patch.object(llm_reranker, "get_client", return_value=client):
            fallback = ranking.rank_candidates(self.candidates, **kwargs, use_llm=True, llm_n=2)
        self.assertEqual([(r["candidate"]["candidate_id"],r["final_score"]) for r in fallback],
                         [(r["candidate"]["candidate_id"],r["final_score"]) for r in base])


if __name__ == "__main__":
    unittest.main()
