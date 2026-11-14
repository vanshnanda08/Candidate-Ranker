import { useId, useState } from "react";
import type { ReactNode } from "react";
import type { CandidateResult } from "../types";
import { ScoreBar } from "./ScoreBar";

interface CandidateCardProps {
  result: CandidateResult;
  defaultOpen: boolean;
  actions?: ReactNode;
}

export function CandidateCard({ result: r, defaultOpen, actions }: CandidateCardProps) {
  const [open, setOpen] = useState(defaultOpen);
  const detailsId = useId();
  return <article data-candidate-id={r.candidate_id} data-original-rank={r.rank}
    className={`candidate-card ${r.honeypot_penalty < 0.2 ? "candidate-flagged" : ""}`}>
    <div className="candidate-summary">
      <button type="button" aria-expanded={open} aria-controls={detailsId}
        onClick={() => setOpen((value) => !value)} className="candidate-toggle">
        <span className="rank-number">{String(r.rank).padStart(2, "0")}</span>
        <span className="candidate-identity">
          <span className="candidate-title">{r.current_title}</span>
          <span className="candidate-subtitle">{r.years_of_experience} years experience · {r.candidate_id}</span>
          <span className="candidate-matches"><span className="match-label">Matched requirements</span>
            {r.structured.matched_skills.length ? r.structured.matched_skills.join(" · ") : "No matching evidence"}</span>
        </span>
        <span className="detail-indicator">Details <span aria-hidden="true" className="chevron">{open ? "−" : "+"}</span></span>
      </button>
      {actions && <div className="candidate-actions">{actions}</div>}
    </div>
    <div id={detailsId} className="detail-reveal" data-open={open} inert={!open} aria-hidden={!open}>
      <div className="reveal-inner"><div className="candidate-details">
        <div><h4 className="detail-label">Profile</h4>
          <p className="font-semibold">{r.name}</p><p className="helper">{r.headline}</p>
          <p className="profile-meta">{r.location}<br />{r.current_company} · {r.current_industry}<br />{r.current_company_size} employees</p>
          {r.honeypot_flags.length > 0 && <p className="feedback feedback-warning">Profile flags: {r.honeypot_flags.join("; ")}</p>}
        </div>
        <div><h4 className="detail-label">Score breakdown</h4>
          <div className="display-score"><span>Displayed score</span><strong>{r.display_score.toFixed(4)}</strong></div>
          <ScoreBar label="Semantic" value={r.semantic_score} />
          <ScoreBar label="Skills" value={r.structured.skill_score} />
          <ScoreBar label="Career" value={r.structured.career_score} />
          <ScoreBar label="Experience" value={r.structured.exp_score} />
          <ScoreBar label="Behavioral" value={r.behavioral.behavioral_score} />
        </div>
        <div><h4 className="detail-label">Availability</h4><dl className="availability-list">
          <div><dt>Response rate</dt><dd>{Math.round(r.behavioral.response_rate * 100)}%</dd></div>
          <div><dt>Interview rate</dt><dd>{Math.round(r.behavioral.interview_completion * 100)}%</dd></div>
          <div><dt>Notice</dt><dd>{r.behavioral.notice_days}d</dd></div>
          <div><dt>Last active</dt><dd>{r.behavioral.inactive_days}d ago</dd></div>
        </dl></div>
        <p className="candidate-explanation"><strong>Why ranked here:</strong> {r.reasoning}</p>
      </div></div>
    </div>
  </article>;
}
