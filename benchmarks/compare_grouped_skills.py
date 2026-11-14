"""Cache-only, single-component experiment against the frozen review benchmark."""
import argparse
from datetime import date
from itertools import combinations
import json
from pathlib import Path
import time

from benchmarks import build_review_set as review
from benchmarks import evaluate_review_set as evaluation
from benchmarks.review_labels import read_csv, validate_labels
from benchmarks.grouped_skills import (SPEC, SPEC_PATH, run_hybrid,
                                        verify_controlled_components)
from pipeline import ranking


def compare_rankings(rankings, grades):
    """Use one numeric judged pool for every method/cutoff; unknown is not zero."""
    known = [int(grade) for grade in grades.values() if grade in ('0','1','2','3')]
    report = {'judged_pool_size': len(known), 'gain':'2^grade - 1',
              'ideal_pool':'same original judged pool for every method and cutoff',
              'cutoff_definition':'prefixes of reported top-20 lists', 'methods':{}, 'overlap':{}}
    for method, ids in rankings.items():
        if len(ids) != 20 or len(set(ids)) != 20:
            raise ValueError('Each method must supply 20 unique ordered IDs')
        report['methods'][method] = {}
        for k in (10,20):
            top = [grades.get(cid) for cid in ids[:k]]
            judged = sum(g in ('0','1','2','3') for g in top)
            ideal = evaluation.dcg(sorted(known, reverse=True)[:k])
            reasons = []
            if judged != k: reasons.append('cutoff_contains_unjudged_or_U')
            if ideal == 0: reasons.append('ideal_gain_is_zero')
            report['methods'][method][str(k)] = {
                'judged_count':judged, 'cutoff':k, 'judged_coverage':judged/k,
                'missing_count':sum(g is None or g == '' for g in top), 'U_count':top.count('U'),
                'pooled_ndcg':None if reasons else evaluation.dcg(top)/ideal,
                'unavailable_reasons':reasons, 'ideal_dcg':ideal}
    for first, second in combinations(rankings,2):
        report['overlap'][first+' vs '+second] = {
            str(k):len(set(rankings[first][:k]) & set(rankings[second][:k])) for k in (10,20)}
    return report


def followup_review(candidates_by_id, rankings, grades, *, dataset_sha, seed,
                    output, provenance):
    union = set().union(*(set(ids) for ids in rankings.values()))
    unknown = [cid for cid in union if grades.get(cid) not in ('0','1','2','3')]
    unknown.sort(key=lambda cid:(review.priority(seed,'skill-groups-followup-v1',cid),cid))
    if not unknown:
        return {'additional_judgments_needed':0,'reviewer_csv':None}
    rows = [review.evidence_row(candidates_by_id[cid],dataset_sha) for cid in unknown]
    manifest = {'format_version':'skill-groups-followup-v1','seed':seed,'dataset_sha256':dataset_sha,
                'provenance':provenance, 'top20':rankings,
                'pool':[{'review_id':review.review_id(dataset_sha,cid),'candidate_id':cid,
                         'selection_methods':[name for name,ids in rankings.items() if cid in ids]}
                        for cid in unknown],
                'existing_U_count':sum(grades.get(cid)=='U' for cid in unknown),
                'rubric':'unchanged benchmarks/labeling_rubric.md',
                'shuffle':'SHA256([seed, skill-groups-followup-v1, candidate_id])',
                'evidence_sha256':review.digest(review.canonical(rows))}
    csv_path, manifest_path = review.write_review_files(Path(output)/'followup',rows,manifest)
    return {'additional_judgments_needed':len(unknown), 'reviewer_csv':str(csv_path),
            'manifest':str(manifest_path), 'union_size':len(union)}


