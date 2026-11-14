"""Build a blinded, reproducible review pool using verified embeddings only."""
import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import re
import tempfile

import numpy as np

from pipeline import encoder, ranking
from pipeline.dates import parse_as_of
from pipeline.jd_parser import JD_RAW, get_jd, get_jd_text_for_embedding

VERSION = 1
DEFAULT_SEED = 20261113
FIELDS = ['review_id', 'total_experience_years', 'current_role', 'summary',
          'skills_evidence', 'career_evidence', 'work_location',
          'work_arrangement_evidence', 'relevance_grade', 'reason']
KEYWORD_GROUPS = {
    'embedding_retrieval': ['embedding', 'embeddings', 'sentence transformers', 'bge', 'e5',
                           'openai embeddings', 'semantic search', 'dense retrieval'],
    'vector_or_hybrid': ['vector database', 'vector databases', 'hybrid search', 'pinecone',
                         'weaviate', 'qdrant', 'milvus', 'elasticsearch', 'faiss'],
    'python': ['python'],
    'evaluation': ['ndcg', 'mrr', 'map', 'mean average precision', 'a/b testing',
                   'offline to online'],
}
SHIPPING_TERMS = ['production', 'deployed', 'shipped']
SYSTEM_TERMS = ['retrieval', 'ranking', 'search', 'recommendation', 'recommendations']


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def file_sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def terms_pattern(terms):
    return re.compile(r'(?<!\w)(?:' + '|'.join(re.escape(t) for t in terms) + r')(?!\w)')


PATTERNS = {key: terms_pattern(terms) for key, terms in KEYWORD_GROUPS.items()}
SHIP_PATTERN = terms_pattern(SHIPPING_TERMS)
SYSTEM_PATTERN = terms_pattern(SYSTEM_TERMS)


def keyword_score(candidate):
    """0–5 lexical group coverage; synonyms/repetition never add extra points."""
    p = candidate['profile']
    parts = [p['headline'], p['summary'], p['current_title']]
    parts += [s['name'] for s in candidate.get('skills', [])]
    parts += [str(job.get(field, '')) for job in candidate.get('career_history', [])
              for field in ('title', 'description')]
    text = ' '.join(parts).casefold().replace('-', ' ').replace('—', ' ').replace('–', ' ')
    return sum(bool(pattern.search(text)) for pattern in PATTERNS.values()) + int(
        bool(SHIP_PATTERN.search(text) and SYSTEM_PATTERN.search(text)))


class VerifiedCacheIdentity:
    """Identity of the real model behind cached vectors; never loads/encodes."""
    _embedding_cache_identity = {'name': encoder.MODEL_NAME, 'revision': encoder.MODEL_REVISION}

    def get_sentence_embedding_dimension(self):
        return 384

    def encode(self, *args, **kwargs):
        raise RuntimeError('Fresh encoding prohibited: diagnose the verified cache miss first')


def verified_embeddings(candidates):
    model = VerifiedCacheIdentity()
    paths = {
        'candidates': encoder._cache_path('candidates', model,
            ([c['candidate_id'], encoder.build_candidate_text(c)] for c in candidates)),
        'jd': encoder._cache_path('jd', model, [get_jd_text_for_embedding()]),
    }
    arrays = {}
    for kind, path in paths.items():
        shape = (len(candidates), 384) if kind == 'candidates' else (384,)
        array = encoder._read_cache(path, shape)
        if array is None:
            raise RuntimeError(f'No valid verified {kind} cache: {path}. Stop and diagnose; no encoding or cache writes attempted.')
        arrays[kind] = array
    return arrays, paths


def priority(seed, domain, cid):
    return digest(canonical([seed, domain, cid]))


