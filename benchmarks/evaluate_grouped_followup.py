"""Evaluate frozen Phase 4A runs after all follow-up reviews are confirmed."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from benchmarks.compare_grouped_skills import compare_rankings
from benchmarks.evaluate_review_set import canonical,sha256,verify_benchmark
from benchmarks.review_labels import read_csv,validate_labels

METHODS = {'keyword_only','current_hybrid','grouped_hybrid'}
DATE = '2026-11-13'


def _pool_mapping(original, manifest):
    by_review, by_candidate = {}, {}
    for entry in manifest.get('pool', []):
        rid,cid = entry['review_id'],entry['candidate_id']
        if not rid or not cid or rid in by_review or cid in by_candidate:
            raise ValueError('Missing or duplicate manifest IDs')
        by_review[rid]=cid;by_candidate[cid]=rid
    if set(by_review)!={row['review_id'] for row in original} or len(by_review)!=len(original):
        raise ValueError('Reviewer IDs do not match manifest pool')
    return by_review,by_candidate


def combine_labels(original, labeled, original_manifest, follow_original, follow_labeled,
                   follow_manifest, rankings, *, require_complete=False, expected_counts=(50,21)):
    """Validate and join both pools by ID; blank/U remain distinct from numeric 0."""
    first=validate_labels(original,labeled,require_complete=True,expected_count=expected_counts[0])
    second=validate_labels(follow_original,follow_labeled,require_complete=require_complete,expected_count=expected_counts[1])
    if set(first)&set(second):
        raise ValueError('Overlapping review IDs across label sets')
    first_mapping,first_candidates=_pool_mapping(original,original_manifest)
    second_mapping,second_candidates=_pool_mapping(follow_original,follow_manifest)
    if set(first_candidates)&set(second_candidates):
        raise ValueError('Overlapping candidate IDs across label sets')
    if original_manifest['dataset']['sha256']!=follow_manifest['dataset_sha256']:
        raise ValueError('Follow-up dataset fingerprint mismatch')
    if follow_manifest['top20']!=rankings:
        raise ValueError('Follow-up rankings differ from frozen Phase 4A rankings')
    if set(rankings)!=METHODS or any(len(ids)!=20 or len(set(ids))!=20 for ids in rankings.values()):
        raise ValueError('Expected exactly three frozen top-20 lists with unique IDs')
    union=set().union(*(set(ids) for ids in rankings.values()))
    if set(second_candidates)!=union-set(first_candidates):
        raise ValueError('Follow-up pool is not exactly the unknown frozen top-20 union')
    if [row['review_id'] for row in follow_original]!=[entry['review_id'] for entry in follow_manifest['pool']]:
        raise ValueError('Follow-up evidence order differs from its frozen manifest')
    blank=[dict(row,relevance_grade='',reason='') for row in follow_original]
    if hashlib.sha256(canonical(blank).encode()).hexdigest()!=follow_manifest['evidence_sha256']:
        raise ValueError('Follow-up evidence fingerprint mismatch')
    dataset_sha=original_manifest['dataset']['sha256']
    for rid,cid in {**first_mapping,**second_mapping}.items():
        expected='R-'+hashlib.sha256(canonical(['talentlens-review-v1',dataset_sha,cid]).encode()).hexdigest()[:16]
        if rid!=expected:raise ValueError('Stable review ID mapping mismatch')
    grades={cid:first[rid]['relevance_grade'] for rid,cid in first_mapping.items()}
    grades.update({cid:second[rid]['relevance_grade'] for rid,cid in second_mapping.items()})
    assert len(grades)==sum(expected_counts)
    if not union<=set(grades):raise ValueError('A frozen ranking candidate is absent from the combined pool')
    return grades


def evaluate_combined(original, labeled, original_manifest, follow_original, follow_labeled,
                      follow_manifest, rankings, *, require_complete=False, expected_counts=(50,21)):
    grades=combine_labels(original,labeled,original_manifest,follow_original,follow_labeled,
                          follow_manifest,rankings,require_complete=require_complete,expected_counts=expected_counts)
    report=compare_rankings(rankings,grades)
    report['ideal_pool']='same combined numeric judged pool for every method and cutoff; U/blank excluded, never mapped to 0'
    counts=Counter(grade or 'blank' for grade in grades.values())
    report['grade_counts']={grade:counts[grade] for grade in ('0','1','2','3','U','blank')}
    report['combined_pool_size']=len(grades)
    report['reviewed_count']=sum(bool(grade) for grade in grades.values())
    report['grouped_change_from_current']={}
    for cutoff in ('10','20'):
        current=report['methods']['current_hybrid'][cutoff]
        grouped=report['methods']['grouped_hybrid'][cutoff]
        available=current['pooled_ndcg'] is not None and grouped['pooled_ndcg'] is not None
        report['grouped_change_from_current'][cutoff]={
            'pooled_ndcg_change':grouped['pooled_ndcg']-current['pooled_ndcg'] if available else None,
            'judged_coverage_change':grouped['judged_coverage']-current['judged_coverage'],
            'unavailable_reasons':[] if available else sorted(set(current['unavailable_reasons']+grouped['unavailable_reasons']))}
    report['as_of']=DATE
    report['label_provenance']='AI-assisted and user-confirmed'
    report['scope']='one-role pooled pilot; frozen Phase 4A rankings, no reranking, training or inference'
    return report


def verify_phase4_artifacts(root, experiment, original_manifest, frozen_labels_sha):
    """Read frozen artifacts only after completion; verify bytes and cross-links."""
    root,experiment=Path(root).resolve(),Path(experiment).resolve()
    audit=json.loads((experiment/'verification.json').read_text())
    required={'comparison.json','private_rankings.json','followup/reviewer.csv','followup/manifest.json'}
    if not required<=set(audit['file_sha256']):raise ValueError('Incomplete Phase 4A integrity anchor')
    for relative in required:
        path=(experiment/relative).resolve()
        if not path.is_relative_to(experiment) or sha256(path)!=audit['file_sha256'][relative]:
            raise ValueError(f'Frozen Phase 4A artifact fingerprint mismatch: {relative}')
    plan=json.loads((experiment/'execution_plan.json').read_text())
    prereg=json.loads((experiment/'preregistration.json').read_text())
    expected_settings={'coarse_n':500,'use_llm':False,'llm_n':0,'top_n':[10,20]}
    if plan['as_of']!=DATE or plan['settings']!=expected_settings:
        raise ValueError('Phase 4A scoring date/settings changed')
    for relative,digest in plan['source_sha256'].items():
        path=(root/relative).resolve()
        if not path.is_relative_to(root) or sha256(path)!=digest:
            raise ValueError(f'Frozen Phase 4A source changed: {relative}')
    spec_sha=sha256(root/'benchmarks/grouped_skills_spec.json')
    if spec_sha!=plan['spec_sha256'] or spec_sha!=prereg['spec_sha256']:
        raise ValueError('Phase 4A skill specification changed')
    if sha256(root/'benchmarks/SKILL_GROUP_EXPERIMENT.md')!=prereg['protocol_sha256']:
        raise ValueError('Phase 4A protocol changed')
    manifest=json.loads((experiment/'followup/manifest.json').read_text())
    private=json.loads((experiment/'private_rankings.json').read_text())
    comparison=json.loads((experiment/'comparison.json').read_text())
    if comparison['as_of']!=DATE or comparison['claude_enabled'] is not False or comparison['spec_sha256']!=spec_sha:
        raise ValueError('Frozen comparison settings differ')
    if manifest['format_version']!='skill-groups-followup-v1' or manifest['top20']!=private['rankings']:
        raise ValueError('Follow-up manifest differs from frozen rankings')
    if manifest['dataset_sha256']!=original_manifest['dataset']['sha256']:
        raise ValueError('Follow-up dataset fingerprint mismatch')
    provenance=manifest['provenance']
    if (provenance['as_of']!=DATE or provenance['spec_sha256']!=spec_sha or
        provenance['frozen_manifest_sha256']!=comparison['frozen_benchmark_verification']['manifest_sha256'] or
        provenance['frozen_labels_sha256']!=frozen_labels_sha):
        raise ValueError('Follow-up provenance mismatch')
    if manifest['seed']!=prereg['specification']['followup_seed']:
        raise ValueError('Follow-up shuffle seed mismatch')
    return manifest,private['rankings'],{'status':'verified','as_of':DATE,'skill_spec_sha256':spec_sha,
                                         'frozen_rankings':True,'model_inference':False}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frozen-dir',required=True,help='Frozen Phase 3A/3B folder')
    parser.add_argument('--experiment-dir',required=True,help='Frozen Phase 4A folder')
    parser.add_argument('--followup-labels',required=True)
    args=parser.parse_args(argv)
    frozen,experiment=Path(args.frozen_dir),Path(args.experiment_dir)
    root=Path(__file__).resolve().parents[1]
    try:
        original_fields,original=read_csv(frozen/'reviewer.csv')
        fields,labeled=read_csv(frozen/'reviewer_labeled.csv')
        follow_fields,follow_original=read_csv(experiment/'followup/reviewer.csv')
        if Path(args.followup_labels).exists():
            saved_fields,follow_labeled=read_csv(args.followup_labels)
        else:
            saved_fields=follow_fields
            follow_labeled=[dict(row,relevance_grade='',reason='') for row in follow_original]
        if original_fields!=fields or follow_fields!=saved_fields or original_fields!=follow_fields:
            raise ValueError('Label file columns differ from original reviewer schema')
        validate_labels(original,labeled,require_complete=True,expected_count=50)
        # This gate precedes all real manifests, ranking files and aggregate output.
        validate_labels(follow_original,follow_labeled,require_complete=True,expected_count=21)
        manifest=json.loads((frozen/'manifest.json').read_text())
        verification=verify_benchmark(manifest,original,root=root,manifest_path=frozen/'manifest.json',
            verification_path=frozen/'verification.json',original_path=frozen/'reviewer.csv')
        completion=json.loads((frozen/'phase3b_completion_verification.json').read_text())
        label_sha=sha256(frozen/'reviewer_labeled.csv')
        if label_sha!=completion['file_sha256']['reviewer_labeled.csv']:
            raise ValueError('Frozen Phase 3B labels changed')
        follow_manifest,rankings,phase4check=verify_phase4_artifacts(root,experiment,manifest,label_sha)
        report=evaluate_combined(original,labeled,manifest,follow_original,follow_labeled,
                                 follow_manifest,rankings,require_complete=True)
        report['verification']={'phase3':verification,'phase4':phase4check}
    except (OSError,ValueError,KeyError) as exc:
        parser.error(str(exc))
    print(json.dumps(report,indent=2,allow_nan=False))


if __name__=='__main__':main()
