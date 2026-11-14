"""Offline pooled NDCG@10 from frozen runs; real evaluation waits for all labels."""
import argparse
import ast
from collections import Counter
import hashlib
import json
import math
from pathlib import Path

from benchmarks.review_labels import read_csv, validate_labels

METHODS = {'keyword_top10': 'keyword', 'semantic_top10': 'semantic', 'hybrid_top10': 'hybrid'}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def sha256(path):
    hasher = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            hasher.update(block)
    return hasher.hexdigest()


def frozen_methods(manifest, original):
    """Join each frozen method to anonymous IDs; never rerank or use method scores."""
    pool = manifest.get('pool', [])
    review_ids, candidates = set(), {}
    for entry in pool:
        rid, cid = entry['review_id'], entry['candidate_id']
        if not rid or not cid or rid in review_ids or cid in candidates:
            raise ValueError('Manifest pool has missing/duplicate IDs')
        review_ids.add(rid)
        candidates[cid] = rid
    if review_ids != {row['review_id'] for row in original} or len(pool) != len(original):
        raise ValueError('Manifest and reviewer pools differ')
    if set(manifest.get('top10', {})) != set(METHODS):
        raise ValueError('Expected exactly the three frozen Phase 3A methods')
    result = {}
    for method, recorded_name in METHODS.items():
        ids = manifest['top10'][method]
        if len(ids) != 10 or len(set(ids)) != 10 or not set(ids) <= set(candidates):
            raise ValueError(f'{method}: expected ten unique candidates in the review pool')
        recorded = manifest.get('method_rankings', {}).get(recorded_name, [])
        if [row['candidate_id'] for row in recorded] != ids:
            raise ValueError(f'{method}: inconsistent frozen ranking order')
        result[method] = [candidates[cid] for cid in ids]
    return result


def dcg(grades):
    return sum((2 ** int(grade) - 1) / math.log2(position + 2)
               for position, grade in enumerate(grades))


def evaluate(original, labeled, manifest, *, require_complete=False):
    labels = validate_labels(original, labeled, require_complete=require_complete)
    methods = frozen_methods(manifest, original)
    known = [int(row['relevance_grade']) for row in labels.values()
             if row['relevance_grade'] in ('0', '1', '2', '3')]
    ideal = dcg(sorted(known, reverse=True)[:10])
    counts = Counter(row['relevance_grade'] or 'blank' for row in labels.values())
    report = {
        'scope': 'one-role judged-pool comparison; not population-wide relevance',
        'gain': '2^grade - 1', 'discount': 'log2(rank + 1)',
        'ideal_pool': 'numeric grades 0–3 only; U and blank excluded, never mapped to 0',
        'grade_counts': {grade: counts[grade] for grade in ('0', '1', '2', '3', 'U', 'blank')},
        'pool_size': len(labels), 'numeric_judged_pool_size': len(known),
        'ideal_dcg_at_10': ideal, 'methods': {},
    }
    for method, review_ids in methods.items():
        grades = [labels[rid]['relevance_grade'] for rid in review_ids]
        judged = sum(grade in ('0', '1', '2', '3') for grade in grades)
        reasons = []
        if judged < 10:
            reasons.append('top_10_contains_U_or_blank')
        if ideal == 0:
            reasons.append('ideal_gain_is_zero')
        report['methods'][method] = {
            'judged_count': judged, 'top_k': 10, 'judged_coverage': judged / 10,
            'U_count': grades.count('U'), 'blank_count': grades.count(''),
            'pooled_ndcg_at_10': None if reasons else dcg(grades) / ideal,
            'unavailable_reasons': reasons,
        }
    return report


