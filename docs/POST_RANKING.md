# Local post-ranking workflow

Filtering, comparison and shortlisting use only the returned ranking and the
submitted job/dataset snapshot. No backend or scoring changes are needed. Editing
the next job draft never reinterprets the existing results.

- **Filters for returned results** searches current titles and recorded matched
  skills. Experience bounds are inclusive, and the requirement dropdown selects
  an exact recorded match for a submitted required/preferred skill. Filters combine
  with AND, preserve response order/rank numbers and make no API calls. Reset clears
  every filter. Chart/statistics and the original submission export cover the full
  response even while cards are filtered.
- **Compare candidates** accepts at most three selections. Filters do not change
  selections. A successful replacement ranking resets comparison and filters;
  failed requests retain the existing workspace. Comparison lists each required
  and preferred skill and either its recorded match or **No matching evidence**.
  That phrase describes missing recorded evidence, not a demonstrated inability.
  The built-in response records required matches only, so preferred matches are
  not inferred from unrelated fields. On narrow screens comparison cards stack.
  Native buttons/checkboxes/selects support Tab, Space/Enter and arrow keys, with
  visible focus indicators and descriptive labels.
- **Shortlist** is a dedicated view available even before ranking. Add/remove from
  results or comparison; edit notes or remove entries in the saved view. Notes
  save on each edit. A refresh restores saved lists without storing a full ranking
  or rerunning inference. Use the job/dataset selector to open an older list.

## Persistence and scope

The browser's localStorage key is `talentlens.shortlists.v1`. Managed demo/upload
selection is now available directly in the dashboard; see the main README. Each list contains
its submitted job context (mode, title, exact description, required/preferred
lists and experience bounds) and dataset selection (exact path and sample/JSONL
format). Managed datasets additionally retain the backend's validated-content
SHA-256 fingerprint; it replaces the path/filename in their scope identity. Two
uploads with the same filename but different content are separate, and identical
validated content shares a scope. Existing path-scoped lists remain readable.
Object key order is canonical; a title alone is never the identity.
Same-title jobs with different requirements/descriptions are separate. Rank limits,
Claude settings and scoring date do not create separate lists for the same
job/dataset. Legacy advanced paths retain their original behavior: file contents
are not fingerprinted for those old scopes, and changing a file in place keeps
that path-selection scope. Managed uploads use content identity instead.

Each saved candidate contains only `candidate_id`, `title`, `original_rank` and
`notes` (up to 5,000 characters). Original rank is a snapshot at the time of adding;
reranking does not silently overwrite saved ranks or notes. Remove/re-add to capture
a new rank. Names, contact details, full profiles, scores and comparison/filter state
are not persisted. No saved data is sent to the backend. Lists are specific to the
browser origin, so changing ports/origins or clearing site data changes availability.
Multiple tabs do not coordinate concurrent edits; the latest successful save wins.

Missing storage starts empty. Unavailable/denied storage, invalid JSON/schema,
duplicate IDs/scopes or quota failures show a message while the ranking and
in-memory shortlist remain usable. Mounting does not overwrite invalid saved data;
an explicit new shortlist edit can replace it if storage works. Export in-memory
changes before closing if saving fails. Versioned validation strips unneeded fields.

## Two separate exports

`shortlist.csv` contains `candidate_id,title,original_rank,notes`. Text fields use
RFC-style double-quote escaping; embedded commas, quotes, CR/LF and multiline notes
are retained. A leading apostrophe neutralizes spreadsheet formula prefixes
`=`, `+`, `-`, `@`, including after leading whitespace/control characters. Leading
tab/CR/LF also triggers protection. This protective character is an export-only
change; saved notes are untouched. All text columns are protected, including titles
and candidate IDs. Rank stays numeric.

The existing `submission.csv` builder is unchanged and uses all returned rows,
original ranks and scores, regardless of filters or shortlist membership.

## Fictional local demo

From the workspace root, create a new temporary file (the script refuses overwrites):

