"""Offline upload/schema/content-identity and aggregate-only API regressions."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import server
from pipeline import datasets, encoder
from pipeline.demo_data import four_candidates
from test_embedding_cache import FakeEncoder


class DatasetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        for target, value in [("DATASET_DIR", self.directory / "uploads")]:
            p = patch.object(datasets, target, value); p.start(); self.addCleanup(p.stop)
        p = patch.object(encoder, "CACHE_DIR", self.directory / "cache"); p.start(); self.addCleanup(p.stop)
        self.client = TestClient(server.app)

    def upload(self, rows, filename="profiles.json"):
        raw = rows if isinstance(rows, bytes) else json.dumps(rows).encode()
        return self.client.post("/api/datasets", files={"file": (filename, raw, "application/json")})

    def test_demo_count_without_model_and_valid_upload_roundtrip(self):
        with patch.object(server, "get_model", side_effect=AssertionError("model loaded during validation")):
            demo = self.client.get("/api/datasets/demo")
            self.assertEqual(demo.status_code, 200); self.assertEqual(demo.json()["profile_count"], 50)
            info = self.upload(four_candidates()).json()
        self.assertEqual(info["profile_count"], 4)
        self.assertRegex(info["dataset_id"], r"^upload_[0-9a-f]{64}$")
        self.assertEqual(self.client.get('/api/datasets/'+info['dataset_id']).json()['fingerprint'], info['fingerprint'])
        with patch.object(server, "get_model", return_value=FakeEncoder()):
            response = self.client.post('/api/rank', json={'dataset_id':info['dataset_id'],'use_llm':False,'as_of':'2026-11-13'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['dataset']['fingerprint'],info['fingerprint'])
        self.assertEqual(response.json()['total_candidates'],4)

    def test_same_name_different_content_and_formatting_identity(self):
        rows = four_candidates()
        first = self.upload(rows).json()
        formatted = self.upload(json.dumps(rows, indent=4, sort_keys=True).encode(), filename='renamed.json').json()
        self.assertEqual(first['dataset_id'],formatted['dataset_id'])
        rows[0]['profile']['summary'] += ' Changed profile evidence.'
        second = self.upload(rows).json()
        self.assertNotEqual(first['fingerprint'],second['fingerprint'])

    def test_validated_content_roundtrip_is_idempotent(self):
        first=self.upload(four_candidates()).json()
        contents=(self.directory/'uploads'/f"{first['dataset_id']}.json").read_bytes()
        second=self.upload(contents,filename='renamed.json').json()
        self.assertEqual(first['dataset_id'],second['dataset_id'])

    def test_invalid_json_schema_duplicates_and_nonfinite_values(self):
        bad = [b'not JSON', b'{}', b'[]', b'[1]', b'[{"candidate_id":"x"}]', b'[{"x":1e999}]', b'[{"x":1,"x":2}]']
        for change in [lambda r:r[0]['skills'].append({}),
                       lambda r:r[0]['profile'].update(years_of_experience=True),
                       lambda r:r[0]['profile'].update(years_of_experience=float('nan')),
                       lambda r:r[0].update(redrob_signals={'recruiter_response_rate':'many'}),
                       lambda r:r[0]['career_history'][0].update(description=None),
                       lambda r:r.append(copy.deepcopy(r[0]))]:
            rows=four_candidates();change(rows);bad.append(json.dumps(rows).encode())
        with patch.object(server,'get_model',side_effect=AssertionError('model loaded')):
            for raw in bad:
                self.assertEqual(self.upload(raw).status_code,422)
        self.assertFalse((self.directory/'uploads').exists())

    def test_size_count_extension_and_unknown_identifiers(self):
        with patch.object(server,'MAX_UPLOAD_BYTES',10):
            self.assertEqual(self.upload(b' '*11).status_code,413)
        self.assertEqual(self.upload(four_candidates(),filename='bad.txt').status_code,422)
        with patch.object(datasets,'MAX_PROFILES',2):
            self.assertEqual(self.upload(four_candidates()).status_code,422)
        for value in ['unknown','upload_'+'a'*64,'../outside']:
            response=self.client.post('/api/rank',json={'dataset_id':value})
            self.assertEqual(response.status_code,404)

    def test_tampered_stored_upload_is_rejected(self):
        info=self.upload(four_candidates()).json()
        (self.directory/'uploads'/f"{info['dataset_id']}.json").write_text('[]')
        self.assertEqual(self.client.get('/api/datasets/'+info['dataset_id']).status_code,400)

    def test_upload_storage_failure_is_actionable(self):
        with patch.object(server, 'store_upload', side_effect=OSError('disk full')):
            response=self.upload(four_candidates())
        self.assertEqual(response.status_code,503);self.assertIn('disk space',response.json()['detail'])

    def test_aggregate_report_has_no_individual_records(self):
        report=self.client.get('/api/benchmarks').json()
        self.assertEqual(report['pool_size'],71)
        self.assertEqual(report['methods']['current_hybrid']['20']['pooled_ndcg'],.9744102412230781)
        self.assertTrue(all(row['10']['pooled_ndcg']==1 for row in report['methods'].values()))
        self.assertNotIn('candidate_id',json.dumps(report));self.assertNotIn('review_id',json.dumps(report))


if __name__=='__main__':unittest.main()
