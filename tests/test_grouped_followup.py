"""Fictional combined-pool fixtures; no real review labels/manifests are opened."""
import copy
import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

from benchmarks import evaluate_grouped_followup as followup
from benchmarks.evaluate_review_set import canonical,sha256


def fixture():
    dataset='fictional-dataset-fingerprint'
    def entries(start,count):
        rows=[];pool=[]
        for i in range(start,start+count):
            cid=f'fictional-{i}'
            rid='R-'+hashlib.sha256(canonical(['talentlens-review-v1',dataset,cid]).encode()).hexdigest()[:16]
            rows.append({'review_id':rid,'evidence':f'Fictional profile {i}','relevance_grade':'','reason':''})
            pool.append({'review_id':rid,'candidate_id':cid})
        return rows,pool
    original,pool=entries(0,50);new,newpool=entries(50,21)
    oldids=[e['candidate_id'] for e in pool];newids=[e['candidate_id'] for e in newpool]
    rankings={'keyword_only':oldids[:10]+newids[:10],
              'current_hybrid':oldids[10:20]+newids[10:20],
              'grouped_hybrid':oldids[:10]+newids[:9]+newids[20:]}
    oldmanifest={'dataset':{'sha256':dataset},'pool':pool}
    newmanifest={'dataset_sha256':dataset,'pool':newpool,'top20':copy.deepcopy(rankings),
                 'evidence_sha256':hashlib.sha256(canonical(new).encode()).hexdigest()}
    labeled=[dict(row,relevance_grade='2',reason='User-confirmed fictional evidence') for row in original]
    newlabeled=[dict(row,relevance_grade='1',reason='User-confirmed fictional evidence') for row in new]
    return [original,labeled,oldmanifest,new,newlabeled,newmanifest,rankings]


def write_csv(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=rows[0]);writer.writeheader();writer.writerows(rows)