def run(args):
    start = time.perf_counter()
    root = Path(__file__).resolve().parents[1]
    frozen, output = Path(args.frozen_dir).resolve(), Path(args.output_dir).resolve()
    if output == root or root in output.parents or output == frozen or frozen in output.parents:
        raise ValueError('Experiment output must be outside the project and frozen benchmark folder')
    output.mkdir(parents=True,exist_ok=True,mode=0o700)
    prereg = json.loads((output/'preregistration.json').read_text())
    if review.file_sha(SPEC_PATH) != prereg['spec_sha256'] or review.file_sha(root/'benchmarks/SKILL_GROUP_EXPERIMENT.md') != prereg['protocol_sha256']:
        raise ValueError('Pre-registered specification/protocol changed; create an explicit new experiment version')
    code = ['benchmarks/grouped_skills.py','benchmarks/compare_grouped_skills.py',
            'tests/test_grouped_skills.py']
    plan = {'spec_sha256':prereg['spec_sha256'], 'as_of':'2026-11-13',
            'frozen_dir':str(frozen),'source_sha256':{p:review.file_sha(root/p) for p in code},
            'settings':{'coarse_n':500,'use_llm':False,'llm_n':0,'top_n':[10,20]}}
    plan_path = output/'execution_plan.json'
    if plan_path.exists() and json.loads(plan_path.read_text()) != plan:
        raise ValueError('Experiment code/settings changed; use a new registered version')
    review.atomic_write(plan_path,json.dumps(plan,indent=2)+'\n')
    print('Pre-registration and code plan verified before reading labels or comparison results.',flush=True)
    _, original = read_csv(frozen/'reviewer.csv')
    _, labeled = read_csv(frozen/'reviewer_labeled.csv')
    labels = validate_labels(original,labeled,require_complete=True,expected_count=50)
    manifest = json.loads((frozen/'manifest.json').read_text())
    frozen_check = evaluation.verify_benchmark(manifest,original,root=root,
        manifest_path=frozen/'manifest.json',verification_path=frozen/'verification.json',
        original_path=frozen/'reviewer.csv')
    completed = json.loads((frozen/'phase3b_completion_verification.json').read_text())
    if review.file_sha(frozen/'reviewer_labeled.csv') != completed['file_sha256']['reviewer_labeled.csv']:
        raise ValueError('Confirmed labels differ from frozen Phase 3B')
    candidates = ranking.load_ranking_input(manifest['dataset']['path'],False)
    arrays, cache_paths = review.verified_embeddings(candidates)
    del arrays  # Subsequent shared-ranker calls verify/read the same cache identities.
    baseline10, baseline10_trace = run_hybrid(candidates,top_n=10)
    expected10 = manifest['method_rankings']['hybrid']
    actual10 = [{'candidate_id':r['candidate']['candidate_id'],'display_score':r['display_score']} for r in baseline10]
    if actual10 != expected10:
        raise ValueError('Frozen hybrid top 10 did not reproduce exactly; stop before variant comparison')
    print('Frozen hybrid top 10 IDs/order/display scores reproduced exactly.',flush=True)
    baseline20, baseline_trace = run_hybrid(candidates,top_n=20)
    variant20, variant_trace = run_hybrid(candidates,top_n=20,experimental=True)
    controls = verify_controlled_components(baseline_trace,variant_trace)
    if list(baseline10_trace) != list(baseline_trace):
        raise ValueError('Baseline shortlist differs between requested cutoffs')
    keywords = sorted(((c['candidate_id'],review.keyword_score(c)) for c in candidates),
                      key=lambda pair:(-pair[1],pair[0]))
    if [cid for cid,_ in keywords[:10]] != manifest['top10']['keyword_top10']:
        raise ValueError('Frozen keyword baseline failed reproduction')
    rankings = {'keyword_only':[cid for cid,_ in keywords[:20]],
                'current_hybrid':[r['candidate']['candidate_id'] for r in baseline20],
                'grouped_hybrid':[r['candidate']['candidate_id'] for r in variant20]}
    grades = {entry['candidate_id']:labels[entry['review_id']]['relevance_grade'] for entry in manifest['pool']}
    aggregates = compare_rankings(rankings,grades)
    aggregates.update({'frozen_benchmark_verification':frozen_check,
        'baseline_reproduction':{'hybrid_top10_ids_order_display_scores_equal':True,'keyword_top10_equal':True},
        'controls':controls,'production_unchanged':True,
        'top_n_normalization_check':{
            'baseline_standalone_10_equals_prefix_20':actual10==[{'candidate_id':r['candidate']['candidate_id'],'display_score':r['display_score']} for r in baseline20[:10]],
            'baseline_standalone_10_ids_equal_prefix_20':rankings['current_hybrid'][:10]==manifest['top10']['hybrid_top10'],
            'variant_standalone_10_ids_equal_prefix_20':rankings['grouped_hybrid'][:10]==[r['candidate']['candidate_id'] for r in ranking.select_and_normalize(variant20,10)]},
        'as_of':'2026-11-13','claude_enabled':False,'spec_sha256':prereg['spec_sha256'],
        'cache':{key:{'path':str(path),'sha256':review.file_sha(path),'status':'verified_hit'} for key,path in cache_paths.items()},
        'label_provenance':'AI-assisted and user-confirmed; original 50 labels unchanged'})
    aggregates['followup'] = followup_review({c['candidate_id']:c for c in candidates},rankings,grades,
        dataset_sha=manifest['dataset']['sha256'],seed=SPEC['followup_seed'],output=output,
        provenance={'spec_sha256':prereg['spec_sha256'],'frozen_manifest_sha256':frozen_check['manifest_sha256'],
                    'frozen_labels_sha256':review.file_sha(frozen/'reviewer_labeled.csv'),'as_of':'2026-11-13'})
    # Individual rankings/components are local audit artifacts, not reviewer evidence.
    audit = {'rankings':rankings,'hybrid_top10_reproduction':actual10,
             'keyword_top20_scores':keywords[:20],
             'current_top20':[{'candidate_id':r['candidate']['candidate_id'],'display_score':r['display_score'],'raw_score':r['final_score']} for r in baseline20],
             'grouped_top20':[{'candidate_id':r['candidate']['candidate_id'],'display_score':r['display_score'],'raw_score':r['final_score']} for r in variant20],
             'all_shortlist_components':{'current':baseline_trace,'grouped':variant_trace}}
    review.atomic_write(output/'private_rankings.json',json.dumps(audit,indent=2)+'\n')
    review.atomic_write(output/'comparison.json',json.dumps(aggregates,indent=2,allow_nan=False)+'\n')
    review.atomic_write(output/'runtime.json',json.dumps({'wall_seconds':round(time.perf_counter()-start,3)})+'\n')
    print(json.dumps(aggregates,indent=2,allow_nan=False))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frozen-dir',required=True)
    parser.add_argument('--output-dir',required=True)
    args = parser.parse_args(argv)
    run(args)


if __name__ == '__main__': main()
