"""Offline pool composition, blinding, deterministic output and label retention."""
import copy
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import numpy as np
from benchmarks import build_review_set as review
from pipeline import encoder


class ReviewSetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.sample = json.loads((Path(__file__).resolve().parents[1] / 'sample_candidates.json').read_text())[0]

    def test_pool_covers_all_top10_cutoff_and_outside_sample(self):
        semantic = [f'CAND_{9_000_000 + i:07d}' for i in range(1, 101)]
        top = {'hybrid_top10': semantic[10:20], 'semantic_top10': semantic[:10], 'keyword_top10': semantic[25:35]}
        ids, sources, near = review.select_pool(semantic, top, seed=42, coarse_n=20)
        self.assertEqual(len(ids), 50)
        self.assertEqual(len(set(ids)), 50)
        self.assertTrue(all(set(values) <= set(ids) for values in top.values()))
        self.assertEqual(near, semantic[15:25])
        self.assertTrue(all('semantic_cutoff' in sources[cid] for cid in near))
        random_ids = [cid for cid in ids if 'outside_random' in sources[cid]]
        self.assertTrue(random_ids)
        self.assertTrue(all(cid not in semantic[:20] for cid in random_ids))
        self.assertEqual((ids, sources, near), review.select_pool(semantic, top, seed=42, coarse_n=20))
        self.assertNotEqual(ids, review.select_pool(semantic, top, seed=43, coarse_n=20)[0])

    def test_ids_are_stable_opaque_and_unique(self):
        ids = [review.review_id('dataset', str(i)) for i in range(100)]
        self.assertEqual(len(set(ids)), 100)
        self.assertEqual(ids, [review.review_id('dataset', str(i)) for i in range(100)])
        self.assertNotEqual(ids[0], review.review_id('changed dataset', '0'))
        self.assertTrue(all(len(r) == 18 and r.startswith('R-') for r in ids))

    def test_keyword_alternatives_repetition_and_word_boundaries(self):
        candidate = copy.deepcopy(self.sample)
        candidate['profile'].update(headline='', summary='Python FAISS E5 MRR deployed search', current_title='')
        candidate['career_history'] = []; candidate['skills'] = []
        self.assertEqual(review.keyword_score(candidate), 5)
        candidate['profile']['summary'] += ' Python Python Pinecone Qdrant MAP NDCG MRR E5'
        self.assertEqual(review.keyword_score(candidate), 5)
        candidate['profile']['summary'] = 'roadmap pythonic'
        self.assertEqual(review.keyword_score(candidate), 0)
        candidate['profile']['summary'] = 'Python hybrid search semantic search A/B testing shipped search'
        self.assertEqual(review.keyword_score(candidate), 5)

    def test_reviewer_fields_are_blinded_and_labels_blank(self):
        candidate = copy.deepcopy(self.sample)
        name = candidate['profile']['anonymized_name']
        company = candidate['profile']['current_company']
        cid = candidate['candidate_id']
        candidate['profile']['summary'] = f'{name} at {company}; {cid}; user@example.com https://example.org +91 98765 43210 production retrieval'
        row = review.evidence_row(candidate, 'dataset')
        self.assertEqual(list(row), review.FIELDS)
        self.assertEqual(row['relevance_grade'], '')
        self.assertEqual(row['reason'], '')
        text = json.dumps(row)
        for forbidden in (name, company, cid, 'user@example.com', 'https://example.org', '98765'):
            self.assertNotIn(forbidden, text)
        for forbidden in ('anonymized_name', 'recruiter_response_rate', 'profile_views', 'institution', 'tier', 'selection_methods', 'final_score'):
            self.assertNotIn(forbidden, text)
        self.assertIn('production retrieval', text)
        self.assertEqual(review.scrub('2026-11-13', candidate), '2026-11-13')
        self.assertEqual(review.safe_cell('=2+3'), "'=2+3")

    def test_reruns_preserve_labels_and_manifest_exactly(self):
        row = review.evidence_row(self.sample, 'dataset')
        manifest = {'seed': 1, 'input': 'same'}
        csv_path, manifest_path = review.write_review_files(self.directory, [row], manifest)
        original = csv_path.read_bytes()
        review.write_review_files(self.directory, [row], manifest)
        self.assertEqual(csv_path.read_bytes(), original)
        edited = dict(row, relevance_grade='2', reason='Human evidence note, with comma\nand newline')
        with csv_path.open('w', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=review.FIELDS); writer.writeheader(); writer.writerow(edited)
        manifest_before = manifest_path.read_bytes()
        review.write_review_files(self.directory, [row], manifest)
        with csv_path.open(newline='') as handle: actual = next(csv.DictReader(handle))
        self.assertEqual(actual, edited)
        self.assertEqual(manifest_path.read_bytes(), manifest_before)
        before = csv_path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'configuration changed'):
            review.write_review_files(self.directory, [row], {'seed': 2})
        self.assertEqual(csv_path.read_bytes(), before)

    def test_existing_evidence_or_bad_ids_are_not_overwritten(self):
        row = review.evidence_row(self.sample, 'dataset')
        csv_path, _ = review.write_review_files(self.directory, [row], {'seed': 1})
        for field, value in [('summary', 'edited evidence'), ('review_id', 'unknown'), ('relevance_grade', '4')]:
            edited = dict(row, **{field: value})
            with csv_path.open('w', newline='') as handle:
                writer = csv.DictWriter(handle, fieldnames=review.FIELDS); writer.writeheader(); writer.writerow(edited)
            before = csv_path.read_bytes()
            with self.assertRaises(ValueError): review.write_review_files(self.directory, [row], {'seed': 1})
            self.assertEqual(csv_path.read_bytes(), before)

    def test_verified_cache_only_never_encodes_or_writes(self):
        candidates = [self.sample]
        with patch.object(encoder, 'CACHE_DIR', self.directory / 'cache'), redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, 'Stop and diagnose'):
                review.verified_embeddings(candidates)
            self.assertFalse(encoder.CACHE_DIR.exists())
            model = review.VerifiedCacheIdentity()
            with self.assertRaisesRegex(RuntimeError, 'Fresh encoding prohibited'): model.encode(['text'])
            candidate_path = encoder._cache_path('candidates', model,
                ([c['candidate_id'], encoder.build_candidate_text(c)] for c in candidates))
            jd_path = encoder._cache_path('jd', model, [review.get_jd_text_for_embedding()])
            encoder.CACHE_DIR.mkdir()
            np.save(candidate_path, np.ones((1, 384), dtype=np.float32))
            np.save(jd_path, np.ones(384, dtype=np.float32))
            before = {p.name: p.read_bytes() for p in encoder.CACHE_DIR.iterdir()}
            arrays, paths = review.verified_embeddings(candidates)
            self.assertEqual(arrays['candidates'].shape, (1, 384))
            self.assertEqual(before, {p.name: p.read_bytes() for p in encoder.CACHE_DIR.iterdir()})
            np.save(candidate_path, np.zeros((2, 384), dtype=np.float32))
            with self.assertRaisesRegex(RuntimeError, 'Stop and diagnose'): review.verified_embeddings(candidates)


if __name__ == '__main__':
    unittest.main()
