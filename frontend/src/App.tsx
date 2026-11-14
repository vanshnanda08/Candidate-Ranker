import { useEffect, useRef, useState } from "react";
import { ApiError, fetchJd, runRanking } from "./api";
import { RankingSettings } from "./components/RankingSettings";
import { ControlsPanel } from "./components/ControlsPanel";
import { JdPanel } from "./components/JdPanel";
import { CustomJobForm } from "./components/CustomJobForm";
import type { JobDraft } from "./components/CustomJobForm";
import { PostRankingWorkspace } from "./components/PostRankingWorkspace";
import { reviewContext } from "./postRanking.ts";
import type { RankingSnapshot } from "./postRanking";
import type { DatasetInfo, JobDescription, RankRequest } from "./types";
import { BenchmarkView } from "./components/BenchmarkView";

const DEFAULT_FORM: RankRequest = {
  dataset_id: "demo",
  data_path: "sample_candidates.json",
  is_sample: true,
  top_n: 20,
  use_llm: false,
  llm_n: 30,
  coarse_n: 500,
};

const EMPTY_JOB: JobDraft = {
  title: "", description: "", required: "", preferred: "", minimum: "", maximum: "",
};

export default function App() {
  const [form, setForm] = useState<RankRequest>(DEFAULT_FORM);
  const [dataset, setDataset] = useState<DatasetInfo | null>(null);
  const [page, setPage] = useState("dashboard");
  const [jd, setJd] = useState<JobDescription | null>(null);
  const [ranking, setRanking] = useState<RankingSnapshot | null>(null);
  const nextRun = useRef(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [custom, setCustom] = useState(false);
  const [draft, setDraft] = useState<JobDraft>(EMPTY_JOB);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    fetchJd()
      .then(setJd)
      .catch((e: Error) => setError(`Failed to load job description: ${e.message}`));
  }, []);

  async function handleRun() {
    if (loading || (form.dataset_id !== null && !dataset)) return;
    setLoading(true);
    setError(null);
    setFieldErrors({});
    try {
      const splitSkills = (value: string) => value.split(/[,\n]/).map((s) => s.trim()).filter(Boolean);
      const payload: RankRequest = { ...form, job: custom ? {
        title: draft.title, description: draft.description,
        required_skills: splitSkills(draft.required), preferred_skills: splitSkills(draft.preferred),
        experience_min: draft.minimum === "" ? null : Number(draft.minimum),
        experience_max: draft.maximum === "" ? null : Number(draft.maximum),
      } : null };
      const data = await runRanking(payload);
      setRanking({ runId: ++nextRun.current, response: data,
        context: reviewContext(data.job, data.dataset ? { data_path: `dataset:${data.dataset.fingerprint}`,
          is_sample: true, fingerprint: data.dataset.fingerprint, label: dataset?.label ?? data.dataset.label }
          : { data_path: payload.data_path, is_sample: payload.is_sample }) });
    } catch (e) {
      if (e instanceof ApiError) setFieldErrors(e.fieldErrors);
      setError(e instanceof Error ? e.message : "Ranking failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Skip to content</a>
      <header className="app-header">
        <div className="page-width header-content">
          <div className="brand"><span className="brand-mark" aria-hidden="true">t.</span>
            <div><h1>TalentLens AI</h1></div></div>
          <nav aria-label="Project views" className="segmented-nav">
            <button type="button" aria-pressed={page === "dashboard"} onClick={() => setPage("dashboard")}>Dashboard</button>
            <button type="button" aria-pressed={page === "benchmark"} onClick={() => setPage("benchmark")}>Benchmark</button>
          </nav>
        </div>
      </header>
      {page === "benchmark" && <main id="main-content" tabIndex={-1} className="page-width page-content"><BenchmarkView /></main>}
      <main id={page === "dashboard" ? "main-content" : undefined} tabIndex={-1} hidden={page !== "dashboard"} className="page-width page-content">
        <div className="dashboard-layout">
        <details className="setup-shell" open>
          <summary><span>Ranking setup</span><span className="setup-chevron" aria-hidden="true">⌄</span></summary>
          <div className="setup-grid">
            <ControlsPanel form={form} onChange={(patch) => setForm((f) => ({ ...f, ...patch }))}
              loading={loading} dataset={dataset}
              onDataset={(id, info) => { setForm((f) => ({ ...f, dataset_id: id })); setDataset(info); }} />
            <CustomJobForm custom={custom} onModeChange={(value) => { setCustom(value); setFieldErrors({}); setError(null); }}
              draft={draft} onChange={(patch) => setDraft((d) => ({ ...d, ...patch }))}
              errors={fieldErrors} loading={loading} onRun={handleRun}><JdPanel jd={jd} /></CustomJobForm>
            <RankingSettings form={form} onChange={(patch) => setForm((f) => ({ ...f, ...patch }))}
              loading={loading} ready={form.dataset_id === null || Boolean(dataset)} error={error} />
          </div>
        </details>
        <div className="review-area" aria-busy={loading}><PostRankingWorkspace ranking={ranking} loading={loading} /></div>
        </div>
      </main>
    </div>
  );
}
