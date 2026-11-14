"""Controlled tests; no real result/label inspection needed for skill definitions."""
import copy
import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from benchmarks import grouped_skills as groups
from benchmarks.compare_grouped_skills import compare_rankings,followup_review
from pipeline import encoder,feature_scorer
from test_embedding_cache import FakeEncoder


def candidate(*skills,summary='',description=''):
    return {'profile':{'summary':summary},'skills':[{'name':s,'proficiency':'advanced'} for s in skills],
            'career_history':[{'description':description}] if description else [],'redrob_signals':{}}


class GroupScoringTests(unittest.TestCase):
    def test_equivalent_vector_alternatives_count_one(self):
        scores=[]
        for alternative in ('FAISS','Pinecone','Weaviate','Qdrant','Milvus','Elasticsearch','OpenSearch','pgvector'):
            c=candidate(alternative)
            core,_=groups.group_matches(c)
            self.assertEqual(core,['vector_or_hybrid'])
            scores.append(groups.score_skills(c)[0])
        self.assertEqual(len(set(scores)),1)
        documented=candidate(description='Designed hybrid search combining BM25 with dense vectors.')
        self.assertEqual(groups.group_matches(documented)[0],['vector_or_hybrid'])
        self.assertEqual(groups.score_skills(documented)[0],scores[0])

    def test_repeated_and_multiple_aliases_never_add_credit(self):
        one=candidate('FAISS','QLoRA','XGBoost')
        many=candidate('FAISS','FAISS','Pinecone','Qdrant','LoRA','QLoRA','PEFT','XGBoost','LightGBM','Learning to Rank')
        self.assertEqual(groups.group_matches(one),groups.group_matches(many))
        self.assertEqual(groups.score_skills(one),groups.score_skills(many))

    def test_unrelated_substrings_and_hybrid_work_do_not_match(self):
        c=candidate('Pineconeful','Pythonic','MRRobotics','roadmap','flora','QLoRAX',
                    summary='Owned a roadmap for hybrid working and carpet layouts.')
        self.assertEqual(groups.group_matches(c),([],[]))
        self.assertEqual(groups.score_skills(c)[0],0)

    def test_no_evidence_and_bare_python_or_metric_claims(self):
        self.assertEqual(groups.score_skills({}),(0,0,[]))
        self.assertEqual(groups.score_skills(candidate('Python','NDCG','MRR')),(0,0,[]))
        c=candidate(summary='Built a RAG side project using Python and FAISS; I have no professional ML experience.')
        self.assertEqual(groups.group_matches(c),([],[]))
        self.assertEqual(groups.group_matches(candidate(summary='I am interested in building Python search.')),([],[]))

    def test_embedding_families_and_system_types_are_alternatives(self):
        for tool in ('sentence-transformers','BGE','E5','OpenAI embeddings'):
            for system in ('search','ranking','recommendation'):
                c=candidate(description=f'Built production {system} with {tool}.')
                core,_=groups.group_matches(c)
                self.assertIn('production_embedding_retrieval',core)
                self.assertIn('shipped_ranking_search_or_recommendation',core)
        self.assertNotIn('production_embedding_retrieval',groups.group_matches(candidate('E5'))[0])

    def test_evaluation_alternatives_not_separate_requirements(self):
        for method in ('NDCG','MRR','MAP','A/B testing','A/B test','offline-to-online'):
            c=candidate(description=f'Designed ranking evaluation using {method}.')
            self.assertEqual(groups.group_matches(c)[0],['ranking_evaluation'])
        c=candidate(description='Designed ranking evaluation using NDCG, MRR, MAP and A/B testing.')
        self.assertEqual(groups.group_matches(c)[0],['ranking_evaluation'])

    def test_python_actions_and_open_source_contribution_require_evidence(self):
        c=candidate(description='Implemented Python ingestion tests for our API.')
        self.assertIn('python_engineering',groups.group_matches(c)[0])
        self.assertNotIn('ai_ml_open_source',groups.group_matches(candidate('PyTorch','TensorFlow'))[1])
        c=candidate(description='Contributed an open-source retrieval library.')
        self.assertIn('ai_ml_open_source',groups.group_matches(c)[1])

    def test_assessment_penalty_is_unchanged(self):
        c=candidate('FAISS','Python',description='Implemented Python services.')
        raw=groups.score_skills(c)[0]
        c['redrob_signals']['skill_assessment_scores']={'FAISS':39,'Python':20}
        self.assertAlmostEqual(groups.score_skills(c)[0],raw*.85*.85)
        c['redrob_signals']['skill_assessment_scores']={'FAISS':40}
        self.assertEqual(groups.score_skills(c)[0],raw)
        c['skills'][0]['proficiency']='intermediate'
        c['redrob_signals']['skill_assessment_scores']={'FAISS':0}
        self.assertEqual(groups.score_skills(c)[0],raw)

    def test_only_skill_derived_structured_fields_change_and_patches_restore(self):
        from pipeline.demo_data import demo_candidates
        # Explicit relevant fictional evidence; do not depend on sample row order.
        demo = demo_candidates()
        sample = [demo[4], demo[0], demo[1], demo[2]]
        original_function=feature_scorer.score_skills
        with tempfile.TemporaryDirectory() as tmp,patch.object(encoder,'CACHE_DIR',Path(tmp)):
            base,base_trace=groups.run_hybrid(sample,top_n=4,model_factory=FakeEncoder)
            variant,variant_trace=groups.run_hybrid(sample,top_n=4,experimental=True,model_factory=FakeEncoder)
        controlled=groups.verify_controlled_components(base_trace,variant_trace)
        self.assertEqual(controlled['shortlist_size'],4)
        self.assertTrue(controlled['non_skill_components_equal'])
        self.assertTrue(any(base_trace[cid]['structured']['skill_score']!=variant_trace[cid]['structured']['skill_score'] for cid in base_trace))
        self.assertIs(feature_scorer.score_skills,original_function)
        for row in variant:
            s=row['structured']
            expected=round(s['skill_score']*.35+s['career_score']*.35+s['exp_score']*.15+s['edu_score']*.05+s['loc_score']*.10,4)
            # Existing scorer uses unrounded skill internally; allow its 4-decimal output precision.
            self.assertAlmostEqual(s['structured_score'],expected,places=3)
        with self.assertRaises(RuntimeError):
            groups.run_hybrid(sample,top_n=4,experimental=True,model_factory=lambda:(_ for _ in ()).throw(RuntimeError('fixture failure')))
        self.assertIs(feature_scorer.score_skills,original_function)

    def test_control_checker_rejects_other_component_or_shortlist_changes(self):
        base={'fictional':{'structured':{'career_score':1,'exp_score':1,'edu_score':1,'loc_score':1},'behavioral':{'x':1},'honeypot':(1,[])}}
        changed=copy.deepcopy(base);changed['fictional']['structured']['career_score']=0
        with self.assertRaises(ValueError):groups.verify_controlled_components(base,changed)
        with self.assertRaises(ValueError):groups.verify_controlled_components(base,{})


