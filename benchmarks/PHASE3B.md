> Historical experiment instructions. Set `REVIEW_ROOT` to your own private review directory. Private labels, manifests and datasets are not bundled.

# Phase 3B: confirmed labels and frozen pooled evaluation

During labeling, read only the rubric and reviewer evidence. Do not open the
real manifest or disclose methods, ranks or scores. Actual grades/reasons come
only from the user's explicit confirmations. No real evaluation runs until all
50 profiles have a grade 0–3 or U and a non-empty reason.

## Apply the existing rubric consistently

A documented gap is an explicit statement or substantive responsibility/history
showing a shortfall. Missing evidence means the profile does not establish the
requirement; it is not proof that the candidate lacks it. Use U only when there
is too little substantive evidence to judge the profile, rather than for one
missing detail in an otherwise informative profile.

Unconfirmed hybrid/relocation compatibility is a follow-up item, not an automatic
downgrade or reason to use U. A remote preference, a relocation flag or current
city does not by itself establish inability to meet the arrangement. Record
“hybrid compatibility unconfirmed” when appropriate. A clear statement that the
candidate cannot meet the required hybrid arrangement is a material role
constraint. For an otherwise complete match, that fits the rubric's grade-2
material-gap anchor; it does not automatically make the candidate grade 0.
This clarifies the existing rubric without changing the frozen Phase 3A rubric.

## Save confirmations and resume

`benchmarks.review_labels.save_confirmed(original_path, labeled_path, confirmations)`
accepts a list of dictionaries containing exactly review_id, relevance_grade and
reason. Use the separate reviewer_labeled.csv path. It validates the whole batch
before an atomic write, retains original evidence/IDs and all prior confirmed
labels, and rejects silent revisions. Repeating the same confirmation is safe.
It never opens a manifest. An empty confirmation batch writes nothing.

`next_batch(original_path, labeled_path)` returns the next five blank grades in
the original reviewer order. U counts as a completed review, not a numeric
judgment. The saved file supports resuming in a later session. Close external CSV
editors while saving to avoid concurrent edits. The original reviewer.csv is
never overwritten. No actual labels have been supplied or saved at setup time.

## Metrics and availability

The evaluator consumes only the frozen Phase 3A top-10 lists. It joins candidate
IDs to review IDs through the manifest and joins labels by review_id, never by
CSV row position. It does not rerun ranking, load a model or change weights.

- Gain = 2^grade − 1 for numeric grades 0, 1, 2, 3.
- DCG@10 = sum of gain/log2(rank+1), with ranks starting at 1.
- IDCG@10 uses the ten highest numeric grades in the entire judged pool.
- U and blank are unknown and excluded from that ideal pool, not mapped to 0.
- A method's NDCG@10 is unavailable (JSON null with a reason) if any of its ten
  profiles is U/blank, or if IDCG@10 is zero.
- Judged coverage counts numeric grades 0–3 divided by 10. A grade 0 is judged;
  U is not. U/blank counts are reported separately.

If U occurs outside a method's top 10, that method can still have NDCG against
the known judged-pool ideal. This is conditional on known judgments, not an
estimate of the unjudged candidates' relevance. No recall is calculated. If added
later, relevance must be grades 2/3 and the denominator must be the known relevant
candidates in the judged pool, explicitly named judged-pool recall.

## Run only after all 50 confirmations

```bash
.venv/bin/python -m benchmarks.evaluate_review_set \
  --original ${REVIEW_ROOT}/senior-ai-engineer-2026-11-13/reviewer.csv \
  --labels ${REVIEW_ROOT}/senior-ai-engineer-2026-11-13/reviewer_labeled.csv \
  --manifest ${REVIEW_ROOT}/senior-ai-engineer-2026-11-13/manifest.json \
  --verification ${REVIEW_ROOT}/senior-ai-engineer-2026-11-13/verification.json
```

The CLI checks completion before opening the manifest. It then verifies Phase 3A
manifest/original-CSV fingerprints, exact evidence and mapping, recorded dataset
byte fingerprint/count, as_of=2026-11-13, no-Claude ranker settings, model revision,
frozen source hashes and cache hashes. The source and artifact fingerprints are
compared with the locally recorded Phase 3A verification file. This trusts the
Phase 3A freeze as the provenance anchor; it does not authenticate a jointly
replaced manifest and verification file or recount/rerank the full dataset.
Changing frozen inputs fails verification instead of silently evaluating a new
benchmark. Aggregate JSON is printed locally only after validation succeeds.

## Offline tests

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python -m unittest discover -s tests -v
```

All new evaluation/save fixtures are fictional, including fixture manifest
mappings. They cover label validity and reasons, immutable evidence, missing or
duplicate IDs, persistence/resume, U versus 0, gain/discount arithmetic, pooled
ideal ordering, unavailable metrics, coverage, frozen-list consistency, input
fingerprints and the completion-before-manifest gate. Real labels/manifests are
not used by these tests. Actual aggregate results remain pending human review.