def select_pool(semantic_ids, top_methods, *, seed, target=50, coarse_n=500, near_count=10):
    """Union top lists, fixed window spanning cutoff, then seeded outside sample."""
    if len(semantic_ids) != len(set(semantic_ids)):
        raise ValueError('Candidate IDs must be unique')
    population = set(semantic_ids)
    methods = {}
    def add(cid, method):
        methods.setdefault(cid, set()).add(method)
    for method, ids in top_methods.items():
        for cid in ids:
            if cid not in population:
                raise ValueError(f'Unknown candidate in {method}')
            add(cid, method)
    # For coarse_n=500, near_count=10: ranks 496..505, inclusive.
    start = max(0, coarse_n - near_count // 2)
    near = semantic_ids[start:start + near_count]
    for cid in near:
        add(cid, 'semantic_cutoff')
    if len(methods) > target:
        raise ValueError('Target too small for mandatory top-list/cutoff union')
    outside = [cid for cid in semantic_ids[coarse_n:] if cid not in methods]
    outside.sort(key=lambda cid: (priority(seed, 'outside-sample', cid), cid))
    needed = target - len(methods)
    if len(outside) < needed:
        raise ValueError('Not enough candidates outside the shortlist to fill target')
    for cid in outside[:needed]:
        add(cid, 'outside_random')
    ordered = sorted(methods, key=lambda cid: (priority(seed, 'review-shuffle', cid), cid))
    return ordered, {cid: sorted(sources) for cid, sources in methods.items()}, near


def review_id(dataset_sha, cid):
    return 'R-' + digest(canonical(['talentlens-review-v1', dataset_sha, cid]))[:16]


def scrub(text, candidate):
    """Strip known identities and contact tokens while retaining technical evidence."""
    text = '' if text is None else str(text)
    profile = candidate['profile']
    identities = [candidate['candidate_id'], profile.get('anonymized_name'), profile.get('current_company')]
    identities += [j.get('company') for j in candidate.get('career_history', [])]
    identities += [e.get('institution') for e in candidate.get('education', [])]
    for value in sorted({x for x in identities if x}, key=len, reverse=True):
        text = re.sub(r'(?<!\w)' + re.escape(value) + r'(?!\w)', '[redacted]', text, flags=re.I)
    text = re.sub(r'\bCAND_[0-9]+\b', '[redacted]', text)
    text = re.sub(r'\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b', '[contact removed]', text, flags=re.I)
    text = re.sub(r'(?:https?://|www\.|(?:github|linkedin)\.com/)[^\s,;]+', '[link removed]', text, flags=re.I)
    def phone(match):
        return '[contact removed]' if sum(c.isdigit() for c in match[0]) >= 10 else match[0]
    text = re.sub(r'(?<!\w)\+?\d[\d ()-]{8,}\d(?!\w)', phone, text)
    return text


def safe_cell(text):
    text = str(text)
    return "'" + text if text.lstrip().startswith(('=', '+', '-', '@')) else text


def evidence_row(candidate, dataset_sha):
    p = candidate['profile']
    skills = [{'skill': scrub(s['name'], candidate), 'self_reported_proficiency': scrub(s.get('proficiency', ''), candidate),
               'duration_months': s.get('duration_months', '')} for s in candidate.get('skills', [])]
    jobs = []
    consulting = get_jd()['consulting_companies']
    for job in candidate.get('career_history', []):
        company = str(job.get('company', '')).casefold()
        context = ('Consulting/services employer explicitly listed in the JD'
                   if any(term in company for term in consulting)
                   else 'Employer product/consulting status unconfirmed')
        jobs.append({field: scrub(job.get(field, ''), candidate) for field in
                     ('title', 'start_date', 'end_date', 'duration_months', 'industry', 'company_size', 'description')})
        jobs[-1]['employer_context'] = context
    signals = candidate['redrob_signals']
    arrangement = {field: signals.get(field, 'not disclosed')
                   for field in ('preferred_work_mode', 'willing_to_relocate')}
    row = {'review_id': review_id(dataset_sha, candidate['candidate_id']),
           'total_experience_years': str(p['years_of_experience']),
           'current_role': scrub(p['current_title'], candidate), 'summary': scrub(p['summary'], candidate),
           'skills_evidence': canonical(skills), 'career_evidence': canonical(jobs),
           'work_location': scrub(p['location'], candidate),
           'work_arrangement_evidence': scrub(canonical(arrangement), candidate),
           'relevance_grade': '', 'reason': ''}
    return {field: safe_cell(row[field]) for field in FIELDS}


def atomic_write(path, content):
    path = Path(path)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='', dir=path.parent,
                                         delete=False) as handle:
            temp = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        if temp:
            temp.unlink(missing_ok=True)


