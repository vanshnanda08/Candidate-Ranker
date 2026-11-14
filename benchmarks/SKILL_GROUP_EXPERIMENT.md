# Offline grouped-skill experiment, version 1

These rules are fixed from `JD_RAW` and the existing labeling rubric **before
inspecting this experiment's rankings**. Existing AI-assisted, user-confirmed
labels are used only for evaluation. No tuning or fitting to those labels is
performed. This is an experimental evidence-matching proxy, not an automatic
rubric grade or verification of a candidate's claims.

## Requirement groups and evidence

Each of five essentials contributes at most one match:

1. Production embedding retrieval: sentence-transformer, BGE, E5, OpenAI or a
   comparable explicit embedding/semantic retrieval description, with action,
   system and production context in the same narrative unit.
2. Vector infrastructure **or** documented hybrid search: FAISS, Pinecone,
   Weaviate, Qdrant, Milvus and Elasticsearch are alternatives. OpenSearch and
   pgvector are comparable alternatives, not extra requirements. A documented
   hybrid search/retrieval approach, including BM25 plus dense vectors, also
   satisfies this group without a vendor name. Named skill claims count as
   declared capability for this tool group, not proof of production expertise.
3. Python engineering: a narrative action involving Python; a bare Python tag
   does not establish personal implementation. This lexical proxy still cannot
   establish strong code quality, which remains a human-review question.
4. Ranking evaluation: owned/designed/etc. evaluation involving ranking, search,
   retrieval or recommendations, with NDCG **or** MRR **or** MAP **or** A/B testing
   **or** offline/online validation. No bonus for naming several metrics.
5. Shipping: built/shipped/owned/etc. a ranking, search **or** recommendation
   system with production/use context. These are different acceptable systems.
   End-to-end scope, genuine ownership and meaningful scale still require human
   review; no arbitrary traffic threshold is added.

The five nice-to-have groups are LLM fine-tuning (LoRA/QLoRA/PEFT alternatives),
learning to rank (XGBoost/LightGBM/neural LTR alternatives), HR/recruiting or
marketplace context, distributed systems or inference optimization, and AI/ML
open-source contributions. Merely using an open-source framework does not count
as a contribution. Generic LLM, PyTorch or TensorFlow tags earn no independent
nice-to-have points. Multiple aliases/repetitions never add group credit.

Inputs: `skills[].name` for declared tool/nice-to-have capability, and
`profile.summary` plus `career_history[].description` for narrative evidence.
Narratives are split on periods, exclamation/question marks, semicolons and
newlines. Case is folded, hyphens normalized, whitespace collapsed, and matches
require token/phrase boundaries. Units explicitly expressing no production or
professional experience, coursework, side projects or future learning intentions
are excluded from narrative matching. This is a conservative heuristic, not
complete negation or relationship extraction. A single unit may satisfy multiple
**distinct** JD requirements, but never more than once per requirement.

No title, employer, school, location or engagement signals enter this experimental
skill calculation. The other production scorers continue using their original
inputs, including existing behavior/education/location components. Experience
level and role logistics stay in their existing components; they are not counted
again as skill groups. Exact aliases, action/context words and rules live in
`grouped_skills_spec.json`, whose hash is recorded before ranking.

## Controlled change

Skill score = 0.75 × matched essentials/5 + 0.25 × matched nice groups/5, followed
by the **unchanged** assessment penalty. This preserves the production skill
score's 75/25 combination and exact-name/proficiency assessment rule. Existing
structured weights (including skill ×0.35), final weights (30/40/20/5/5), penalty
multipliers, rounding, normalization and ID tie rules are unchanged. Skill-derived
diagnostics naturally show group names/counts instead of individual aliases.

Only `feature_scorer.score_skills` is temporarily replaced inside a local context
while calling the existing shared ranker. The original function is restored on
success and exceptions. No production files/defaults/routes import this variant.
Both methods use identical cached embeddings, text/model identity, top-500 semantic
shortlist, scoring date 2026-11-13, and use_llm=False/llm_n=0. All 500 candidates'
non-skill components and order are checked for equality.

## Comparison and follow-up protocol

First verify frozen Phase 3A inputs and confirmed Phase 3B labels, then reproduce
the hybrid top_n=10 IDs **and display scores** exactly. Also verify keyword top 10.
Generate top 20 for the frozen keyword baseline, current hybrid and grouped hybrid.
Report @10 from each reported top-20 prefix and @20 from the entire list. Because
production normalization depends on top_n, separately record whether standalone
hybrid top 10 equals its top-20 prefix; do not alter that behavior to force nesting.

All NDCG values use the **same existing judged pool**, gain 2^grade−1 and
log2(rank+1) discounts. Do not drop unknown positions or treat them as grade 0.
Report NDCG only when every position at that cutoff has a numeric judgment and
the pooled ideal gain is positive. U and missing labels are reported separately.
Report pairwise overlap counts at both cutoffs. Existing top-10 results alone do
not establish the quality of newly selected, unjudged profiles.

If needed, create a **separate** review CSV for the unknown candidates in the
three-method top-20 union, using the existing rubric/evidence redactor and stable
review IDs. Shuffle by seed 20261114 with an independent SHA-256 priority domain.
Keep method/rank/score mappings in a separate local manifest, not reviewer cells.
All new grades/reasons start blank; reruns preserve entered follow-up labels.
Never modify the frozen 50 judgments. Expanded-pool evaluation waits for review.
Any gain on this one-role, deliberately pooled set remains exploratory.
