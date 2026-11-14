"""Fictional fixtures only: no real manifest, labels or ranking identities."""
import copy
import csv
import hashlib
import io
import json
import math
from contextlib import redirect_stderr
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from benchmarks import evaluate_review_set as evaluation
from benchmarks import review_labels as labels


def fixture():
    original = [{'review_id': f'F-{i:02}', 'evidence': f'Fictional evidence {i}',
                 'relevance_grade': '', 'reason': ''} for i in range(12)]
    labeled = [dict(row, relevance_grade=str(3 - min(i // 3, 3)), reason='Fictional confirmed reason')
               for i, row in enumerate(original)]
    candidates = [f'fictional-candidate-{i}' for i in range(12)]
    methods = {'hybrid_top10': candidates[:10], 'semantic_top10': list(reversed(candidates[:10])),
               'keyword_top10': candidates[2:12]}
    manifest = {'pool': [{'review_id': row['review_id'], 'candidate_id': cid}
                         for row, cid in zip(original, candidates)], 'top10': methods,
                'method_rankings': {name: [{'candidate_id': cid} for cid in methods[key]]
                                    for key, name in evaluation.METHODS.items()}}
    return original, labeled, manifest


def write_csv(path, rows):
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


class LabelValidationTests(unittest.TestCase):
    def setUp(self):
        self.original, self.labeled, self.manifest = fixture()
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.source = self.directory / 'reviewer.csv'
        self.saved = self.directory / 'reviewer_labeled.csv'
        write_csv(self.source, self.original)

    def test_valid_labels_and_missing_labels_remain_distinct(self):
        valid = labels.validate_labels(self.original, self.labeled, require_complete=True)
        self.assertEqual(len(valid), 12)
        valid = labels.validate_labels(self.original, self.original)
        self.assertTrue(all(r['relevance_grade'] == '' for r in valid.values()))
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            labels.validate_labels(self.original, self.original, require_complete=True)

    def test_reject_invalid_grades_or_reason_pairs(self):
        for grade in ('4', '-1', 'u', 'NaN', '2.0', ' 2 ', 2, None):
            changed = copy.deepcopy(self.labeled); changed[0]['relevance_grade'] = grade
            with self.subTest(grade=grade), self.assertRaises(ValueError):
                labels.validate_labels(self.original, changed)
        for grade, reason in [('2', ''), ('U', '  '), ('', 'unconfirmed note')]:
            changed = copy.deepcopy(self.labeled); changed[0].update(relevance_grade=grade, reason=reason)
            with self.assertRaises(ValueError): labels.validate_labels(self.original, changed)

    def test_reject_missing_duplicate_unknown_ids_and_edited_evidence(self):
        variants = [self.labeled[:-1], self.labeled + [self.labeled[0]]]
        unknown = copy.deepcopy(self.labeled); unknown[0]['review_id'] = 'unknown'; variants.append(unknown)
        edited = copy.deepcopy(self.labeled); edited[0]['evidence'] = 'edited'; variants.append(edited)
        extra = copy.deepcopy(self.labeled); extra[0]['extra_column'] = 'extra'; variants.append(extra)
        for changed in variants:
            with self.assertRaises(ValueError): labels.validate_labels(self.original, changed)
        with self.assertRaises(ValueError): labels.validate_labels(self.original + [self.original[0]], self.labeled)
        with self.assertRaises(ValueError): labels.validate_labels(self.original, self.labeled, expected_count=50)

    def test_save_only_confirmations_preserve_original_and_resume(self):
        before = self.source.read_bytes()
        confirm = {'review_id': 'F-00', 'relevance_grade': 'U', 'reason': 'Not enough fictional evidence'}
        self.assertFalse(self.saved.exists())
        self.assertEqual(labels.save_confirmed(self.source, self.saved, [confirm]), 1)
        self.assertEqual(self.source.read_bytes(), before)
        _, rows = labels.read_csv(self.saved)
        self.assertEqual(rows[0]['relevance_grade'], 'U')
        self.assertTrue(all(not r['relevance_grade'] for r in rows[1:]))
        self.assertEqual(labels.next_batch(self.source, self.saved)[0]['review_id'], 'F-01')
        self.assertEqual(labels.save_confirmed(self.source, self.saved, [confirm]), 1)
        self.assertEqual(labels.save_confirmed(self.source, self.saved,
            [{'review_id': 'F-01', 'relevance_grade': '0', 'reason': 'Documented fictional gap'}]), 2)
        _, rows = labels.read_csv(self.saved)
        self.assertEqual(rows[0]['relevance_grade'], 'U')
        self.assertEqual(rows[1]['relevance_grade'], '0')
        write_csv(self.saved, list(reversed(rows)))
        self.assertEqual(labels.next_batch(self.source, self.saved)[0]['review_id'], 'F-02')

    def test_failed_confirmation_batches_do_not_write_or_overwrite(self):
        good = {'review_id': 'F-00', 'relevance_grade': '2', 'reason': 'Confirmed fictional reason'}
        for updates in ([], [dict(good, review_id='unknown')], [good, good],
                        [good, dict(good, review_id='F-01', relevance_grade='4')]):
            with self.assertRaises(ValueError): labels.save_confirmed(self.source, self.saved, updates)
            self.assertFalse(self.saved.exists())
        labels.save_confirmed(self.source, self.saved, [good]); before = self.saved.read_bytes()
        with self.assertRaisesRegex(ValueError, 'already confirmed'):
            labels.save_confirmed(self.source, self.saved, [dict(good, relevance_grade='1')])
        self.assertEqual(self.saved.read_bytes(), before)
        with self.assertRaises(ValueError): labels.save_confirmed(self.source, self.source, [good])

    def test_csv_headers_and_width_validation(self):
        for content in ('review_id,relevance_grade,reason,reason\nx,1,a,b\n',
                        'review_id,relevance_grade,reason\nx,1\n',
                        'review_id,relevance_grade,reason\nx,1,a,b\n'):
            self.saved.write_text(content)
            with self.assertRaises(ValueError): labels.read_csv(self.saved)


class MetricTests(unittest.TestCase):
    def setUp(self): self.original, self.labeled, self.manifest = fixture()

    def test_hand_calculated_ndcg_and_perfect_order(self):
        report = evaluation.evaluate(self.original, self.labeled, self.manifest, require_complete=True)
        ideal = sum((2 ** int(r['relevance_grade']) - 1) / math.log2(i + 2)
                    for i, r in enumerate(self.labeled[:10]))
        reversed_dcg = sum((2 ** int(r['relevance_grade']) - 1) / math.log2(i + 2)
                           for i, r in enumerate(reversed(self.labeled[:10])))
        self.assertAlmostEqual(report['ideal_dcg_at_10'], ideal)
        self.assertEqual(report['methods']['hybrid_top10']['pooled_ndcg_at_10'], 1)
        self.assertAlmostEqual(report['methods']['semantic_top10']['pooled_ndcg_at_10'], reversed_dcg / ideal)
        self.assertTrue(all(r['judged_coverage'] == 1 for r in report['methods'].values()))

    def test_join_is_by_review_id_not_csv_row_order(self):
        expected = evaluation.evaluate(self.original, self.labeled, self.manifest)
        actual = evaluation.evaluate(self.original, list(reversed(self.labeled)), self.manifest)
        self.assertEqual(actual, expected)
        self.assertEqual(evaluation.dcg([0, 0, 0]), 0)

    def test_U_is_unknown_but_zero_is_judged(self):
        self.labeled[0]['relevance_grade'] = 'U'
        report = evaluation.evaluate(self.original, self.labeled, self.manifest, require_complete=True)
        method = report['methods']['hybrid_top10']
        self.assertIsNone(method['pooled_ndcg_at_10'])
        self.assertEqual(method['judged_count'], 9)
        self.assertEqual(method['judged_coverage'], .9)
        self.assertEqual(method['U_count'], 1)
        self.assertEqual(report['grade_counts']['U'], 1)
        self.labeled[0]['relevance_grade'] = '0'
        changed = evaluation.evaluate(self.original, self.labeled, self.manifest)
        self.assertEqual(changed['methods']['hybrid_top10']['judged_coverage'], 1)
        self.assertIsNotNone(changed['methods']['hybrid_top10']['pooled_ndcg_at_10'])

    def test_blank_top10_is_unjudged_and_real_completion_gate_rejects_it(self):
        self.labeled[0].update(relevance_grade='', reason='')
        report = evaluation.evaluate(self.original, self.labeled, self.manifest)
        self.assertIsNone(report['methods']['hybrid_top10']['pooled_ndcg_at_10'])
        self.assertEqual(report['methods']['hybrid_top10']['blank_count'], 1)
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            evaluation.evaluate(self.original, self.labeled, self.manifest, require_complete=True)

    def test_U_outside_method_top10_is_excluded_from_ideal_not_mapped_to_zero(self):
        self.labeled[-1].update(relevance_grade='U', reason='Fictional unknown')
        report = evaluation.evaluate(self.original, self.labeled, self.manifest)
        self.assertEqual(report['numeric_judged_pool_size'], 11)
        self.assertIsNotNone(report['methods']['hybrid_top10']['pooled_ndcg_at_10'])
        self.assertIsNone(report['methods']['keyword_top10']['pooled_ndcg_at_10'])

    def test_zero_ideal_and_all_U_make_metrics_unavailable(self):
        for grade in ('0', 'U'):
            labeled = [dict(r, relevance_grade=grade, reason='Fictional reason') for r in self.labeled]
            report = evaluation.evaluate(self.original, labeled, self.manifest)
            self.assertEqual(report['ideal_dcg_at_10'], 0)
            self.assertTrue(all(r['pooled_ndcg_at_10'] is None for r in report['methods'].values()))
            self.assertTrue(all('ideal_gain_is_zero' in r['unavailable_reasons'] for r in report['methods'].values()))
            self.assertEqual(report['methods']['hybrid_top10']['judged_count'], 10 if grade == '0' else 0)

    def test_known_relevant_outside_top10_contributes_to_pool_ideal(self):
        for r in self.labeled: r['relevance_grade'] = '0'
        self.labeled[-1]['relevance_grade'] = '3'
        report = evaluation.evaluate(self.original, self.labeled, self.manifest)
        self.assertEqual(report['ideal_dcg_at_10'], 7)
        self.assertEqual(report['methods']['hybrid_top10']['pooled_ndcg_at_10'], 0)
        self.assertGreater(report['methods']['keyword_top10']['pooled_ndcg_at_10'], 0)

    def test_invalid_manifest_joins_and_ranking_orders_fail(self):
        for change in ('duplicate_review', 'duplicate_candidate', 'missing_pool', 'unknown_candidate',
                       'duplicate_top10', 'short_top10', 'inconsistent_order', 'missing_method'):
            manifest = copy.deepcopy(self.manifest)
            if change == 'duplicate_review': manifest['pool'][1]['review_id'] = manifest['pool'][0]['review_id']
            elif change == 'duplicate_candidate': manifest['pool'][1]['candidate_id'] = manifest['pool'][0]['candidate_id']
            elif change == 'missing_pool': manifest['pool'].pop()
            elif change == 'unknown_candidate': manifest['top10']['hybrid_top10'][0] = 'unknown'
            elif change == 'duplicate_top10': manifest['top10']['hybrid_top10'][1] = manifest['top10']['hybrid_top10'][0]
            elif change == 'short_top10': manifest['top10']['hybrid_top10'].pop()
            elif change == 'inconsistent_order': manifest['method_rankings']['hybrid'].reverse()
            elif change == 'missing_method': manifest['top10'].pop('hybrid_top10')
            with self.subTest(change=change), self.assertRaises(ValueError):
                evaluation.evaluate(self.original, self.labeled, manifest)

    def test_incomplete_cli_does_not_open_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            original = [{'review_id': f'F-{i}', 'evidence': 'fictional', 'relevance_grade': '', 'reason': ''} for i in range(50)]
            write_csv(folder/'original.csv', original); write_csv(folder/'labeled.csv', original)
            with redirect_stderr(io.StringIO()) as errors, patch.object(evaluation.json, 'loads', side_effect=AssertionError('manifest accessed')):
                with self.assertRaises(SystemExit) as result:
                    evaluation.main(['--original', str(folder/'original.csv'), '--labels', str(folder/'labeled.csv'),
                                     '--manifest', str(folder/'absent.json'), '--verification', str(folder/'absent-verification.json')])
            self.assertEqual(result.exception.code, 2)
            self.assertIn('Review incomplete', errors.getvalue())


class FrozenInputTests(unittest.TestCase):
    def test_fixture_input_integrity_and_failures_without_real_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root/'pipeline').mkdir()
            (root/'pipeline/encoder.py').write_text("MODEL_NAME = 'fictional-encoder'\nMODEL_REVISION = 'fictional-revision'\n")
            (root/'dataset.jsonl').write_text('{"fictional":true}\n')
            (root/'cache.npy').write_bytes(b'fictional frozen cache bytes')
            original, _, manifest = fixture()
            dataset_sha = evaluation.sha256(root/'dataset.jsonl')
            for entry, row in zip(manifest['pool'], original):
                rid = 'R-' + hashlib.sha256(evaluation.canonical(['talentlens-review-v1', dataset_sha, entry['candidate_id']]).encode()).hexdigest()[:16]
                entry['review_id'] = row['review_id'] = rid
            manifest.update(format_version=1, as_of='2026-11-13',
                dataset={'path': str(root/'dataset.jsonl'), 'sha256': dataset_sha, 'records': 100000},
                ranker_settings={'hybrid_top_n':10, 'coarse_n':500, 'llm_n':0, 'use_llm':False, 'cache':True},
                model={'name':'fictional-encoder', 'revision':'fictional-revision', 'dimension':384},
                jd={'raw':'Fictional JD', 'sha256':hashlib.sha256(b'Fictional JD').hexdigest()},
                source_sha256={'pipeline/encoder.py':evaluation.sha256(root/'pipeline/encoder.py')},
                cache={'fictional':{'path':str(root/'cache.npy'), 'sha256':evaluation.sha256(root/'cache.npy'), 'status':'verified_hit'}},
                evidence_sha256=hashlib.sha256(evaluation.canonical(original).encode()).hexdigest())
            original_path=root/'original.csv'; write_csv(original_path,original)
            manifest_path=root/'manifest.json'; reference_path=root/'verification.json'
            def freeze(current):
                manifest_path.write_text(json.dumps(current))
                reference_path.write_text(json.dumps({'manifest_sha256':evaluation.sha256(manifest_path),'reviewer_sha256':evaluation.sha256(original_path)}))
            def verify(current):
                return evaluation.verify_benchmark(current,original,root=root,manifest_path=manifest_path,verification_path=reference_path,original_path=original_path)
            freeze(manifest)
            self.assertEqual(verify(manifest)['status'], 'verified')
            for field in ('date','settings','model','jd','evidence','mapping'):
                changed=copy.deepcopy(manifest)
                if field=='date': changed['as_of']='2026-11-14'
                elif field=='settings': changed['ranker_settings']['use_llm']=True
                elif field=='model': changed['model']['revision']='changed'
                elif field=='jd': changed['jd']['raw']='changed'
                elif field=='evidence': changed['evidence_sha256']='changed'
                elif field=='mapping': changed['pool'][0]['review_id']='changed'
                freeze(changed)
                with self.subTest(field=field),self.assertRaises(ValueError): verify(changed)
            freeze(manifest); manifest_path.write_text('tampered manifest')
            with self.assertRaisesRegex(ValueError,'manifest fingerprint'):verify(manifest)
            freeze(manifest)
            for path in (root/'dataset.jsonl',root/'cache.npy',root/'pipeline/encoder.py',original_path):
                before=path.read_bytes();path.write_bytes(b'changed')
                with self.subTest(path=path.name),self.assertRaises(ValueError):verify(manifest)
                path.write_bytes(before)


if __name__ == '__main__': unittest.main()