def write_review_files(output_dir, rows, manifest):
    """Require identical inputs on rerun; preserve grade/reason verbatim by ID."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    csv_path, manifest_path = output_dir / 'reviewer.csv', output_dir / 'manifest.json'
    if csv_path.exists() or manifest_path.exists():
        if not csv_path.exists() or not manifest_path.exists():
            raise ValueError('Both existing reviewer.csv and manifest.json are required; use a new output directory')
        if json.loads(manifest_path.read_text()) != manifest:
            raise ValueError('Inputs/configuration changed; use a new output directory to protect labels')
        with csv_path.open(newline='', encoding='utf-8') as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != FIELDS:
                raise ValueError('Reviewer CSV columns changed; preserving existing file')
            previous = list(reader)
        by_id = {r['review_id']: r for r in previous}
        if len(by_id) != len(previous) or set(by_id) != {r['review_id'] for r in rows}:
            raise ValueError('Reviewer IDs changed or duplicated; preserving existing file')
        rows = [dict(row) for row in rows]
        for row in rows:
            old = by_id[row['review_id']]
            if any(old[field] != row[field] for field in FIELDS if field not in ('relevance_grade', 'reason')):
                raise ValueError('Review evidence was edited; preserving existing file')
            if old['relevance_grade'].strip() not in ('', '0', '1', '2', '3', 'U'):
                raise ValueError('Invalid existing relevance_grade; preserving existing file')
            row.update({field: old[field] for field in ('relevance_grade', 'reason')})
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(rows)
    atomic_write(csv_path, stream.getvalue())
    atomic_write(manifest_path, json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + '\n')
    return csv_path, manifest_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidates', required=True)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--as-of', type=parse_as_of, required=True, metavar='YYYY-MM-DD')
    parser.add_argument('--seed', type=int, default=DEFAULT_SEED)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    output = Path(args.output_dir).resolve()
    if output == root or root in output.parents:
        parser.error('--output-dir must be outside the project/Git workspace')
    dataset_sha = file_sha(args.candidates)
    candidates = ranking.load_ranking_input(args.candidates, False)
    if len(candidates) != 100000:
        parser.error('This pilot expects the local 100,000-record JSONL dataset')
    arrays, paths = verified_embeddings(candidates)
    similarities = encoder.cosine_similarities(arrays['jd'], arrays['candidates'])
    semantic = ranking.select_shortlist(candidates, similarities, len(candidates))
    semantic_ids = [c['candidate_id'] for c, _ in semantic]
    hybrid = ranking.rank_candidates(candidates, top_n=10, coarse_n=500, llm_n=0,
                 use_llm=False, cache=True, model_factory=VerifiedCacheIdentity, as_of=args.as_of)
    keywords = sorted(((c['candidate_id'], keyword_score(c)) for c in candidates),
                      key=lambda pair: (-pair[1], pair[0]))
    methods = {'hybrid_top10': [r['candidate']['candidate_id'] for r in hybrid],
               'semantic_top10': semantic_ids[:10],
               'keyword_top10': [cid for cid, _ in keywords[:10]]}
    ordered, sources, near = select_pool(semantic_ids, methods, seed=args.seed)
    by_id = {c['candidate_id']: c for c in candidates}
    rows = [evidence_row(by_id[cid], dataset_sha) for cid in ordered]
    assert len(rows) == len({r['review_id'] for r in rows}) == 50
    assert all(set(ids) <= set(ordered) for ids in methods.values())
    source_files = ['pipeline/ranking.py', 'pipeline/encoder.py', 'pipeline/dates.py',
                    'pipeline/behavioral.py', 'pipeline/honeypot.py', 'pipeline/feature_scorer.py',
                    'pipeline/loader.py', 'pipeline/jd_parser.py', 'pipeline/llm_reranker.py',
                    'benchmarks/build_review_set.py', 'benchmarks/labeling_rubric.md']
    manifest = {
        'format_version': VERSION, 'seed': args.seed, 'as_of': args.as_of.isoformat(),
        'dataset': {'path': str(Path(args.candidates).resolve()), 'sha256': dataset_sha, 'records': len(candidates)},
        'jd': {'raw': JD_RAW, 'requirements': get_jd(), 'embedding_text': get_jd_text_for_embedding(),
               'sha256': digest(JD_RAW)},
        'model': {'name': encoder.MODEL_NAME, 'revision': encoder.MODEL_REVISION, 'dimension': 384},
        'cache': {key: {'path': str(path.resolve()), 'sha256': file_sha(path), 'status': 'verified_hit'}
                  for key, path in paths.items()},
        'ranker_settings': {'hybrid_top_n': 10, 'coarse_n': 500, 'llm_n': 0, 'use_llm': False,
                            'cache': True, 'ordering': 'shared ranker including displayed-score ties'},
        'keyword_baseline': {'groups': KEYWORD_GROUPS, 'shipping_terms': SHIPPING_TERMS,
                            'system_terms': SYSTEM_TERMS, 'score': 'four binary groups plus shipping AND system group; max 5',
                            'tie_break': 'candidate_id ascending', 'input_fields': 'headline, summary, current_title, skill names, career titles/descriptions'},
        'sampling': {'target': 50, 'semantic_cutoff_ranks_inclusive': [496, 505], 'near_ids': near,
                     'outside_population': 'semantic ranks >500 excluding already selected candidates',
                     'random': 'ascending SHA256(JSON([seed, outside-sample, candidate_id])) without replacement',
                     'shuffle': 'independent ascending SHA256(JSON([seed, review-shuffle, candidate_id]))',
                     'review_id': 'R- plus first 16 hex SHA256(JSON([talentlens-review-v1, dataset_sha256, candidate_id]))'},
        'top10': methods,
        'method_rankings': {'hybrid': [{'candidate_id': r['candidate']['candidate_id'], 'display_score': r['display_score']} for r in hybrid],
                            'semantic': [{'candidate_id': c['candidate_id'], 'similarity': score} for c, score in semantic[:10]],
                            'keyword': [{'candidate_id': cid, 'score': score} for cid, score in keywords[:10]]},
        'pool': [{'review_id': review_id(dataset_sha, cid), 'candidate_id': cid, 'selection_methods': sources[cid]}
                 for cid in ordered],
        'counts_by_selection_method': {method: sum(method in values for values in sources.values())
                                      for method in [*methods, 'semantic_cutoff', 'outside_random']},
        'evidence_sha256': digest(canonical(rows)),
        'source_sha256': {name: file_sha(root / name) for name in source_files},
        'environment': {'python': platform.python_version(), 'numpy': np.__version__},
        'evaluation_scope': 'one-role pooled NDCG@10 after labeling; any recall denominator is known relevant in judged pool; U is not automatically 0',
    }
    csv_path, manifest_path = write_review_files(output, rows, manifest)
    print(json.dumps({'pool_size': len(rows), 'counts_by_selection_method': manifest['counts_by_selection_method'],
                      'reviewer_csv': str(csv_path), 'manifest': str(manifest_path),
                      'dataset_sha256': dataset_sha, 'seed': args.seed, 'as_of': args.as_of.isoformat()}, indent=2))


if __name__ == '__main__':
    main()