class ComparisonTests(unittest.TestCase):
    def test_common_judged_pool_and_unknown_not_zero_at_cutoffs(self):
        ids=[f'F-{i}' for i in range(30)]
        ranks={'keyword_only':ids[:20],'current_hybrid':ids[:20],'grouped_hybrid':ids[10:30]}
        grades={cid:'2' for cid in ids[:20]}
        report=compare_rankings(ranks,grades)
        self.assertEqual(report['methods']['current_hybrid']['10']['pooled_ndcg'],1)
        self.assertEqual(report['methods']['current_hybrid']['20']['pooled_ndcg'],1)
        self.assertEqual(report['methods']['grouped_hybrid']['10']['pooled_ndcg'],1)
        self.assertIsNone(report['methods']['grouped_hybrid']['20']['pooled_ndcg'])
        self.assertEqual(report['methods']['grouped_hybrid']['20']['missing_count'],10)
        self.assertEqual(report['overlap']['current_hybrid vs grouped_hybrid'],{'10':0,'20':10})
        for name in ranks:
            self.assertEqual(report['methods'][name]['20']['ideal_dcg'],report['methods']['keyword_only']['20']['ideal_dcg'])
        grades[ids[0]]='0';zero=compare_rankings(ranks,grades)
        self.assertEqual(zero['methods']['current_hybrid']['10']['judged_count'],10)
        self.assertIsNotNone(zero['methods']['current_hybrid']['10']['pooled_ndcg'])
        grades[ids[0]]='U';unknown=compare_rankings(ranks,grades)
        self.assertIsNone(unknown['methods']['current_hybrid']['10']['pooled_ndcg'])
        self.assertEqual(unknown['methods']['current_hybrid']['10']['U_count'],1)
        zeros=compare_rankings(ranks,{cid:'0' for cid in ids})
        self.assertTrue(all(method['10']['pooled_ndcg'] is None for method in zeros['methods'].values()))

    def test_blinded_followup_contains_only_unknown_union_and_preserves_labels(self):
        sample=json.loads((Path(__file__).resolve().parents[1]/'sample_candidates.json').read_text())[:4]
        by_id={c['candidate_id']:c for c in sample};ids=list(by_id)
        rankings={'keyword_only':ids[:3],'current_hybrid':ids[1:],'grouped_hybrid':ids[::-1]}
        grades={ids[0]:'0',ids[1]:'2'}
        with tempfile.TemporaryDirectory() as tmp:
            result=followup_review(by_id,rankings,grades,dataset_sha='fictional',seed=7,output=tmp,provenance={'fixture':True})
            self.assertEqual(result['additional_judgments_needed'],2)
            path=Path(result['reviewer_csv']);before=path.read_bytes()
            with path.open() as handle:rows=list(csv.DictReader(handle))
            self.assertTrue(all(r['relevance_grade']==r['reason']=='' for r in rows))
            self.assertFalse(any(k in rows[0] for k in ('candidate_id','rank','score','selection_methods')))
            followup_review(by_id,rankings,grades,dataset_sha='fictional',seed=7,output=tmp,provenance={'fixture':True})
            self.assertEqual(path.read_bytes(),before)
            rows[0].update(relevance_grade='1',reason='Fictional confirmed note')
            with path.open('w',newline='') as handle:
                writer=csv.DictWriter(handle,fieldnames=rows[0]);writer.writeheader();writer.writerows(rows)
            followup_review(by_id,rankings,grades,dataset_sha='fictional',seed=7,output=tmp,provenance={'fixture':True})
            with path.open() as handle:saved=list(csv.DictReader(handle))
            self.assertEqual(saved[0]['reason'],'Fictional confirmed note')
            self.assertEqual(saved[0]['relevance_grade'],'1')


if __name__=='__main__':unittest.main()
