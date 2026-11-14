# Final local release verification

Verified 2026-11-14. This clean copy includes the Phase 6B design and Candidate Ranker browser title. Technical checks pass. The owner subsequently confirmed permission and authorized publication; see PUBLICATION_STATUS.md. This documentation update changes no tested application code.

## Source selection and fixes

The requested `fe7f38c` object was not available in either inspected repository. The actual prepared snapshot was `83c0d86`. The original working tree had no newer source changes compared with that snapshot's recorded baseline. This copy starts from its sanitized tracked files, preserving its dependency fixes, fictional sample, required notices, font licenses and test-fixture corrections. It does not import either repository's history.

Two reproduced issues were addressed here:

1. Opening Vite before the API's initial imports completed caused failed initial data fetches. README now requires waiting for startup completion and checking `/api/health` before opening the dashboard, with reload guidance if it was opened early.
2. A browser-simulated failed ranking connection displayed only `Failed to fetch`. The API client now gives an actionable server/retry message, while intentional cancellation retains its identity. Two unit tests and a desktop/mobile first-user regression cover it. On failure, the previous results retain their original submitted job; retry submits the new draft and replaces results only after success.

No hybrid scoring, embedding input, scoring weight, tie-breaking, output schema or benchmark value was changed. The visual theme and shortlist storage keys/formats remain intact.

## Clean setup and first run

A fresh Python 3.12.14 virtual environment was installed from the README's tested requirements-lock.txt option, with no system-site packages. `pip check` passed. A fresh `npm ci` installed the verified lockfile. All server/ranking/browser processes had ANTHROPIC_API_KEY unset; Claude was off in requests. No browser profile, model files or application embeddings were copied into this release.

With an empty HF_HOME and absent application embedding cache, the online API's first real Chrome ranking downloaded the pinned model and encoded JD plus 50 fictional profiles. It returned 20 candidates in **26.681 s** browser wall time. The repeat returned identical result objects in **0.395 s**, with candidate and JD cache hits confirmed in the logs. These one-run observations include HTTP/browser waiting and are correctness/runtime checks, not performance guarantees. The first user's normal local-date default was 2026-11-14; the separate CLI/API and full-run checks explicitly used 2026-11-13.

For an immediate first online API run, omit the offline environment flags from the README API command. The README's explicit model predownload followed by offline API startup is the alternative for reproducible offline use. Both require network only for the initial public model download.

## Final checks

| Check | Result |
|---|---|
| Fresh Python installation; pip check | Pass |
| Fresh npm ci; full and omit-dev audits | Pass; zero vulnerabilities |
| Backend offline regression suite | 105 passed |
| Frontend unit/DOM suite | 23 passed |
| Installed Chrome desktop/narrow suite | 10 passed in 40.4 s |
| Frontend lint/build | Pass; existing 500 kB chunk advisory remains |
| Default CLI/API parity | Same top-20 IDs, order and displayed scores; explicit 2026-11-13 date, Claude off |
| Cache identity/invalidation | Tests cover hits, changed IDs/text/order, JD text/requirements, model/revision, invalid arrays and same-path updates |
| Custom criteria | Real browser: Backend Engineer selects the fictional backend profile, Brand Designer selects the fictional design profile, with appropriate skill evidence/reasoning |
| Failure/retry | Old results retain Backend Engineer context while Brand Designer fails; retry succeeds and switches context |
| Uploads | Valid count, malformed JSON, invalid records and oversized file guidance pass |
| Review workflow | Local filters/rank retention, comparison, keyboard/focus, reduced motion, notes after refresh, same-title job and same-filename upload isolation, both downloads pass |
| Benchmark | Original aggregate bytes and single-role caveat preserved; hybrid remains default |

The first-user browser scenario runs in a new browser context for both 1440×1000 and 390×844. Existing suites also verify both downloaded CSV contents, formula escaping, all-returned submission export under filters, long requirement fit and no page-level horizontal overflow. No live Claude call was made.

## Private full-dataset correctness/runtime check

The local 100,000-profile dataset was available outside the release. A preflight verified exact content/order/model/revision cache identity and valid arrays. The warm CLI used those original cache entries read-only, with the model's encode method patched to fail on any miss. It selected top 100 with coarse_n=500, Claude off and date 2026-11-13. Preflight took **3.989 s**; the timed `rank.main` call took **7.421 s** (CLI internal timer 7.0 s). These scopes exclude process import time. `validate_submission.py` passed on the temporary 100-row CSV. No full encode occurred, and no records/output/cache files are in this snapshot. This does not refresh the frozen benchmark artifacts or claim a quality improvement.

## Commands

Follow the root README clean setup. From the release root:

```bash
export HF_HOME="$PWD/.model-cache"
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m pip check
mkdir -p .release-local
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python rank.py --candidates sample_candidates.json --sample --top-n 20 --coarse-n 500 --llm-n 0 --no-llm --no-cache --as-of 2026-11-13 --out .release-local/sample-cli.csv
cd frontend
npm test
npm run lint
npm run build
npm audit --json
npm audit --omit=dev --json
npm run test:browser
```

The executed Chrome command additionally set TALENTLENS_CHROME_PATH to installed Google Chrome, HF_HOME to the fresh release model directory, and browser-output/upload directories outside the public snapshot. ANTHROPIC_API_KEY was unset. The runner starts/stops both servers; ports 8000 and 5173 must be free first. The full private-data command and logs remain in the separate local verification report, not in public source.

## Dependencies and permission gate

No new npm findings were reported; the prepared snapshot's compatible Vite/PostCSS and transitive tooling fixes remain. The build emits approximately 585.21 kB minified JavaScript / 173.90 kB gzip, retaining the known chunk-size advisory. No forced major upgrade or blanket install-script permission was used. Font licenses retain their original bytes.

The exact target https://github.com/vanshnanda08/Candidate-Ranker.git was inspected and had no refs. The release has fresh local history and that remote configured; the original upstream remote is untouched. Upstream main remains at 229dd6a8c8c7594b906a0cbe2f7c38e15186eb25 with no repository license/notice file found. The initial inherited-code/JD publication gate was subsequently addressed by the owner confirming that they have permission and instructing the push. The underlying agreement is not bundled or independently reviewed. Font notices and the tested code remain unchanged; optional personal-name credits were subsequently removed at the project owner’s request; no blanket open-source license is inferred.
