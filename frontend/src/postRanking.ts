import type { ActiveJob, CandidateResult, RankResponse } from "./types";

export interface DatasetSelection { data_path: string; is_sample: boolean; fingerprint?: string; label?: string }
export type SubmittedJob = Omit<ActiveJob, "scoring_notes">;
export interface ReviewContext { job: SubmittedJob; dataset: DatasetSelection }
export interface RankingSnapshot { runId: number; response: RankResponse; context: ReviewContext }
export interface ResultFilters { search: string; minimum: string; maximum: string; requirement: string }

const normalized = (value: string) => value.trim().toLowerCase().replace(/\s+/g, " ");

export function hasRecordedMatch(candidate: CandidateResult, requirement: string): boolean {
  return candidate.structured.matched_skills.some((skill) => normalized(skill) === normalized(requirement));
}

export function filterResults(candidates: CandidateResult[], filters: ResultFilters) {
  const minimum = filters.minimum.trim() === "" ? null : Number(filters.minimum);
  const maximum = filters.maximum.trim() === "" ? null : Number(filters.maximum);
  if ([minimum, maximum].some((value) => value !== null && (!Number.isFinite(value) || value < 0))) {
    return { rows: [], error: "Enter non-negative numbers for experience, or leave the bounds blank." };
  }
  if (minimum !== null && maximum !== null && minimum > maximum) {
    return { rows: [], error: "Minimum experience must not exceed maximum experience." };
  }
  const query = normalized(filters.search);
  return { rows: candidates.filter((candidate) =>
    (!query || [candidate.current_title, ...candidate.structured.matched_skills]
      .some((value) => normalized(value).includes(query))) &&
    (minimum === null || candidate.years_of_experience >= minimum) &&
    (maximum === null || candidate.years_of_experience <= maximum) &&
    (!filters.requirement || hasRecordedMatch(candidate, filters.requirement))), error: null };
}

export function toggleComparison(selected: string[], id: string): string[] {
  return selected.includes(id) ? selected.filter((value) => value !== id)
    : selected.length < 3 ? [...selected, id] : selected;
}

export function reviewContext(job: ActiveJob, dataset: DatasetSelection): ReviewContext {
  return { job: { mode: job.mode, title: job.title, description: job.description,
    required_skills: [...job.required_skills], preferred_skills: [...job.preferred_skills],
    experience_min: job.experience_min, experience_max: job.experience_max }, dataset: { ...dataset } };
}

export function contextKey(context: ReviewContext): string {
  // Explicit field order makes object insertion order irrelevant. No title-only keys.
  const { job, dataset } = context;
  const identity = [job.mode, job.title, job.description, job.required_skills,
    job.preferred_skills, job.experience_min, job.experience_max];
  return dataset.fingerprint ? JSON.stringify([2, ...identity, "sha256", dataset.fingerprint])
    : JSON.stringify([1, ...identity, dataset.data_path, dataset.is_sample]);
}