class CombinedPoolTests(unittest.TestCase):
    def test_complete_pool_same_ideal_coverage_and_deltas(self):
        data=fixture();data[4][0]['relevance_grade']='3'
        report=followup.evaluate_combined(*data,require_complete=True)
        self.assertEqual(report['combined_pool_size'],71)
        self.assertEqual(report['judged_pool_size'],71)
        self.assertEqual(report['reviewed_count'],71)
        self.assertEqual(report['grade_counts'],{'0':0,'1':20,'2':50,'3':1,'U':0,'blank':0})
        for cutoff in ('10','20'):
            methods=report['methods']
            self.assertTrue(all(m[cutoff]['judged_coverage']==1 for m in methods.values()))
            self.assertEqual(len({m[cutoff]['ideal_dcg'] for m in methods.values()}),1)
            delta=methods['grouped_hybrid'][cutoff]['pooled_ndcg']-methods['current_hybrid'][cutoff]['pooled_ndcg']
            self.assertAlmostEqual(report['grouped_change_from_current'][cutoff]['pooled_ndcg_change'],delta)
        self.assertGreater(report['grouped_change_from_current']['20']['pooled_ndcg_change'],0)
        # A newly judged grade 3 changes the ideal for every method, including ones
        # whose top ten contain only old judgments; do not reuse the old 50-pool ideal.
        self.assertLess(report['methods']['current_hybrid']['10']['pooled_ndcg'],1)

    def test_partial_followup_keeps_blanks_unknown_and_completion_gate_fails(self):
        data=fixture()
        for row in data[4][5:]:row.update(relevance_grade='',reason='')
        report=followup.evaluate_combined(*data)
        self.assertEqual(report['combined_pool_size'],71)
        self.assertEqual(report['judged_pool_size'],55)
        self.assertEqual(report['grade_counts']['blank'],16)
        self.assertIsNone(report['methods']['current_hybrid']['20']['pooled_ndcg'])
        self.assertIsNone(report['grouped_change_from_current']['20']['pooled_ndcg_change'])
        with self.assertRaisesRegex(ValueError,'incomplete'):
            followup.evaluate_combined(*data,require_complete=True)

    def test_U_is_completed_but_unknown_and_zero_is_judged(self):
        data=fixture()
        for mapping in (data[5]['top20'],data[6]):
            mapping['grouped_hybrid'][0],mapping['grouped_hybrid'][10]=mapping['grouped_hybrid'][10],mapping['grouped_hybrid'][0]
        data[4][0]['relevance_grade']='U'
        report=followup.evaluate_combined(*data,require_complete=True)
        self.assertEqual(report['reviewed_count'],71)
        self.assertEqual(report['judged_pool_size'],70)
        self.assertEqual(report['methods']['grouped_hybrid']['10']['U_count'],1)
        self.assertIsNone(report['grouped_change_from_current']['10']['pooled_ndcg_change'])
        data[4][0]['relevance_grade']='0'
        report=followup.evaluate_combined(*data,require_complete=True)
        self.assertEqual(report['judged_pool_size'],71)
        self.assertEqual(report['methods']['grouped_hybrid']['10']['judged_coverage'],1)
        self.assertIsNotNone(report['grouped_change_from_current']['10']['pooled_ndcg_change'])

    def test_overlapping_review_and_candidate_ids_are_rejected(self):
        data=fixture();rid=data[0][0]['review_id']
        data[3][0]['review_id']=rid;data[4][0]['review_id']=rid;data[5]['pool'][0]['review_id']=rid
        with self.assertRaisesRegex(ValueError,'Overlapping review IDs'):followup.combine_labels(*data)
        data=fixture();data[5]['pool'][0]['candidate_id']=data[2]['pool'][0]['candidate_id']
        with self.assertRaisesRegex(ValueError,'Overlapping candidate IDs'):followup.combine_labels(*data)

    def test_duplicate_unknown_or_edited_followup_rows_fail(self):
        for kind in ('duplicate','unknown','evidence','invalid_grade','no_reason'):
            data=fixture()
            if kind=='duplicate':data[4][1]=dict(data[4][0])
            elif kind=='unknown':data[4][0]['review_id']='unknown'
            elif kind=='evidence':data[4][0]['evidence']='edited'
            elif kind=='invalid_grade':data[4][0]['relevance_grade']='4'
            elif kind=='no_reason':data[4][0]['reason']=''
            with self.subTest(kind=kind),self.assertRaises(ValueError):followup.combine_labels(*data)

    def test_manifest_dataset_rankings_and_unknown_union_are_validated(self):
        for kind in ('dataset','order','mapping','pool','evidence_hash'):
            data=fixture()
            if kind=='dataset':data[5]['dataset_sha256']='wrong'
            elif kind=='order':data[5]['top20']['current_hybrid'].reverse()
            elif kind=='mapping':data[5]['pool'][0]['review_id']='wrong'
            elif kind=='pool':data[6]['current_hybrid'][-1]='outsider';data[5]['top20']=copy.deepcopy(data[6])
            elif kind=='evidence_hash':data[5]['evidence_sha256']='wrong'
            with self.subTest(kind=kind),self.assertRaises(ValueError):followup.combine_labels(*data)

    def test_label_file_order_does_not_change_join(self):
        data=fixture();expected=followup.evaluate_combined(*data,require_complete=True)
        data[1].reverse();data[4].reverse()
        self.assertEqual(followup.evaluate_combined(*data,require_complete=True),expected)

    def test_zero_ideal_leaves_all_metrics_and_delta_unavailable(self):
        data=fixture()
        for row in data[1]+data[4]:row['relevance_grade']='0'
        report=followup.evaluate_combined(*data,require_complete=True)
        self.assertTrue(all(m['10']['pooled_ndcg'] is None and m['20']['pooled_ndcg'] is None for m in report['methods'].values()))
        self.assertEqual(report['grouped_change_from_current']['20']['unavailable_reasons'],['ideal_gain_is_zero'])

    def test_partial_or_missing_followup_cli_never_opens_real_manifests(self):
        data=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);frozen=root/'frozen';experiment=root/'experiment'
            write_csv(frozen/'reviewer.csv',data[0]);write_csv(frozen/'reviewer_labeled.csv',data[1])
            write_csv(experiment/'followup/reviewer.csv',data[3])
            for present in (False,True):
                path=experiment/'followup/reviewer_labeled.csv'
                if present:
                    partial=copy.deepcopy(data[4]);partial[-1].update(relevance_grade='',reason='')
                    write_csv(path,partial)
                with redirect_stderr(io.StringIO()) as errors,patch.object(followup.json,'loads',side_effect=AssertionError('manifest opened')):
                    with self.assertRaises(SystemExit) as error:
                        followup.main(['--frozen-dir',str(frozen),'--experiment-dir',str(experiment),'--followup-labels',str(path)])
                self.assertEqual(error.exception.code,2)
                self.assertIn('Review incomplete',errors.getvalue())