def verify_benchmark(manifest, original, *, root, manifest_path, verification_path, original_path):
    """Verify the frozen benchmark before real aggregate reporting, without inference."""
    reference = json.loads(Path(verification_path).read_text())
    if sha256(original_path) != reference['reviewer_sha256']:
        raise ValueError('Original reviewer CSV fingerprint mismatch')
    if sha256(manifest_path) != reference['manifest_sha256']:
        raise ValueError('Frozen Phase 3A manifest fingerprint mismatch')
    if manifest['format_version'] != 1 or manifest['as_of'] != '2026-11-13':
        raise ValueError('Wrong benchmark version or scoring date')
    settings = manifest['ranker_settings']
    expected = {'hybrid_top_n': 10, 'coarse_n': 500, 'llm_n': 0, 'use_llm': False, 'cache': True}
    if any(settings.get(key) != value for key, value in expected.items()):
        raise ValueError('Frozen ranker settings differ')
    dataset = manifest['dataset']
    if dataset['records'] != 100000 or sha256(dataset['path']) != dataset['sha256']:
        raise ValueError('Dataset fingerprint/count differs from Phase 3A')
    for relative, recorded in manifest['source_sha256'].items():
        path = (Path(root) / relative).resolve()
        if not path.is_relative_to(Path(root).resolve()) or sha256(path) != recorded:
            raise ValueError(f'Frozen benchmark source changed: {relative}')
    # Literal configuration reads avoid importing/loading the embedding model.
    assignments = {}
    for node in ast.parse((Path(root) / 'pipeline/encoder.py').read_text()).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in ('MODEL_NAME', 'MODEL_REVISION'):
                    assignments[target.id] = ast.literal_eval(node.value)
    if manifest['model'] != {'name': assignments['MODEL_NAME'], 'revision': assignments['MODEL_REVISION'], 'dimension': 384}:
        raise ValueError('Embedding model identity/revision differs')
    # JD source must be frozen, and its recorded raw text must hash consistently.
    jd = manifest['jd']
    if hashlib.sha256(jd['raw'].encode()).hexdigest() != jd['sha256']:
        raise ValueError('JD fingerprint mismatch')
    for entry in manifest['cache'].values():
        if entry['status'] != 'verified_hit' or sha256(entry['path']) != entry['sha256']:
            raise ValueError('Recorded verified embedding cache changed')
    if [row['review_id'] for row in original] != [entry['review_id'] for entry in manifest['pool']]:
        raise ValueError('Original reviewer order differs from frozen pool')
    blank_rows = [dict(row, relevance_grade='', reason='') for row in original]
    if hashlib.sha256(canonical(blank_rows).encode()).hexdigest() != manifest['evidence_sha256']:
        raise ValueError('Frozen reviewer evidence fingerprint mismatch')
    for entry in manifest['pool']:
        expected_id = 'R-' + hashlib.sha256(canonical(['talentlens-review-v1', dataset['sha256'], entry['candidate_id']]).encode()).hexdigest()[:16]
        if entry['review_id'] != expected_id:
            raise ValueError('Frozen review ID mapping mismatch')
    frozen_methods(manifest, original)
    return {'status': 'verified', 'as_of': manifest['as_of'],
            'dataset_sha256': dataset['sha256'], 'manifest_sha256': reference['manifest_sha256'],
            'frozen_rankings_only': True, 'model_inference': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--original', required=True)
    parser.add_argument('--labels', required=True)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--verification', required=True, help='Phase 3A verification.json with frozen manifest SHA-256')
    args = parser.parse_args(argv)
    # Gate before even opening the real manifest, keeping methods hidden during labeling.
    try:
        original_fields, original = read_csv(args.original)
        fields, labeled = read_csv(args.labels)
        if fields != original_fields:
            raise ValueError('Labeled CSV columns differ from original')
        validate_labels(original, labeled, require_complete=True, expected_count=50)
        manifest = json.loads(Path(args.manifest).read_text())
        verification = verify_benchmark(manifest, original, root=Path(__file__).resolve().parents[1],
                            manifest_path=args.manifest, verification_path=args.verification, original_path=args.original)
        report = evaluate(original, labeled, manifest, require_complete=True)
    except (ValueError, KeyError, OSError) as exc:
        parser.error(str(exc))
    report['benchmark_verification'] = verification
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
