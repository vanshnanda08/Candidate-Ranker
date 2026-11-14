"""Offline regressions for shared ranking and CLI/HTTP boundaries."""
import ast
import copy
import csv
import io
import json
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import rank
import server
from pipeline import encoder, ranking, llm_reranker
from validate_submission import validate_submission, REQUIRED_HEADER
from test_embedding_cache import FakeEncoder


class RankingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.patch = patch.object(encoder, 'CACHE_DIR', self.directory / 'cache')
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.sample = json.loads((Path(__file__).resolve().parents[1] / 'sample_candidates.json').read_text())
        self.model = FakeEncoder()
        self.client = TestClient(server.app)

    def write_input(self, candidates, name='input.json'):
        path = self.directory / name
        path.write_text(json.dumps(candidates))
        return path

    def export(self, path, *options):
        output = self.directory / 'result.csv'
        with redirect_stdout(io.StringIO()), patch.object(ranking, 'load_model', return_value=self.model):
            rank.main(['--candidates', str(path), '--sample', '--out', str(output), *options])
        with output.open() as handle:
            return list(csv.DictReader(handle))

    def api(self, path, **limits):
        with patch.object(server, 'get_model', return_value=self.model):
            return self.client.post('/api/rank', json={'data_path': str(path), **limits})

    def assert_parity(self, cli, response):
        self.assertEqual(response.status_code, 200, response.text)
        api = response.json()['results']
        self.assertEqual([(r['candidate_id'], int(r['rank']), float(r['score']), r['reasoning']) for r in cli],
                         [(r['candidate_id'], r['rank'], r['display_score'], r['reasoning']) for r in api])

    def test_sample_cli_api_parity(self):
        path = self.write_input(self.sample)
        self.assert_parity(self.export(path, '--top-n', '20', '--no-llm', '--no-cache'),
                           self.api(path, top_n=20, use_llm=False))

    def test_empty_inputs_without_loading_model(self):
        for name, text, sample_flag in [('empty.json', '[]', True), ('empty.jsonl', '', False)]:
            with self.subTest(name=name):
                path = self.directory / name
                path.write_text(text)
                output = self.directory / 'empty.csv'
                with patch.object(ranking, 'load_model', side_effect=AssertionError('model loaded')), \
                     patch.object(server, 'get_model', side_effect=AssertionError('model loaded')), \
                     patch.object(ranking, 'rerank_batch', side_effect=AssertionError('Claude called')), \
                     redirect_stdout(io.StringIO()):
                    rank.main(['--candidates', str(path), '--out', str(output), *(['--sample'] if sample_flag else [])])
                    response = self.client.post('/api/rank', json={'data_path': str(path), 'is_sample': sample_flag, 'use_llm': True})
                with output.open() as handle:
                    self.assertEqual(list(csv.reader(handle)), [REQUIRED_HEADER])
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {'job': server.job_details(None), 'total_candidates': 0, 'top_n': 0, 'honeypots_in_top': 0,
                                                   'top_score': 0, 'results': []})

    def test_one_candidate_and_oversized_limits(self):
        path = self.write_input(self.sample[:1])
        cli = self.export(path, '--top-n', '999', '--coarse-n', '999', '--llm-n', '0')
        response = self.api(path, top_n=999, coarse_n=999, llm_n=0, use_llm=True)
        self.assert_parity(cli, response)
        self.assertEqual(len(cli), 1)
        self.assertEqual(float(cli[0]['score']), .2)

    def test_all_equal_scores_and_cutoffs_cli_api(self):
        candidates = []
        for cid in (5, 3, 4, 2, 1):
            candidate = copy.deepcopy(self.sample[0])
            candidate['candidate_id'] = f'CAND_{9_000_000 + cid:07d}'
            candidates.append(candidate)
        path = self.write_input(candidates)
        cli = self.export(path, '--top-n', '2', '--coarse-n', '3', '--no-llm')
        self.assert_parity(cli, self.api(path, top_n=2, coarse_n=3, use_llm=False))
        self.assertEqual([r['candidate_id'] for r in cli], ['CAND_9000001', 'CAND_9000002'])
        self.assertEqual([float(r['score']) for r in cli], [.2, .2])

    def test_semantic_ties_resolved_before_coarse_cutoff(self):
        candidates = [{'candidate_id': cid} for cid in ['D', 'C', 'B', 'A']]
        selected = ranking.select_shortlist(candidates, [.8, .9, .8, .8], 2)
        self.assertEqual([c['candidate_id'] for c, _ in selected], ['C', 'A'])
        self.assertEqual(ranking.select_shortlist(list(reversed(candidates)), [.8, .8, .9, .8], 2), selected)

    @staticmethod
    def row(cid, score):
        return {'candidate': {'candidate_id': cid}, 'final_score': score}

    def test_exact_raw_ties_at_final_cutoff(self):
        rows = [self.row('Z', .8), self.row('C', .5), self.row('A', .5), self.row('B', .5)]
        selected = ranking.select_and_normalize(rows, 3)
        self.assertEqual([r['candidate']['candidate_id'] for r in selected], ['Z', 'A', 'B'])
        self.assertEqual([r['display_score'] for r in selected], [.99, .2, .2])
        self.assertEqual([r['rank'] for r in selected], [1, 2, 3])

    def test_rounding_ties_reorder_only_after_raw_membership(self):
        rows = [self.row('Z', .9), self.row('H', .500002), self.row('B', .500001),
                self.row('A', .5), self.row('L', .1)]
        selected = ranking.select_and_normalize(rows, 3)
        self.assertEqual([r['candidate']['candidate_id'] for r in selected], ['Z', 'B', 'H'])
        self.assertEqual([r['display_score'] for r in selected], [.99, .2, .2])
        # A has the lowest ID but must not cross the raw top-N cutoff.
        self.assertNotIn('A', [r['candidate']['candidate_id'] for r in selected])
        self.assertEqual(ranking.select_and_normalize([], 1), [])

    def test_rounding_tie_cli_api_exports(self):
        scores = {9: .9, 8: .500002, 2: .500001, 1: .5, 3: .1}
        candidates = []
        for cid, score in scores.items():
            candidate = copy.deepcopy(self.sample[0])
            candidate['candidate_id'] = f'CAND_{9_000_000 + cid:07d}'
            candidate['_test_raw'] = score
            candidates.append(candidate)
        path = self.write_input(candidates)
        original = ranking.compute_structured_score
        def structured(candidate):
            return dict(original(candidate), test_raw=candidate['_test_raw'])
        with patch.object(ranking, 'compute_structured_score', side_effect=structured), \
             patch.object(ranking, 'compute_final_score', side_effect=lambda sem, st, beh, hp: st['test_raw']):
            cli = self.export(path, '--top-n', '3', '--no-llm')
            self.assert_parity(cli, self.api(path, top_n=3, use_llm=False))
        self.assertEqual([r['candidate_id'] for r in cli],
                         ['CAND_9000009', 'CAND_9000002', 'CAND_9000008'])

    def test_cli_invalid_limits(self):
        for option in ('--top-n', '--coarse-n', '--llm-n'):
            values = ['-1', '1.5', 'nope'] + ([] if option == '--llm-n' else ['0'])
            for value in values:
                with self.subTest(option=option, value=value), redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as error:
                        rank.parse_args(['--candidates', 'unused', option, value])
                    self.assertEqual(error.exception.code, 2)

    def test_api_invalid_limits_rejected_before_pipeline(self):
        with patch.object(server, 'get_candidates', side_effect=AssertionError('input read')):
            for field in ('top_n', 'coarse_n', 'llm_n'):
                values = [-1, 1.5, '2', True, None] + ([] if field == 'llm_n' else [0])
                for value in values:
                    with self.subTest(field=field, value=value):
                        self.assertEqual(self.client.post('/api/rank', json={field: value}).status_code, 422)

    def test_missing_and_malformed_inputs(self):
        missing = self.directory / 'missing.json'
        with redirect_stdout(io.StringIO()), self.assertRaisesRegex(SystemExit, 'Error:'):
            rank.main(['--candidates', str(missing), '--sample'])
        self.assertEqual(self.api(missing).status_code, 404)
        for text in ('not json', '{}', 'null', '[1]', '[{"candidate_id":"X"}]'):
            path = self.directory / 'bad.json'
            path.write_text(text)
            with self.subTest(text=text), redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(SystemExit, 'Error:'):
                    rank.main(['--candidates', str(path), '--sample'])
                self.assertEqual(self.api(path).status_code, 400)
        path = self.directory / 'bad.jsonl'
        path.write_text(json.dumps(self.sample[0]) + '\n{bad json\n')
        self.assertEqual(self.api(path, is_sample=False).status_code, 400)
        with self.assertRaisesRegex(SystemExit, 'Cannot read candidates'), redirect_stdout(io.StringIO()):
            rank.main(['--candidates', str(path)])
        candidate = copy.deepcopy(self.sample[0])
        candidate['skills'] = [{}]
        path = self.write_input([candidate])
        self.assertEqual(self.api(path).status_code, 400)
        with self.assertRaisesRegex(SystemExit, 'Malformed candidate'), redirect_stdout(io.StringIO()):
            self.export(path, '--no-llm')

    def test_zero_llm_pool_skips_integration(self):
        with patch.object(ranking, 'rerank_batch', side_effect=AssertionError('Claude called')):
            path = self.write_input(self.sample[:2])
            self.assert_parity(self.export(path, '--llm-n', '0'), self.api(path, use_llm=True, llm_n=0))

    def test_claude_blend_and_missing_score_fallback(self):
        candidates = copy.deepcopy(self.sample[:2])
        def stub(pool, batch_size):
            self.assertEqual(batch_size, 5)
            self.assertTrue(all('final_score' in c for c in pool))
            return [dict(pool[0], llm_score=.9, llm_reasoning='stub reasoning'), pool[1]]
        with patch.object(ranking, 'load_model', return_value=self.model):
            base = ranking.rank_candidates(candidates, use_llm=False, top_n=2)
            by_id = {r['candidate']['candidate_id']: r for r in base}
            with patch.object(ranking, 'rerank_batch', side_effect=stub):
                actual = ranking.rank_candidates(candidates, use_llm=True, top_n=2)
        for row in actual:
            original = by_id[row['candidate']['candidate_id']]['final_score']
            expected = round(.6 * original + .4 * .9, 6) if 'llm_score' in row else original
            self.assertEqual(row['final_score'], expected)
        self.assertTrue(any(r['candidate'].get('llm_reasoning') == 'stub reasoning' for r in actual))
        self.assertFalse(any('final_score' in c or 'llm_reasoning' in c for c in candidates))

    def test_claude_batch_failure_uses_base_score(self):
        # Exercise the actual rerank_batch fallback through the shared integration.
        class Client:
            class Messages:
                def create(self, **kwargs):
                    raise RuntimeError('offline stub failure')
            messages = Messages()
        with patch.object(ranking, 'load_model', return_value=self.model), \
             patch.object(llm_reranker, 'get_client', return_value=Client()):
            base = ranking.rank_candidates(self.sample[:2], use_llm=False, top_n=2)
            fallback = ranking.rank_candidates(self.sample[:2], use_llm=True, top_n=2)
        self.assertEqual([(r['candidate']['candidate_id'], r['final_score']) for r in base],
                         [(r['candidate']['candidate_id'], r['final_score']) for r in fallback])
        self.assertTrue(all('unavailable' in r['candidate']['llm_reasoning'] for r in fallback))

    def test_claude_stub_cli_api_parity(self):
        def stub(pool, batch_size):
            return [dict(c, llm_score=i / 10, llm_reasoning='stub') for i, c in enumerate(pool)]
        path = self.write_input(self.sample[:5])
        with patch.object(ranking, 'rerank_batch', side_effect=stub):
            self.assert_parity(self.export(path, '--top-n', '5', '--llm-n', '3'),
                               self.api(path, top_n=5, llm_n=3, use_llm=True))

    def test_validator_rejects_nonfinite_and_retains_format_checks(self):
        path = self.directory / 'submission.csv'
        def write(score, duplicate=False):
            with path.open('w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(REQUIRED_HEADER)
                for i in range(1, 101):
                    writer.writerow([f'CAND_{9_000_000 + (1 if duplicate else i):07d}', i,
                                     score if i == 1 else .2, 'test'])
        write(.99)
        self.assertEqual(validate_submission(path), [])
        for score in ('NaN', 'nan', 'inf', '-inf', 'Infinity', '1e999'):
            write(score)
            self.assertTrue(any('must be finite' in e for e in validate_submission(path)), score)
        write(.99, duplicate=True)
        self.assertTrue(any('duplicate candidate_id' in e for e in validate_submission(path)))
        path.write_text('bad,header\n')
        errors = validate_submission(path)
        self.assertTrue(any('header' in e for e in errors))
        self.assertTrue(any('exactly 100' in e for e in errors))

    def test_streamlit_imports_still_resolve_without_running_ui(self):
        source = Path(__file__).resolve().parents[1] / 'app.py'
        nodes = [n for n in ast.parse(source.read_text()).body if isinstance(n, (ast.Import, ast.ImportFrom))]
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), {})


if __name__ == '__main__':
    unittest.main()