class ArtifactVerificationTests(unittest.TestCase):
    def test_fictional_phase4_artifacts_integrity_and_cross_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'source';experiment=Path(tmp)/'experiment'
            (root/'benchmarks').mkdir(parents=True);(experiment/'followup').mkdir(parents=True)
            (root/'benchmarks/grouped_skills_spec.json').write_text('{"fictional":true}')
            (root/'benchmarks/SKILL_GROUP_EXPERIMENT.md').write_text('Fictional fixed protocol')
            (root/'benchmarks/frozen_runner.py').write_text('# Fictional frozen code\n')
            spec=sha256(root/'benchmarks/grouped_skills_spec.json')
            data=fixture();manifest=data[5]
            manifest.update(format_version='skill-groups-followup-v1',seed=123,
                provenance={'as_of':'2026-11-13','spec_sha256':spec,'frozen_manifest_sha256':'frozen-phase3-manifest','frozen_labels_sha256':'old-labels'})
            artifacts={'comparison.json':{'as_of':'2026-11-13','claude_enabled':False,'spec_sha256':spec,
                          'frozen_benchmark_verification':{'manifest_sha256':'frozen-phase3-manifest'}},
                       'private_rankings.json':{'rankings':data[6]},'followup/manifest.json':manifest}
            for name,value in artifacts.items():(experiment/name).write_text(json.dumps(value))
            write_csv(experiment/'followup/reviewer.csv',data[3])
            plan={'as_of':'2026-11-13','settings':{'coarse_n':500,'use_llm':False,'llm_n':0,'top_n':[10,20]},
                  'source_sha256':{'benchmarks/frozen_runner.py':sha256(root/'benchmarks/frozen_runner.py')},'spec_sha256':spec}
            prereg={'spec_sha256':spec,'protocol_sha256':sha256(root/'benchmarks/SKILL_GROUP_EXPERIMENT.md'),
                    'specification':{'followup_seed':123}}
            (experiment/'execution_plan.json').write_text(json.dumps(plan))
            (experiment/'preregistration.json').write_text(json.dumps(prereg))
            names=[*artifacts,'followup/reviewer.csv']
            def freeze():
                (experiment/'verification.json').write_text(json.dumps({'file_sha256':{p:sha256(experiment/p) for p in names}}))
            def verify():return followup.verify_phase4_artifacts(root,experiment,data[2],'old-labels')
            freeze();self.assertEqual(verify()[2]['status'],'verified')
            for name in names:
                path=experiment/name;before=path.read_bytes();path.write_bytes(b'changed')
                with self.subTest(name=name),self.assertRaisesRegex(ValueError,'fingerprint'):verify()
                path.write_bytes(before)
            for field in ('dataset','provenance','rankings'):
                changed=copy.deepcopy(manifest)
                if field=='dataset':changed['dataset_sha256']='wrong'
                elif field=='provenance':changed['provenance']['as_of']='2026-11-14'
                elif field=='rankings':changed['top20']['current_hybrid'].reverse()
                (experiment/'followup/manifest.json').write_text(json.dumps(changed));freeze()
                with self.subTest(field=field),self.assertRaises(ValueError):verify()
                (experiment/'followup/manifest.json').write_text(json.dumps(manifest));freeze()
            path=root/'benchmarks/frozen_runner.py';path.write_text('changed code')
            with self.assertRaisesRegex(ValueError,'source changed'):verify()


if __name__=='__main__':unittest.main()
