import type { RankRequest } from "../types";

interface Props {
  form: RankRequest;
  onChange: (patch: Partial<RankRequest>) => void;
  loading: boolean;
  ready: boolean;
  error: string | null;
}

export function RankingSettings({ form, onChange, loading, ready, error }: Props) {
  return <section className="setup-step ranking-settings" aria-label="Ranking settings">
    <div className="step-heading"><div><h3>Ranking</h3></div></div>
    <label htmlFor="top-n" className="field-label range-label">Top N candidates <output htmlFor="top-n">{form.top_n}</output></label>
    <input id="top-n" type="range" min={10} max={100} step={5} value={form.top_n} disabled={loading}
      onChange={(e) => onChange({ top_n: Number(e.target.value) })} />
    <div className="range-ends"><span>10 candidates</span><span>100 candidates</span></div>
    <details className="advanced-options"><summary>Optional Claude reranking</summary>
      <label className="checkbox-label"><input type="checkbox" checked={form.use_llm} disabled={loading}
        onChange={(e) => onChange({ use_llm: e.target.checked })} />Enable Claude LLM re-ranking</label>
      <p className="helper">Requires ANTHROPIC_API_KEY on the server. Sends profile evidence to Claude.</p>
      <label htmlFor="llm-n" className="field-label">LLM re-ranking pool size: {form.llm_n}</label>
      <input id="llm-n" type="range" min={10} max={100} step={5} value={form.llm_n} disabled={loading || !form.use_llm}
        onChange={(e) => onChange({ llm_n: Number(e.target.value) })} />
    </details>
    <button type="submit" form="ranking-job" disabled={loading || !ready} className="btn btn-primary run-button" aria-busy={loading}>
      {loading ? "Ranking…" : "Run Ranking"}<span aria-hidden="true">{loading ? "…" : "→"}</span>
    </button>
    {!ready && <p className="helper">Select an accepted dataset to continue.</p>}
    {loading && <p role="status" className="feedback">Ranking candidates… You can review the current results while you wait.</p>}
    {error && <p role="alert" className="feedback feedback-error">{error}</p>}
  </section>;
}
