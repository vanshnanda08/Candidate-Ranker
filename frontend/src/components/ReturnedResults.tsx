import { useState } from "react";
import { filterResults, toggleComparison } from "../postRanking.ts";
import type { ResultFilters } from "../postRanking";
import type { CandidateResult, RankResponse } from "../types";
import { buildSubmissionCsv, downloadCsv } from "../csv";
import { CandidateCard } from "./CandidateCard";
import { ComparisonPanel } from "./ComparisonPanel";
import { ScoreChart } from "./ScoreChart";
import { StatsHeader } from "./StatsHeader";

interface Props { result: RankResponse; savedIds: Set<string>; onToggleSaved: (candidate: CandidateResult) => void }
const EMPTY_FILTERS: ResultFilters = { search: "", minimum: "", maximum: "", requirement: "" };
const input = "ui-input";

export function ReturnedResults({ result, savedIds, onToggleSaved }: Props) {
  const [filters, setFilters] = useState<ResultFilters>(EMPTY_FILTERS);
  const [compared, setCompared] = useState<string[]>([]);
  const { rows, error } = filterResults(result.results, filters);
  const selected = compared.map((id) => result.results.find((candidate) => candidate.candidate_id === id)!)
    .filter(Boolean);
  const { job } = result;
  return <div className="fresh-results">
    <section className="panel result-job" aria-label="Result job">
      <p className="eyebrow">{result.results.length} returned candidates <span className="meta-divider">/</span> {result.total_candidates.toLocaleString()} profiles</p><h2 className="major-heading"><span className="sr-only">Results for: </span>{job.title}</h2>
      <p className="text-xs text-slate-500 mt-1">{job.mode === "custom" ? "Custom job" : "Built-in job"} · Current hybrid ranking</p>
      <details className="mt-2 text-sm text-slate-600">
        <summary className="cursor-pointer">Submitted requirements and scoring</summary>
        <p className="whitespace-pre-wrap mt-2">{job.description}</p>
        <p className="mt-2">Required: {job.required_skills.join(", ") || "None supplied"}</p>
        <p>Preferred: {job.preferred_skills.join(", ") || "None supplied"}</p>
        <p>Experience: {job.experience_min ?? "No minimum"} – {job.experience_max ?? "No maximum"} years</p>
        <p className="text-xs mt-2">{job.scoring_notes}</p><StatsHeader data={result} />
      </details>
    </section>
    <section aria-label="Filters for returned results" className="panel result-filters">
      <div className="filter-title-row"><h3>Filters for returned results</h3>    <div className="flex flex-wrap items-center justify-between gap-2">
      <button type="button" onClick={() => downloadCsv("submission.csv", buildSubmissionCsv(result.results))}
        className="btn btn-secondary">
        Download submission.csv (all returned)
      </button>
    </div>
</div>
      <div className="filter-grid">
        <label className="field-label">Search title or matched skill
          <input className={input} type="search" value={filters.search}
            onChange={(e) => setFilters({ ...filters, search: e.target.value })} /></label>
        <label className="field-label">Recorded match for job requirement
          <select className={input} value={filters.requirement}
            onChange={(e) => setFilters({ ...filters, requirement: e.target.value })}>
            <option value="">All requirements</option>
            <optgroup label="Required">{job.required_skills.map((skill) => <option key={skill} value={skill}>{skill}</option>)}</optgroup>
            <optgroup label="Preferred">{job.preferred_skills.map((skill) => <option key={skill} value={skill}>{skill}</option>)}</optgroup>
          </select></label>
        <label className="field-label">Minimum years of experience
          <input className={input} type="number" min="0" step="any" value={filters.minimum}
            aria-invalid={Boolean(error)} onChange={(e) => setFilters({ ...filters, minimum: e.target.value })} /></label>
        <label className="field-label">Maximum years of experience
          <input className={input} type="number" min="0" step="any" value={filters.maximum}
            aria-invalid={Boolean(error)} onChange={(e) => setFilters({ ...filters, maximum: e.target.value })} /></label>
      </div>
      {error && <p role="alert" className="field-error">{error}</p>}
      <div className="flex flex-wrap justify-between gap-2 mt-3 text-sm">
        <p role="status">Showing {rows.length} of {result.results.length} returned candidates · original ranks retained</p>
        <button type="button" className="btn btn-secondary" onClick={() => setFilters(EMPTY_FILTERS)}>Reset filters</button>
      </div>
    </section>
    <details className="panel chart-panel"><summary>Score distribution <span className="helper">All returned candidates</span></summary>
      <ScoreChart results={result.results} />
      <p className="helper">The chart and submission export include all returned candidates, regardless of filters.</p>
    </details>
    <ComparisonPanel candidates={selected} job={job} savedIds={savedIds} onToggleSaved={onToggleSaved}
      onRemove={(id) => setCompared(compared.filter((value) => value !== id))} onClear={() => setCompared([])} />
    <div className="candidate-list-heading"><span className="helper">Original rank · Candidate · Matched requirements</span>
      {compared.length > 0 && <a className="btn btn-secondary" href="#candidate-comparison">View comparison ({compared.length}/3) ↑</a>}
    </div>
    {!rows.length && <div className="empty-state">
      {error ? "Correct the experience range or reset filters." : "No returned candidates match these filters. Try a different title, skill or experience range, or reset filters."}
    </div>}
    <div className="candidate-list">{rows.map((candidate) => <CandidateCard key={candidate.candidate_id} result={candidate} defaultOpen={false}
      actions={<>
        <label className="checkbox-label">
          <input type="checkbox" checked={compared.includes(candidate.candidate_id)}
            disabled={compared.length >= 3 && !compared.includes(candidate.candidate_id)} aria-describedby="comparison-help"
            onChange={() => setCompared(toggleComparison(compared, candidate.candidate_id))}
            aria-label={`Compare ${candidate.candidate_id}`} /> Compare</label>
        <button type="button" aria-pressed={savedIds.has(candidate.candidate_id)}
          aria-label={`${savedIds.has(candidate.candidate_id) ? "Remove" : "Add"} ${candidate.candidate_id} ${savedIds.has(candidate.candidate_id) ? "from" : "to"} shortlist`}
          onClick={() => onToggleSaved(candidate)} className="btn btn-ghost">
          {savedIds.has(candidate.candidate_id) ? "Shortlisted ✓" : "Add to shortlist"}
        </button>
      </>} />)}</div>
  </div>;
}
