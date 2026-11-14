# Custom jobs in the local dashboard

The dashboard starts with **Built-in: Senior AI Engineer**. Its embedding text,
scoring functions, weights, date default, ordering, normalization and CLI remain
unchanged. Choose **Custom job** to enter a title, description, required skills,
preferred skills and optional minimum/maximum years of overall experience. Click
**Run Ranking** in Settings. Each result retains the submitted job even if the
draft is later edited. Expand **Submitted requirements and scoring** to inspect
the job that produced that result. CSV columns remain
`candidate_id,rank,score,reasoning`.

## Run locally

From the tracked project root, in two terminals:

```bash
.venv/bin/python -m uvicorn server:app --host 127.0.0.1 --port 8000
```

```bash
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Open <http://127.0.0.1:5173>. Keep the sample path and Claude unchecked. Select
**Custom job**; try title `Backend Engineer`, description `Build reliable Java
services backed by PostgreSQL.`, required skills `Java, PostgreSQL`, preferred
skills `Docker`, and experience `3` to `10`. Skills accept commas or new lines.
The backend validates the submitted values; errors appear next to the affected
fields and in an alert. Returning to the built-in selection submits `job: null`.
Forms are not saved between browser reloads.

## API

`POST /api/rank` accepts an optional `job` object. Omission or `null` selects the
built-in role. All existing request fields remain available, including `as_of`:

```json
{
  "data_path": "sample_candidates.json",
  "is_sample": true,
  "top_n": 20,
  "coarse_n": 500,
  "use_llm": false,
  "as_of": "2026-11-13",
  "job": {
    "title": "Backend Engineer",
    "description": "Build reliable Java services backed by PostgreSQL.",
    "required_skills": ["Java", "PostgreSQL"],
    "preferred_skills": ["Docker"],
    "experience_min": 3,
    "experience_max": 10
  }
}
```

Title: 1–160 characters, containing letters/numbers. Description: 20–20,000
characters. Each skill list: at most 50 nonblank phrases of at most 100 characters,
containing letters/numbers. Surrounding whitespace is trimmed. Normalized duplicate
skills across either list are rejected rather than counted twice. Bounds may be
omitted independently; supplied values must be finite numbers from 0 to 80, with
minimum ≤ maximum. Unknown custom-job fields are rejected. Invalid jobs return
HTTP 422 before the dataset is read or the model is loaded.

Responses add `job` with `mode`, submitted title/description, structured inputs,
and `scoring_notes`. Existing result fields remain intact. `/api/jd` continues
to expose the built-in JD; it is not mutable shared state.

## Custom scoring and omitted criteria

Custom jobs use a separate scorer; the benchmarked built-in scorer is not
reconfigured. The structured skill lists are authoritative, with no automatic
JD parsing, alias expansion or Phase 4 grouped-skill integration.

| Component | Custom behavior |
|---|---|
| Semantic retrieval | Title + description + supplied skill lists/bounds, serialized in a fixed order. |
| Skills | Literal phrase matches in `skills[].name`, case insensitive, hyphens/whitespace normalized and token boundaries enforced. `Java` does not match `JavaScript`; repeated candidate tags count once. Required coverage gets 75%, preferred 25%; an absent list's share is redistributed to the supplied list. Both absent → constant 0.5. Existing 0.85 poor-assessment multiplier is scoped to matching job skills. |
| Career | 40% overlap between submitted title words and current/past titles, 60% coverage of supplied skill phrases in the profile summary and work descriptions. Title-level words senior/junior/lead/principal/staff are ignored. Without skills, use title overlap alone; without substantive title words, use neutral 0.5. No inherited AI keyword, industry, consulting or company-size preferences. |
| Experience | Within supplied bounds → 1; below minimum → 0.5; above maximum → 0.7. Omitted bounds are unrestricted; both absent → constant 0.5. No inferred ideal subrange. |
| Education/location | No inputs for these criteria in this phase → constant 0.5 each. No inherited Indian-city or school-tier preferences. |
| Behavioral / consistency | Existing availability, activity, notice, engagement, GitHub/trust signals and honeypot consistency checks stay unchanged. These are shared profile signals, not inferred custom requirements. |

Structured weights remain skills 0.35, career 0.35, experience 0.15, education
0.05, location 0.10. Final weights remain semantic 0.30, structured 0.40,
behavioral 0.20, skills 0.05, career 0.05, multiplied by the existing honeypot
penalty. Neutral contributions retain these weights and are constant across
candidates. Date resolution, shortlist cutoff and deterministic tie rules remain
shared. Displayed scores are normalized within the selected result, not calibrated
for comparisons between jobs. Literal matches are evidence indicators, not a
verification of proficiency or an entailment/negation detector.

Claude is optional and off by default. Custom reranking receives that request's
job and a role-neutral prompt which treats structured requirements as authoritative
and omitted criteria as unspecified. Default Claude prompts, blend and fallback
remain unchanged. Live Claude calls were not used for verification. Enabling it
uses the existing external Anthropic integration.

## Isolation, caches and frozen experiments

Custom jobs are immutable request objects with tuple skill lists. No request
modifies `JD_REQUIREMENTS` or module-level scoring defaults. Candidate embedding
inputs are unchanged, so their verified caches are reusable across jobs. The
existing versioned JD cache hashes the complete serialized job text plus model
identity/revision; editing the description or structured inputs selects another
JD entry. `cache=False` still bypasses all reads and writes in the shared ranker.

The grouped-skill experiment, reviewer files, labels and frozen artifacts are not
updated. Source fingerprints for modified production files necessarily differ
from older freezes even when default output parity passes. Keep those recorded
hashes as historical evidence; the old strict verifiers should reject the changed
checkout rather than silently refresh the freeze. New Phase 5A verification records
the before/after source hashes and which frozen references differ, outside Git.

Search, candidate comparison, saved shortlists, weight tuning and model training
remain outside this phase.

## Checks

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python -m unittest discover -s tests -v
cd frontend
npm run build
npm run lint
```

Offline fixtures cover two unrelated roles with equal semantic scores, validation,
omitted criteria, phrase boundaries, one-sided experience, sequential and concurrent
request isolation, candidate/JD caching, cache bypass, empty input, and Claude
prompt/blend/fallback. Existing cache, date, ranking and benchmark metric tests run
alongside them. Real-model default parity uses the 50-candidate sample with date
2026-11-13 and Claude disabled, comparing CLI/API IDs, order and displayed scores
against a snapshot taken before these changes.
