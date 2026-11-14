import { useLayoutEffect, useRef } from "react";
import type { ActiveJob, CandidateResult } from "../types";
import { hasRecordedMatch } from "../postRanking.ts";

interface Props {
  candidates: CandidateResult[];
  job: ActiveJob;
  savedIds: Set<string>;
  onToggleSaved: (candidate: CandidateResult) => void;
  onRemove: (id: string) => void;
  onClear: () => void;
}

export function ComparisonPanel({ candidates, job, savedIds, onToggleSaved, onRemove, onClear }: Props) {
  const panel = useRef<HTMLElement>(null);
  const previousHeight = useRef<number | null>(null);
  const selectionKey = candidates.map((candidate) => candidate.candidate_id).join("|");
  useLayoutEffect(() => {
    const element = panel.current;
    if (!element) return;
    const height = element.getBoundingClientRect().height;
    const from = previousHeight.current;
    previousHeight.current = height;
    if (from === null || from === height || window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches) return;
    // State and controls update immediately; only the containing layout interpolates.
    if (!element.animate) return;
    const styles = window.getComputedStyle(element);
    const duration = Number.parseFloat(styles.getPropertyValue("--motion-panel")) || 220;
    const animation = element.animate?.([{ height: `${from}px` }, { height: `${height}px` }],
      { duration, easing: styles.getPropertyValue("--ease").trim() || "ease-out" });
    return () => animation?.cancel();
  }, [selectionKey]);
  return <section ref={panel} id="candidate-comparison" aria-label="Candidate comparison" className="panel comparison-panel" data-selected={candidates.length > 0}>
    <div className="flex flex-wrap justify-between gap-2 items-center">
      <h3 className="font-semibold text-slate-900">Compare candidates ({candidates.length}/3)</h3>
      <button type="button" onClick={onClear} disabled={!candidates.length}
        className="btn btn-secondary">Clear comparison</button>
    </div>
    <p id="comparison-help" className="helper">Select up to three candidates. Selections stay when filters change.</p>
    {candidates.length > 0 && <p className="helper comparison-disclaimer">Recorded evidence only; no match does not mean a skill is absent.
      {job.mode === "default" && " The built-in response does not record preferred-skill matches."}</p>}
    <div className={`comparison-grid comparison-count-${candidates.length}`}>
      {candidates.map((candidate) => <article key={candidate.candidate_id} className="comparison-card">
        <h4 className="font-semibold">{candidate.current_title}</h4>
        <p className="text-xs text-slate-500 break-all">{candidate.candidate_id}</p>
        <p className="text-sm my-2">Original rank #{candidate.rank} · {candidate.years_of_experience} years</p>
        {([['Required skills', job.required_skills], ['Preferred skills', job.preferred_skills]] as const).map(([label, skills]) =>
          <div key={label} className="mt-3">
            <h5 className="text-sm font-semibold">{label}</h5>
            {!skills.length && <p className="text-xs text-slate-500">None specified</p>}
            {skills.length > 5 && <p className="helper">{skills.length} requirements · Scroll for all evidence</p>}
            <dl className="comparison-evidence" tabIndex={skills.length > 5 ? 0 : undefined} aria-label={`${label} evidence for ${candidate.candidate_id}`}>{skills.map((skill) => <div key={skill}>
              <dt className="font-medium">{skill}</dt>
              <dd className={hasRecordedMatch(candidate, skill) ? "text-emerald-700" : "text-slate-500"}>
                {hasRecordedMatch(candidate, skill) ? `Recorded match: ${skill}` : "No matching evidence"}
              </dd>
            </div>)}</dl>
          </div>)}
        <div className="flex flex-col items-start gap-2 mt-4 text-sm">
          <button type="button" aria-pressed={savedIds.has(candidate.candidate_id)}
            aria-label={`${savedIds.has(candidate.candidate_id) ? "Remove" : "Add"} ${candidate.candidate_id} ${savedIds.has(candidate.candidate_id) ? "from" : "to"} shortlist from comparison`}
            className="btn btn-secondary" onClick={() => onToggleSaved(candidate)}>
            {savedIds.has(candidate.candidate_id) ? "Shortlisted ✓" : "Add to shortlist"}</button>
          <button type="button" className="btn btn-ghost" onClick={() => onRemove(candidate.candidate_id)}
            aria-label={`Remove ${candidate.candidate_id} from comparison`}>Remove from comparison</button>
        </div>
      </article>)}
    </div>
  </section>;
}