```bash
.venv/bin/python scripts/make_post_ranking_demo.py --out /tmp/talentlens-post-ranking-demo.json
```

In two terminals:

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python -m uvicorn server:app --host 127.0.0.1 --port 8000
```

```bash
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Open <http://127.0.0.1:5173>. For this legacy-path walkthrough, expand **Legacy local
path settings**, set the dataset path to the generated file and keep
**Sample JSON** checked and Claude disabled. Choose **Custom job**:

```text
Title: Platform Engineer
Description: Build reliable Java services and relational data products.
Required: Java, PostgreSQL
Preferred: Docker
Minimum experience: 3
Maximum experience: 10
```

1. Run Ranking. Search `PostgreSQL`, then filter experience `5`–`8` and requirement
   `PostgreSQL`. The returned ranks stay unchanged. Try an unmatched search to see
   the no-results message, then Reset filters.
2. Select three Compare checkboxes (Space works when focused); the fourth becomes
   disabled. Change a filter: comparison stays intact. Inspect required/preferred
   evidence, then remove one candidate from comparison.
3. Add candidates from results and comparison to the shortlist. Open **Shortlist**,
   enter notes containing a comma, quotes and a new line; try a note starting `=`.
   Refresh. The saved view recovers entries and notes without a ranking request.
   Export `shortlist.csv`.
4. Re-enter the same title `Platform Engineer` with description `Create visual brand
   identities and accessible design assets.`, required `Figma, Illustrator`, and no
   preferred skills. Use the same dataset and run. Comparison is empty and the new
   shortlist starts empty. The saved-job selector can still open the first list.
5. Switch to **Built-in: Senior AI Engineer** and run the fictional dataset. Check
   the built-in job heading, filter/compare controls, and download submission.csv.
   Its header is `candidate_id,rank,score,reasoning` and it contains all four returned
   rows even if a local filter hides some. This fixture demonstrates workflow, not
   ranking quality for the built-in role.

The embedding model must already be available locally for offline real-model runs.
The fictional four-profile candidate cache is new and local; existing caches and
benchmark datasets are untouched. Keep demo files/exports local, outside Git.

## Verification commands

```bash
cd frontend
npm test
npm run build
npm run lint
```

From the workspace root:

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python -m unittest discover -s tests -v
```

With the local backend running, run the additional React DOM integration against
the real API and fictional file (from `frontend/`):

```bash
TALENTLENS_DEMO_DATASET=/tmp/talentlens-post-ranking-demo.json npm run test:local-api
```

This opt-in test performs three real rankings (custom job A, same-title custom job B,
built-in), local filtering/comparison, saved-note recovery after remount, job isolation
and both CSV exports. It does not call Claude or use production candidate files.

Frontend tests use Node's built-in test runner and TypeScript support (the existing
Node 24 installation), the existing TypeScript compiler, and the new **dev-only
jsdom** dependency for React DOM integration. No existing dependency versions were
changed. Tests use fictional profiles and injectable in-memory/throwing storage.
They cover filtering and original
ranks, comparison limits, full job/dataset isolation, minimal persisted snapshots,
notes recovery, invalid/unavailable/full storage, and shortlist versus submission
CSV behavior. DOM integration mounts the dashboard, submits mocked ranking responses,
filters/compares, saves notes, remounts to simulate refresh, switches same-title jobs,
and captures both download Blobs. It also exercises denied/malformed storage. These
tests verify functional behavior, not pixel layout or native keyboard event defaults.
The separate real-API DOM workflow uses the four fictional profiles with the local
model and Claude off, and captures the actual download Blobs from the dashboard.
The original Phase 5B browser automation host/window capture was unavailable.
That gap is now closed with `npm run test:browser`: real local Chrome tests pass at
1440×1000 and 390×844, including keyboard focus, actual page reload, upload-based
content isolation, comparisons and both file downloads. The Benchmark view uses a
table on desktop and complete metric cards on narrow screens.
