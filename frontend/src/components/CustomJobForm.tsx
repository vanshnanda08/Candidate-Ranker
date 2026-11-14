import type { ReactNode } from "react";
export interface JobDraft {
  title: string;
  description: string;
  required: string;
  preferred: string;
  minimum: string;
  maximum: string;
}

interface Props {
  children?: ReactNode;
  custom: boolean;
  onModeChange: (custom: boolean) => void;
  draft: JobDraft;
  onChange: (patch: Partial<JobDraft>) => void;
  errors: Record<string, string>;
  loading: boolean;
  onRun: () => void;
}

export function CustomJobForm({ custom, onModeChange, draft, onChange, errors, loading, onRun, children }: Props) {
  function errorFor(field: string) {
    return Object.entries(errors).filter(([key]) => key === `job.${field}` || key.startsWith(`job.${field}.`))
      .map(([, message]) => message).join("; ");
  }
  const control = "ui-input";
  function field(label: string, key: keyof JobDraft, apiKey: string, options?: { textarea?: boolean; type?: string }) {
    const error = errorFor(apiKey);
    const props = {
      id: `job-${key}`, value: draft[key], disabled: loading, className: control,
      onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => onChange({ [key]: e.target.value }),
      "aria-invalid": Boolean(error), "aria-describedby": error ? `job-${key}-error` : undefined,
    };
    return <div>
      <label htmlFor={`job-${key}`} className="field-label">{label}</label>
      {options?.textarea ? <textarea {...props} rows={key === "description" ? 4 : 2} />
        : <input {...props} type={options?.type ?? "text"} min={options?.type === "number" ? 0 : undefined}
          max={options?.type === "number" ? 80 : undefined} step={options?.type === "number" ? "any" : undefined} />}
      {error && <p id={`job-${key}-error`} className="field-error">{error}</p>}
    </div>;
  }
  return <form id="ranking-job" noValidate onSubmit={(e) => { e.preventDefault(); onRun(); }}
    className="setup-step job-step" aria-label="Job configuration">
    <div className="step-heading"><div><h3>Job</h3></div></div>
    <label htmlFor="job-mode" className="field-label">Job to rank for</label>
    <select id="job-mode" className={control} value={custom ? "custom" : "default"} disabled={loading}
      onChange={(e) => onModeChange(e.target.value === "custom")}>
      <option value="default">Built-in: Senior AI Engineer</option>
      <option value="custom">Custom job</option>
    </select>
    {!custom && children}
    {custom && <div className="flex flex-col gap-4 mt-4">
      {field("Job title (required)", "title", "title")}
      {field("Job description (required, at least 20 characters)", "description", "description", { textarea: true })}
      <p className="text-xs text-slate-500">Enter skills separated by commas or new lines. These lists set the scoring requirements; the description provides semantic context. List each skill once.</p>
      {field("Required skills", "required", "required_skills", { textarea: true })}
      {field("Preferred skills", "preferred", "preferred_skills", { textarea: true })}
      <div className="grid sm:grid-cols-2 gap-4">
        {field("Minimum experience (optional years)", "minimum", "experience_min", { type: "number" })}
        {field("Maximum experience (optional years)", "maximum", "experience_max", { type: "number" })}
      </div>
      {errors.job && <p role="alert" className="text-sm text-red-700">{errors.job}</p>}
      <p className="text-xs text-slate-500">Leave a skill list or experience bound blank to omit it. Omitted experience, education, and location receive neutral scores; built-in AI-role preferences do not apply. Changes take effect on the next run.</p>
    </div>}
  </form>;
}
