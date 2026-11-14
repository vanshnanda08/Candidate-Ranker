# Publication provenance and owner-confirmed permission

The initial checks below identified an inherited-code/JD permission gate. The project owner subsequently confirmed: “i have the permission for this push it”. Publication of this verified release is proceeding on that confirmation. The underlying agreement was not provided or independently reviewed; no additional license terms or downstream rights are inferred. See ../PUBLICATION_STATUS.md.

The following retains the provenance findings from 2026-11-14; absence of a public repository license is still a factual observation.

## Upstream application code

The checked upstream revision is `229dd6a8c8c7594b906a0cbe2f7c38e15186eb25`. Its repository metadata reported `license: null`, and its recursively listed tree had no LICENSE/COPYING/NOTICE grant. The original README mentions the Redrob AI Hiring Challenge and educational/portfolio sharing. These are historical provenance observations, not a blanket license grant.

The original tracked README, notices, nested source copy, archive member list and upstream metadata/tree were inspected. No separate challenge terms or redistribution agreement was present in those materials. The project owner subsequently confirmed publication permission and requested removal of personal-name references and credit links. Those optional references have been removed from the current files; ownership claims and required third-party notices are unchanged. Original Git commits were not imported into the release.

**Initial gate:** permission covering inherited source and modified/derived versions, public GitHub redistribution, and required notices. The owner has confirmed having the permission needed for this push. No broader right to sublicense or relicense is inferred.

Inherited or derived files included in the owner-authorized release:

- `.gitignore`
- `app.py`
- `frontend/.gitignore`
- `frontend/.oxlintrc.json`
- `frontend/index.html`
- `frontend/package-lock.json`
- `frontend/package.json`
- `frontend/postcss.config.js`
- `frontend/src/App.tsx`
- `frontend/src/api.ts`
- `frontend/src/components/CandidateCard.tsx`
- `frontend/src/components/ControlsPanel.tsx`
- `frontend/src/components/JdPanel.tsx`
- `frontend/src/components/ScoreBar.tsx`
- `frontend/src/components/ScoreChart.tsx`
- `frontend/src/components/StatsHeader.tsx`
- `frontend/src/csv.ts`
- `frontend/src/index.css`
- `frontend/src/main.tsx`
- `frontend/src/types.ts`
- `frontend/tsconfig.app.json`
- `frontend/tsconfig.json`
- `frontend/tsconfig.node.json`
- `frontend/vite.config.ts`
- `pipeline/__init__.py`
- `pipeline/behavioral.py`
- `pipeline/encoder.py`
- `pipeline/feature_scorer.py`
- `pipeline/honeypot.py`
- `pipeline/jd_parser.py`
- `pipeline/llm_reranker.py`
- `pipeline/loader.py`
- `rank.py`
- `requirements.txt`
- `server.py`
- `validate_submission.py`

## Challenge text and rules

`pipeline/jd_parser.py` contains the built-in Senior AI Engineer JD and challenge-specific structured requirements; `validate_submission.py` implements challenge format rules and refers to challenge sections. `benchmarks/labeling_rubric.md` and `benchmarks/grouped_skills_spec.json` summarize this role's requirements. No separate applicable challenge publication terms were available locally. **Initial gate:** permission to publish the JD/challenge material. The owner has confirmed publication permission for this release. Scoring and JD text remain unchanged to preserve benchmarked behavior.

## Fonts — permission evidence present

Unmodified `frontend/public/fonts/instrument-sans.ttf` and `instrument-serif.ttf` are accompanied by the complete original `instrumentsans-OFL.txt` and `instrumentserif-OFL.txt`. Both identify the respective Instrument Project Authors, Copyright 2022, and SIL Open Font License 1.1. Bundling is permitted subject to its conditions; notices remain alongside the font files, and the fonts are not relicensed under an application license or sold separately.

Primary sources: [Sans OFL](https://github.com/google/fonts/blob/main/ofl/instrumentsans/OFL.txt), [Serif OFL](https://github.com/google/fonts/blob/main/ofl/instrumentserif/OFL.txt). No font modification or remote runtime font service was introduced.

## Data and images

- Original `sample_candidates.json`, original dashboard/ranking PNGs, the private full dataset, original submission.csv, raw review CSVs, labels, manifests, rankings and embedding caches are excluded. No publication rights are asserted for them.
- The release `sample_candidates.json` is generated exactly from `pipeline.demo_data.demo_candidates()` and contains 50 clearly fictional DEMO identifiers and profiles. No private source records are used.
- `assets/desktop-*.png` and `assets/mobile-*.png` are the latest verified Phase 6B captures with those fictional profiles and aggregate-only benchmark data. No original screenshots are reused. Publication proceeds on the owner confirmation described above.
- Unused upstream Vite/social SVG assets are omitted. `frontend/public/favicon.svg` is a new simple geometric T mark created for this release.
- The only benchmark data projection is `data/phase4b_aggregate.json`, unchanged from the verified local aggregate report. It contains only role, scoring date, pool size, provenance, metrics and a report hash. It includes no individual labels or candidate mappings. This does not license the excluded private dataset.

## Model and installed dependencies

The pinned model card identifies [all-MiniLM-L6-v2](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/blob/1110a243fdf4706b3f48f1d95db1a4f5529b4d41/README.md) as Apache-2.0. Weights are separately downloaded into ignored local storage, not bundled. Python/npm dependencies are installed from their package registries and not vendored in the public file list; their existing licenses remain applicable. The three direct frontend runtime packages (React, React DOM, Recharts) declare MIT in the installed package metadata. Original font notices are the only third-party binary asset licenses bundled here. If build outputs or dependencies are later redistributed separately, carry all applicable dependency notices too.

## Application license scope

No blanket application license has been selected or invented. The owner has authorized publication on the basis of permission they hold; that does not specify downstream reuse or relicensing terms. The bundled fonts retain OFL 1.1 and separately installed dependencies retain their own licenses.
