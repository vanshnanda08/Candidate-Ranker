import { useEffect, useState } from "react";
import { fetchBenchmark } from "../api";
import type { BenchmarkReport } from "../types";

export function BenchmarkView() {
  const [report, setReport] = useState<BenchmarkReport | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => { fetchBenchmark().then(setReport).catch(() => setError(true)); }, []);
  if (error) return <p role="alert">Could not load the benchmark aggregates. Check the local API and reload.</p>;
  if (!report) return <p role="status">Loading benchmark aggregates…</p>;
  return <section className="panel benchmark-panel" aria-label="Benchmark results">
    <p className="eyebrow">Evaluation · Phase 4B</p><h2 className="benchmark-title"><span>Single-role benchmark:</span> {report.role}</h2>
    <p className="text-sm mt-2">{report.pool_size}-profile judged pool · {report.label_provenance} labels · scoring date {report.as_of} · Claude disabled.</p>
    <p className="benchmark-takeaway">All three methods tied at NDCG@10. Current hybrid led at NDCG@20 and remains the default.</p>
    <div className="hidden sm:block overflow-x-auto mt-4"><table className="benchmark-table">
      <caption className="text-left text-xs text-slate-600 mb-2">Pooled NDCG uses the same judged pool for the ideal ranking.</caption>
      <thead><tr>{["Method", "NDCG@10", "Judged@10", "NDCG@20", "Judged@20"].map((label) => <th className="p-2 border-b" key={label}>{label}</th>)}</tr></thead>
      <tbody>{[["keyword_only", "Keyword-only"], ["current_hybrid", "Current hybrid (default)"], ["grouped_hybrid", "Grouped-skill hybrid (experimental)"]].map(([key, label]) => {
        const row = report.methods[key];
        return <tr key={key} className={key === "current_hybrid" ? "default-method" : undefined}><th scope="row" className="p-2 border-b font-medium">{label}</th>
          {["10", "20"].map((cutoff) => <FragmentCells key={cutoff} value={row[cutoff]} />)}</tr>;
      })}</tbody>
    </table></div>
    <div className="sm:hidden space-y-3 mt-4">
      {[["keyword_only", "Keyword-only"], ["current_hybrid", "Current hybrid (default)"], ["grouped_hybrid", "Grouped-skill hybrid (experimental)"]].map(([key, label]) =>
        <article key={key} className={`benchmark-method ${key === "current_hybrid" ? "default-method" : ""}`}>
          <h3 className="font-semibold text-sm">{label}</h3>
          <dl className="grid grid-cols-2 gap-2 text-sm mt-2">{["10", "20"].map((cutoff) => <div key={cutoff}>
            <dt>NDCG@{cutoff}</dt><dd className="font-mono">{report.methods[key][cutoff].pooled_ndcg.toFixed(6)}</dd>
            <dt className="text-xs mt-1">Judged coverage</dt><dd>{report.methods[key][cutoff].judged_count}/{cutoff}</dd>
          </div>)}</dl>
        </article>)}
    </div>
    <p className="benchmark-caveat">{report.scope} These aggregate results do not establish general hiring effectiveness. Unjudged profiles are not grade zero.</p>
    <details className="text-xs text-slate-500 mt-3"><summary>Verified report source</summary><p>{report.source_report}</p><p className="break-all">SHA-256: {report.source_sha256}</p></details>
  </section>;
}

function FragmentCells({ value }: { value: BenchmarkReport["methods"][string][string] }) {
  return <><td className="p-2 border-b font-mono">{value.pooled_ndcg.toFixed(6)}</td><td className="p-2 border-b">{value.judged_count}/{value.cutoff}</td></>;
}
