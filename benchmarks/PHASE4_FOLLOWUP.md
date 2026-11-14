> Historical experiment instructions. Set `REVIEW_ROOT` to your own private review directory. Private labels, manifests and datasets are not bundled.

# Phase 4 follow-up review and frozen combined-pool evaluation

Use the existing `benchmarks/labeling_rubric.md` and the shuffled Phase 4A follow-up
`reviewer.csv`. Summarize evidence without exposing method provenance, ranks or
scores. Save only explicit user-confirmed grades/reasons in the separate follow-up
`reviewer_labeled.csv`. Keep the blank original and all 50 Phase 3B labels intact.

## Save and resume

Reuse `benchmarks.review_labels.save_confirmed(original_path, labeled_path,
confirmations)` and `next_batch(original_path, labeled_path)`. Paths refer to:

```text
${REVIEW_ROOT}/skill-groups-2026-11-13-v1/followup/reviewer.csv
${REVIEW_ROOT}/skill-groups-2026-11-13-v1/followup/reviewer_labeled.csv
```

The helper validates evidence and IDs, writes atomically, preserves previous
confirmations, and refuses silent revisions. U is a completed review but an
unknown relevance judgment. The next batch follows original shuffled reviewer
order. No unconfirmed grades/reasons are generated. The manifest stays hidden
from the reviewer; evaluate only after all 21 reviews are complete.

## Evaluator extension

The separate `benchmarks.evaluate_grouped_followup` entry point imports the
existing comparison arithmetic. Phase 4A's runner, scoring function, specification,
protocol, tests and stored settings are unchanged; a separate command avoids
invalidating its recorded source hashes. No rankings are regenerated.

Before opening real manifests, the CLI validates completion of the original 50
and follow-up 21 reviews using the existing label validator. It then verifies:

- Phase 3A artifact/data/model/cache/source fingerprints and the Phase 3B label
  fingerprint, using the existing frozen-benchmark verifier.
- Phase 4A's four recorded artifact hashes, code plan, specification/protocol,
  fixed date 2026-11-13 and no-Claude settings.
- Follow-up manifest dataset fingerprint/provenance against the original freeze,
  its top-20 lists against Phase 4A's private frozen rankings, and shuffle seed.
- Unique review IDs and candidate IDs across both pools; all evidence and labels
  joined by review_id, not row position. Duplicate/overlapping pools fail instead
  of silently overwriting a judgment.
- Exactly the additional frozen top-20-union candidates are in the follow-up,
  with the same evidence fingerprint and stable review-ID mapping.

Integrity checks use locally recorded freeze files as trust anchors; they do not
cryptographically authenticate jointly replaced anchors and artifacts. The
Phase 3A dataset SHA-256 protects the recorded dataset/count without rerunning
inference or recounting the 100,000 records.

## Metrics after confirmation

Combine the 50 original and 21 follow-up profiles into one 71-profile review pool.
For all three frozen methods and both cutoffs, derive the ideal ranking from the
same combined numeric judgments (0–3), using gain 2^grade−1 and log2(rank+1).
U and blanks remain distinct from 0 and are excluded from the ideal. A total of
71 completed reviews may contain fewer than 71 numeric judgments if U occurs.

Report pooled NDCG and numeric judged coverage at 10 and 20, plus grouped-minus-
current pooled-NDCG and coverage changes at each cutoff. Any unknown top position
(U or blank) makes that method/cutoff NDCG unavailable; zero ideal gain also makes
it unavailable. The NDCG change is unavailable if either compared value is
unavailable. No incomplete ranked list is condensed to judged positions.

Pure functions support partial fictional fixtures for testing coverage and
unavailability. The real CLI intentionally refuses partial follow-up reviews and
prints no ranking information before completion. Existing Phase 4A @10/@20
metrics are not reused: all ideal gains are recomputed on the combined pool.

## Exact command after all 21 follow-up confirmations

From the project root, using the existing Python 3.12 .venv:

```bash
.venv/bin/python -m benchmarks.evaluate_grouped_followup \
  --frozen-dir ${REVIEW_ROOT}/senior-ai-engineer-2026-11-13 \
  --experiment-dir ${REVIEW_ROOT}/skill-groups-2026-11-13-v1 \
  --followup-labels ${REVIEW_ROOT}/skill-groups-2026-11-13-v1/followup/reviewer_labeled.csv
```

Output is aggregate JSON on local stdout. After completion, save it to a new local
Phase 4B result file, leaving all Phase 4A artifacts unchanged. Report combined
and per-cohort progress/grade counts, both cutoffs' aggregates and differences,
verification status, and the exact command. Describe labels as **AI-assisted and
user-confirmed**. Results are an exploratory one-role pilot, not general ranking
quality. No recall is calculated; any later recall must use known relevant grades
2/3 in the judged pool as its denominator.

## Offline tests

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python -m unittest discover -s tests -v
```

The added fictional fixtures cover partial labels, all 71 confirmed, overlapping
IDs, malformed labels/evidence, manifest/ranking/dataset disagreements, row-order
independence, U versus 0, zero ideal gain, shared expanded ideals and deltas, the
completion-before-manifest gate, and Phase 4A byte/source/provenance checks. The
existing regression suites run unchanged. No real aggregate evaluation is run
while the follow-up labels remain incomplete.
