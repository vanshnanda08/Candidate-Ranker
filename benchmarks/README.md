> Historical experiment instructions. Set `REVIEW_ROOT` to your own private review directory. Private labels, manifests and datasets are not bundled.

# Local Senior AI Engineer review pilot

Start with [the labeling rubric](labeling_rubric.md). Production ranking and caches
are read-only inputs. Nothing here is imported by the production CLI/API.

## Generate or resume

From the workspace root, using the existing Python 3.12 environment:

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python -m benchmarks.build_review_set \
  --candidates candidates.jsonl --as-of 2026-11-13 --seed 20261113 \
  --output-dir ${REVIEW_ROOT}/senior-ai-engineer-2026-11-13
```

The output directory must be outside the Git workspace. `reviewer.csv` and
`manifest.json` remain local and have owner-only file permissions when created.
A cache miss/invalid array stops generation for diagnosis: no model is loaded,
no network request or full encode is attempted, and no cache is written.

On rerun, identical inputs produce identical evidence, review IDs and row order.
Existing `relevance_grade` and `reason` values are preserved verbatim by review ID,
even if you sorted the CSV. A changed configuration, changed evidence, duplicate
IDs or invalid labels stops the generator without overwriting the files. Use a
new directory for a different seed/dataset/JD/code version. Close the CSV editor
before rerunning to avoid concurrent edits. The manifest includes source hashes,
so code/rubric changes are deliberately treated as a new review version.

## Sampling and baselines

- Hybrid: the existing shared `rank_candidates`, top_n=10, coarse_n=500,
  as_of=2026-11-13, use_llm=False, llm_n=0, verified real MiniLM embeddings.
  Existing 30/40/20/5/5 base weights, honeypot multiplier and deterministic final
  normalization/tie ordering are unchanged. Its engagement features remain part
  of this baseline; they are deliberately not evidence for human relevance grades.
- Semantic: descending cached cosine similarity over all records, with ID
  ascending for exact ties, using the existing embedding JD text.
- Keyword: five equally weighted binary lexical groups (0–5). Four groups cover
  embedding retrieval; vector database or hybrid search; Python; and evaluation.
  The fifth requires both a shipping term (production/deployed/shipped) and a
  system term (retrieval/ranking/search/recommendation). Alternative tools and
  repeated matches within a group count once. Exact term lists and source-field
  names are stored in the manifest and `KEYWORD_GROUPS` in the generator.
  Matching is case-folded, hyphens normalized to spaces, and phrase/token bounded;
  `map` does not match `roadmap`. This is a lexical proxy, not evidence of
  ownership, evaluation quality, product experience or seniority. It does not
  assess all rubric essentials. Exact ties use ascending candidate ID.
- Mandatory pool: union of all three top 10s, deduplicated with all provenance
  tags retained. Add semantic ranks **496–505** inclusive, straddling the top-500
  shortlist cutoff. Fill to **50 unique candidates** from semantic ranks >500,
  excluding selected candidates.
- Seeded sample: sort eligible IDs by SHA-256 of JSON `[seed, "outside-sample",
  candidate_id]` and take the needed number without replacement. Shuffle the
  whole reviewer pool with a separate `"review-shuffle"` domain. These seeded
  pseudorandom priorities are stable across reruns and independent of source
  file iteration order. Semantic ranking ties still depend explicitly on IDs.

The manifest records the exact dataset byte SHA-256, JD raw text/requirements and
embedding text, model revision, cache identities/hashes, source hashes,
parameters, top-10 lists, method scores, sampled IDs and review-ID mapping.
Keep it separate from the reviewer during grading to avoid selection-method bias.
Counts by selection tag overlap; they should not be summed as unique people.

## Reviewer handoff

Open **reviewer.csv** alongside the rubric. Fill only:

- `relevance_grade`: `3`, `2`, `1`, `0`, or `U` when evidence is insufficient.
- `reason`: a short evidence-based explanation with the main gap/uncertainty.

Keep `review_id` and all evidence unchanged. Blank means unreviewed; `U` is an
explicit judgment and should have a reason. Structured skills/career cells are
JSON so responsibilities, dates and durations remain associated. Names,
contacts, schools/prestige, engagement fields, method provenance, ranks and
ranking scores are omitted. Known identity/employer/institution names and
contact tokens in free text are redacted. Employer-list context is derived from
the project's JD consulting-company list, not independent verification.

Fictional completed example (not an actual pool label):

```csv
review_id,relevance_grade,reason
R-FICTIONAL,2,"Owned Python retrieval deployment using E5 and FAISS; evaluation ownership is undocumented."
```

## Checks and later evaluation

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python -m unittest discover -s tests -v
```

Tests cover mandatory top-10 inclusion, unique/stable IDs, cutoff and outside
sampling, seeded reproduction, lexical alternatives, blinding, blank grades,
annotation preservation, protective failures and cache-only operation. All
existing production regression tests are included.

After labeling/adjudication, this one-role pilot supports **pooled NDCG@10** for
these three recorded runs. Agree on gain mapping and handling of U first. It is
not an exhaustive judgment set or a population-level quality estimate. Any
recall reported later must use known relevant candidates **in the judged pool**
as its denominator; the remaining dataset is unjudged. No metrics, weight tuning
or model training are implemented here.
