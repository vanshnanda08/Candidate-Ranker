import { useState } from "react";
import { contextKey } from "../postRanking.ts";
import type { RankingSnapshot } from "../postRanking";
import { editNote, NOTE_LIMIT, readShortlists, removeSaved, toggleShortlist, writeShortlists } from "../shortlist.ts";
import type { SavedShortlist } from "../shortlist";
import { buildShortlistCsv } from "../shortlistCsv.ts";
import { downloadCsv } from "../csv";
import { ReturnedResults } from "./ReturnedResults";

const getStorage = () => window.localStorage;

export function PostRankingWorkspace({ ranking, loading = false }: { ranking: RankingSnapshot | null; loading?: boolean }) {
  const [feedback, setFeedback] = useState<{ runId: number | null; text: string }>({ runId: null, text: "" });
  const [initial] = useState(() => readShortlists(getStorage));
  const [scopes, setScopes] = useState(initial.scopes);
  const [warning, setWarning] = useState(initial.warning);
  const [selection, setSelection] = useState({ runId: ranking?.runId ?? null,
    key: ranking ? contextKey(ranking.context) : initial.scopes[0] ? contextKey(initial.scopes[0].context) : "" });
  const [navigation, setNavigation] = useState<{ runId: number | null; view: "results" | "shortlist" }>({
    runId: ranking?.runId ?? null, view: ranking ? "results" : "shortlist" });
  const runId = ranking?.runId ?? null;
  const activeKey = ranking ? contextKey(ranking.context) : "";
  const view = navigation.runId === runId ? navigation.view : ranking ? "results" : "shortlist";
  const selectedKey = selection.runId === runId ? selection.key : activeKey;
  const available = ranking && !scopes.some((scope) => contextKey(scope.context) === activeKey)
    ? [...scopes, { context: ranking.context, entries: [] }] : scopes;
  const selected = available.find((scope) => contextKey(scope.context) === selectedKey) ?? available[0];
  const activeEntries = scopes.find((scope) => contextKey(scope.context) === activeKey)?.entries ?? [];

  function save(next: SavedShortlist[]) {
    setScopes(next);
    setWarning(writeShortlists(getStorage, next));
  }

  return <section className="post-ranking-workspace" aria-label="Post-ranking workspace">
    <div className="review-heading" hidden={!ranking && !available.length}><nav aria-label="Post-ranking views" className="segmented-nav">
      <button type="button" disabled={!ranking} aria-pressed={view === "results"}
        onClick={() => setNavigation({ runId, view: "results" })}
        className="view-tab">Returned results</button>
      <button type="button" aria-pressed={view === "shortlist"} onClick={() => setNavigation({ runId, view: "shortlist" })}
        className="view-tab">Shortlist</button>
    </nav></div>
    <p role="status" className="shortlist-feedback" aria-atomic="true">{feedback.runId === runId ? feedback.text : ""}</p>
    {!ranking && !available.length && view === "shortlist" && <div className="workspace-welcome"><p className="eyebrow">Candidate review</p><h2>Build your<br /><em>next shortlist.</em></h2><p>Select your dataset and job, then run the ranking.</p></div>}
    {warning && <p role="status" className="feedback feedback-warning">{warning}</p>}
    {ranking && <div hidden={view !== "results"} className="ranking-view" data-updating={loading}>
      <ReturnedResults key={ranking.runId} result={ranking.response} savedIds={new Set(activeEntries.map((entry) => entry.candidate_id))}
        onToggleSaved={(candidate) => {
          const saved = activeEntries.some((entry) => entry.candidate_id === candidate.candidate_id);
          save(toggleShortlist(scopes, ranking.context, candidate));
          setFeedback({ runId, text: `${candidate.current_title} ${saved ? "removed from" : "added to"} shortlist.` });
        }} />
    </div>}
    <div hidden={view !== "shortlist" || (!ranking && !available.length)} className="panel shortlist-panel">
      <h2 className="major-heading">Shortlist</h2>
      <p className="text-xs text-slate-500 mt-1">Notes save in this browser, separately for each job and dataset. Export a portable copy.</p>
      {!available.length && <p className="empty-state mt-4">No saved shortlists yet. Run a ranking and add candidates from results or comparison.</p>}
      {selected && <>
        <label className="field-label mt-4">Shortlist job and dataset
          <select className="ui-input" value={contextKey(selected.context)}
            onChange={(e) => setSelection({ runId, key: e.target.value })}>
            {available.map((scope, i) => <option key={contextKey(scope.context)} value={contextKey(scope.context)}>
              {i + 1}. {scope.context.job.title} · Required: {scope.context.job.required_skills.join(", ") || "none"} · {scope.context.dataset.label ?? scope.context.dataset.data_path}
            </option>)}
          </select>
        </label>
        <h3 className="font-semibold mt-3">Shortlist for: {selected.context.job.title}</h3>
        <details className="text-sm text-slate-600 mt-2 break-words">
          <summary className="cursor-pointer">Saved job and dataset details</summary>
          <p className="whitespace-pre-wrap mt-2">{selected.context.job.description}</p>
          <p>Required: {selected.context.job.required_skills.join(", ") || "None specified"}</p>
          <p>Preferred: {selected.context.job.preferred_skills.join(", ") || "None specified"}</p>
          <p>Experience: {selected.context.job.experience_min ?? "No minimum"} – {selected.context.job.experience_max ?? "No maximum"}</p>
          <p className="break-all">Dataset: {selected.context.dataset.data_path} ({selected.context.dataset.is_sample ? "sample JSON" : "JSONL"})</p>
          {selected.context.dataset.fingerprint && <p className="break-all">Content SHA-256: {selected.context.dataset.fingerprint}</p>}
        </details>
        <div className="flex flex-wrap justify-between gap-2 my-4 items-center">
          <p role="status" className="shortlist-count">{selected.entries.length} shortlisted candidates</p>
          <button type="button" disabled={!selected.entries.length}
            className="btn btn-primary"
            onClick={() => downloadCsv("shortlist.csv", buildShortlistCsv(selected.entries))}>Export shortlist.csv</button>
        </div>
        {!selected.entries.length && <p className="empty-state">No candidates saved for this job and dataset. Add candidates from its returned results or comparison.</p>}
        <div className="shortlist-entries">{selected.entries.map((entry) => <article key={entry.candidate_id} className="shortlist-card">
          <div className="flex flex-wrap justify-between gap-2">
            <div className="min-w-0 break-words"><h4 className="font-semibold">{entry.title}</h4>
              <p className="text-sm text-slate-500 break-all">{entry.candidate_id} · Original rank #{entry.original_rank}</p></div>
            <button type="button" aria-label={`Remove ${entry.candidate_id} from saved shortlist`} className="btn btn-ghost"
              onClick={() => save(removeSaved(scopes, contextKey(selected.context), entry.candidate_id))}>Remove</button>
          </div>
          <label htmlFor={`shortlist-note-${encodeURIComponent(entry.candidate_id)}`} className="field-label mt-3">Notes for {entry.candidate_id}</label>
            <textarea id={`shortlist-note-${encodeURIComponent(entry.candidate_id)}`} rows={4} maxLength={NOTE_LIMIT} value={entry.notes} className="ui-input notes-input" placeholder="Record job-related evidence, questions and next steps…"
              onChange={(e) => save(editNote(scopes, contextKey(selected.context), entry.candidate_id, e.target.value))} />
          <p className="text-xs text-slate-500 mt-1">{entry.notes.length}/{NOTE_LIMIT} characters · {warning ? "Changes are in this tab; browser save could not be confirmed" : "Saved in this browser"}</p>
        </article>)}</div>
      </>}
    </div>
  </section>;
}
