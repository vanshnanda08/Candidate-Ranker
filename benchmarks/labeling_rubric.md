# Senior AI Engineer: relevance labeling rubric

Use the supplied evidence as of **2026-11-13** and the actual JD in
`pipeline/jd_parser.py` (`JD_RAW`). This pilot measures evidence of role fit;
profiles are self-reports, not verified employment histories. Treat missing
information as uncertainty, not proof that a candidate lacks a skill.

## Essentials and alternatives

- Senior hands-on engineering level: the JD asks for 5–9 years overall and about
  4–5 years of applied ML/AI at product companies. Look for dated responsibilities
  and relevant ownership, not title alone. Additional experience is not itself
  a negative. A material shortfall in relevant experience is a gap.
- Production embeddings-based retrieval. Sentence Transformers, BGE, E5 and
  OpenAI embeddings are alternatives, not four separate boxes. A comparable
  embedding stack with explicit production retrieval evidence can satisfy this.
- Vector databases **or hybrid search**. Pinecone, Weaviate, Qdrant, Milvus,
  Elasticsearch and FAISS are example alternatives. Do not demand every tool,
  or both a vector database and hybrid search. Explain a comparable alternative.
- Strong hands-on Python and code quality: implementation, tests, maintainability,
  reliability or owned production components. A Python tag alone is weak evidence.
- Ranking evaluation: concrete offline/online evaluation responsibilities and
  decisions. NDCG, MRR and MAP are alternative metrics; they are not all mandatory.
  A/B tests, offline-to-online validation, or a clearly described comparable
  evaluation process can substantiate the requirement. A bare metric name does
  not establish an evaluation framework.
- Shipped an end-to-end **ranking, search, or recommendation** system to real users
  at meaningful scale. These system types are alternatives. Describe personal
  ownership, deployment and users/traffic/operational scope. Do not require an
  arbitrary traffic number absent from the JD.

Role context: Pune/Noida hybrid, with openness to Hyderabad, Mumbai and Delhi NCR.
Record disclosed constraints in the reason; missing logistics alone is not proof
of an engineering gap. An explicit inability to meet the stated work arrangement
is a material role constraint. Do not infer willingness from the current city.

The JD explicitly excludes research-only careers without deployment, recent
wrapper-only AI experience without prior ML production, no production coding in
18 months, an entire consulting/services career without product-company
experience, and CV/speech/robotics-only expertise without NLP/IR experience.
Apply these only when the available responsibilities/timeline establish them;
an incomplete profile, employer brand or job title alone is insufficient.
Employer names are blinded. The packet includes disclosed industry/size and
whether an employer is explicitly on the JD's consulting list; other employers'
product status is unconfirmed, not automatically positive.

## Nice-to-haves

LLM fine-tuning (LoRA/QLoRA/PEFT as alternatives), learning to rank (e.g. XGBoost or
neural LTR), HR-tech/recruiting/marketplace experience, distributed systems and
inference optimization, and AI/ML open-source work. Concrete writing/async work
can strengthen an otherwise supported match. Nice-to-haves cannot replace core
production retrieval, evaluation or hands-on engineering evidence. Do not infer
future tenure intentions from job changes alone.

**Exclude** recruiter views/saves, endorsements, platform activity/response rates,
recent activity, school prestige, names and contact information from relevance
judgments. No school fields or platform-engagement fields are supplied. Skill
self-ratings and certifications alone do not establish production proficiency.

## Grades

| Grade | Meaning |
|---|---|
| 3 | Clear, specific evidence of all technical essentials at the required level, including production retrieval, personal Python ownership, evaluation and shipping. |
| 2 | Credible match for most essentials, with one material gap or limited evidence in one area. State that area. |
| 1 | Some relevant experience, with clear gaps across multiple essentials; e.g. prototypes without production ownership and evaluation. |
| 0 | The available evidence shows little/no fit or clearly establishes a JD exclusion. Do not use 0 simply because fields are missing. |
| U | Too little substantive evidence to judge. A title and keyword list without responsibilities/timeline may warrant U, even if the keywords match. |

Read the whole profile. Grade evidence, not keyword counts. For partial but
substantive profiles use 1/2 as appropriate and name the missing area; use U when
there is no basis to distinguish a weak match from an undocumented strong match.
In `reason`, cite the responsibilities/skills and key gaps; do not invent facts.
Keep source evidence unchanged. Fill only `relevance_grade` and `reason`.

## Fictional boundary examples (not actual candidates)

- **3 vs 2:** Seven years overall, five in applied ML at a product firm; personally
  shipped Python semantic search using E5 + FAISS, owns tests/deployment and
  evaluates with MRR plus online experiments. **3**. Same history but no substantive
  evidence of evaluation design/ownership: **2**, with evaluation unconfirmed.
- **2 vs 1:** Six years of Python product engineering; shipped retrieval with
  Pinecone and owns offline evaluation, but has only two years of applied ML:
  **2**, with relevant seniority a material gap. Six years of general engineering
  plus a small retrieval demo, with no production retrieval or evaluation:
  **1**.
- **1 vs 0:** A data engineer built a relevant Python search prototype but has
  no production retrieval/evaluation ownership: **1**. A well-documented career
  entirely in unrelated marketing, with no relevant engineering evidence: **0**.
- **0 vs U:** A detailed research-only profile explicitly states there has been
  no deployment or production coding: **0** under the JD. An otherwise empty
  profile saying only “Senior AI engineer; Python, LLMs”: **U**, not 0.

Fictional completed row (other evidence columns omitted here only):

```csv
review_id,relevance_grade,reason
R-FICTIONAL,2,"Owned production E5/FAISS retrieval and Python deployment; evaluation responsibilities are not documented."
```

## Later evaluation

After human labeling/adjudication, this **one-role pilot** can support a pooled
NDCG@10 comparison: all three methods' top 10 are in the pool. Use the same judged
pool to define the ideal ranking, document the gain convention, and resolve or
report U judgments explicitly rather than silently treating them as 0. The pool
is deliberately sampled, not an exhaustive relevance set. Any later recall must
use the known relevant candidates **in the judged pool** as its denominator;
most of the 100,000 candidates remain unjudged. No metrics, tuning or training
are performed in this phase.
