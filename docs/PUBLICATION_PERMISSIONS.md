# Publication permission evidence — local draft

Checked 2026-11-14. **Unresolved; do not publish this mixed snapshot yet.** This inventory records observed notices, not a legal opinion or a substitute for a rights-holder grant.

## Upstream application code

Source: [Udhey-Goyal/TalentLens-AI](https://github.com/Udhey-Goyal/TalentLens-AI), formerly redrob-ai-ranker. The checked upstream main revision is `229dd6a8c8c7594b906a0cbe2f7c38e15186eb25`. The GitHub repository metadata has `license: null`, and its recursively listed tree has no LICENSE/COPYING/NOTICE grant. The local original tracked README credits Udhey Goyal and mentions the Redrob AI Hiring Challenge, with educational/portfolio sharing language. That statement does not specify rights to modify, sublicense or redistribute a derivative release.

Evidence: inspected local tracked README and notices, the nested source copy, archive member list, and upstream repository metadata/tree at the pinned revision. No separate challenge terms, redistribution agreement or license file was found in those local materials. Original Git commits were not copied. Attribution remains in README.md and NOTICE.md.

**Needed:** an explicit license or written permission from the upstream rights holder covering the inherited source and modified/derived versions, public GitHub redistribution, and required notices. Newly rewritten files may contain derived integration code; ownership should be settled before applying a blanket license.

Inherited or derived files retained in this draft:

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

`pipeline/jd_parser.py` contains the built-in Senior AI Engineer JD and challenge-specific structured requirements; `validate_submission.py` implements challenge format rules and refers to challenge sections. `benchmarks/labeling_rubric.md` and `benchmarks/grouped_skills_spec.json` summarize this role's requirements. No separate applicable challenge publication terms were available locally. **Needed:** rights-holder confirmation or applicable terms permitting public reproduction of the JD/challenge material. Scoring and JD text are preserved to avoid changing benchmarked behavior while permission remains unresolved.

## Fonts — permission evidence present

Unmodified `frontend/public/fonts/instrument-sans.ttf` and `instrument-serif.ttf` are accompanied by the complete original `instrumentsans-OFL.txt` and `instrumentserif-OFL.txt`. Both identify the respective Instrument Project Authors, Copyright 2022, and SIL Open Font License 1.1. Bundling is permitted subject to its conditions; notices remain alongside the font files, and the fonts are not relicensed under an application license or sold separately.

Primary sources: [Sans OFL](https://github.com/google/fonts/blob/main/ofl/instrumentsans/OFL.txt), [Serif OFL](https://github.com/google/fonts/blob/main/ofl/instrumentserif/OFL.txt). No font modification or remote runtime font service was introduced.

## Data and images

- Original `sample_candidates.json`, original dashboard/ranking PNGs, the private full dataset, original submission.csv, raw review CSVs, labels, manifests, rankings and embedding caches are excluded. No publication rights are asserted for them.
- The release `sample_candidates.json` is generated exactly from `pipeline.demo_data.demo_candidates()` and contains 50 clearly fictional DEMO identifiers and profiles. No private source records are used.
- `assets/desktop-*.png` and `assets/mobile-*.png` are the latest verified Phase 6B captures with those fictional profiles and aggregate-only benchmark data. No original screenshots are reused. Underlying UI/source permissions remain unresolved as above.
- Unused upstream Vite/social SVG assets are omitted. `frontend/public/favicon.svg` is a new simple geometric T mark created for this release.
- The only benchmark data projection is `data/phase4b_aggregate.json`, unchanged from the verified local aggregate report. It contains only role, scoring date, pool size, provenance, metrics and a report hash. It includes no individual labels or candidate mappings. This does not license the excluded private dataset.

## Model and installed dependencies

The pinned model card identifies [all-MiniLM-L6-v2](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/blob/1110a243fdf4706b3f48f1d95db1a4f5529b4d41/README.md) as Apache-2.0. Weights are separately downloaded into ignored local storage, not bundled. Python/npm dependencies are installed from their package registries and not vendored in the public file list; their existing licenses remain applicable. The three direct frontend runtime packages (React, React DOM, Recharts) declare MIT in the installed package metadata. Original font notices are the only third-party binary asset licenses bundled here. If build outputs or dependencies are later redistributed separately, carry all applicable dependency notices too.

## User-owned contributions — decision pending

No license has been invented for the user's new code. After the inherited-code/JD permissions are established, choose a license for solely owned contributions (for example MIT) and identify exclusions/compatibility for inherited material. Required decision: whether the user wants MIT for solely owned new code and has authority to grant it. This decision does not resolve upstream or challenge permission gaps.
