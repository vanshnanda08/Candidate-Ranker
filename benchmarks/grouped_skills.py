"""Experimental requirement coverage; never imported by production ranking."""
from contextlib import nullcontext
from datetime import date
import json
from pathlib import Path
import re
from unittest.mock import patch

from pipeline import feature_scorer, ranking
from benchmarks.build_review_set import VerifiedCacheIdentity

SPEC_PATH = Path(__file__).with_name('grouped_skills_spec.json')
SPEC = json.loads(SPEC_PATH.read_text())
ESSENTIAL = {g['id']: g for g in SPEC['essential_groups']}
NICE = {g['id']: g for g in SPEC['nice_groups']}


def normalize(value):
    return re.sub(r'\s+', ' ', str(value).casefold().translate(str.maketrans({'-':' ', '–':' ', '—':' ', '‑':' ', '−':' '}))).strip()


def pattern(terms):
    return re.compile(r'(?<!\w)(?:' + '|'.join(re.escape(normalize(t)) for t in terms) + r')(?!\w)')


MATCH = {name: pattern(words) for name, words in SPEC['matching'].items()}
ALIASES = {name: pattern(g['aliases']) for name, g in {**ESSENTIAL, **NICE}.items() if 'aliases' in g}
PYTHON = pattern(['python'])
BM25 = pattern(['bm25'])
INFERENCE = pattern(['inference'])
OPEN_SOURCE = pattern(['open source'])


def group_matches(candidate):
    skills = [normalize(s.get('name', '')) for s in candidate.get('skills', [])]
    texts = [candidate.get('profile', {}).get('summary', '')]
    texts += [j.get('description', '') for j in candidate.get('career_history', [])]
    units = [normalize(unit) for text in texts for unit in re.split(r'[.!?;\n]+', str(text or ''))]
    units = [unit for unit in units if unit and not MATCH['negative_or_learning_units'].search(unit)]
    def narrative(predicate): return any(predicate(unit) for unit in units)
    def declared_or_narrative(name):
        return any(ALIASES[name].search(unit) for unit in [*skills, *units])
    def has(unit, name): return bool(MATCH[name].search(unit))
    essential = {
        'production_embedding_retrieval': narrative(lambda u: has(u,'actions') and has(u,'embeddings') and has(u,'systems') and has(u,'production_context')),
        'vector_or_hybrid': declared_or_narrative('vector_or_hybrid') or narrative(lambda u: has(u,'actions') and
             (has(u,'hybrid') or bool(BM25.search(u) and has(u,'dense')))),
        'python_engineering': narrative(lambda u: has(u,'actions') and bool(PYTHON.search(u))),
        'ranking_evaluation': narrative(lambda u: has(u,'actions') and has(u,'systems') and has(u,'evaluation_context') and bool(ALIASES['ranking_evaluation'].search(u))),
        'shipped_ranking_search_or_recommendation': narrative(lambda u: has(u,'actions') and has(u,'systems') and has(u,'production_context')),
    }
    nice = {
        'llm_finetuning': declared_or_narrative('llm_finetuning'),
        'learning_to_rank': declared_or_narrative('learning_to_rank'),
        'hr_recruiting_marketplace': narrative(lambda u: bool(ALIASES['hr_recruiting_marketplace'].search(u))),
        'distributed_or_inference_optimization': declared_or_narrative('distributed_or_inference_optimization') or narrative(lambda u: has(u,'actions') and bool(INFERENCE.search(u)) and has(u,'inference_methods')),
        'ai_ml_open_source': narrative(lambda u: has(u,'contribution_actions') and bool(OPEN_SOURCE.search(u)) and bool(ALIASES['ai_ml_open_source'].search(u))),
    }
    return [g for g in ESSENTIAL if essential[g]], [g for g in NICE if nice[g]]


def score_skills(candidate):
    required, optional = group_matches(candidate)
    # Preserve the production assessment penalty exactly, including exact-name matching.
    proficiency = {s['name'].lower(): s['proficiency'] for s in candidate.get('skills', [])}
    penalty = 1.0
    for name, value in candidate.get('redrob_signals', {}).get('skill_assessment_scores', {}).items():
        if proficiency.get(name.lower()) in ('expert','advanced') and value < 40:
            penalty *= .85
    combined = (.75 * len(required) / len(ESSENTIAL) + .25 * len(optional) / len(NICE)) * penalty
    return combined, len(required), required


def run_hybrid(candidates, *, top_n, experimental=False, model_factory=VerifiedCacheIdentity):
    """Instrument all shortlisted components, restoring patches before returning."""
    trace = {}
    original_skill_function = feature_scorer.score_skills
    structured_fn = feature_scorer.compute_structured_score
    behavioral_fn = ranking.score_behavioral
    honeypot_fn = ranking.evaluate_honeypot
    def structured(candidate):
        result = structured_fn(candidate)
        trace[candidate['candidate_id']] = {'structured': result}
        return result
    def behavioral(candidate, **kwargs):
        result = behavioral_fn(candidate, **kwargs)
        trace[candidate['candidate_id']]['behavioral'] = result
        return result
    def honeypot(candidate, **kwargs):
        result = honeypot_fn(candidate, **kwargs)
        trace[candidate['candidate_id']]['honeypot'] = result
        return result
    with (patch.object(feature_scorer, 'score_skills', score_skills) if experimental else nullcontext()), \
         patch.object(ranking, 'compute_structured_score', side_effect=structured), \
         patch.object(ranking, 'score_behavioral', side_effect=behavioral), \
         patch.object(ranking, 'evaluate_honeypot', side_effect=honeypot):
        rows = ranking.rank_candidates(candidates, top_n=top_n, coarse_n=500, llm_n=0,
            use_llm=False, cache=True, model_factory=model_factory, as_of=date(2026,11,13))
    assert feature_scorer.score_skills is original_skill_function
    return rows, trace


def verify_controlled_components(baseline, experimental):
    if list(baseline) != list(experimental):
        raise ValueError('Semantic shortlist/order changed')
    for cid, before in baseline.items():
        after = experimental[cid]
        if before['behavioral'] != after['behavioral'] or before['honeypot'] != after['honeypot']:
            raise ValueError('Non-skill behavioral/honeypot components changed')
        for field in ('career_score','exp_score','edu_score','loc_score'):
            if before['structured'][field] != after['structured'][field]:
                raise ValueError(f'Non-skill structured component changed: {field}')
    return {'shortlist_order_equal':True,'non_skill_components_equal':True,'shortlist_size':len(baseline)}
