import type { ActiveJob, CandidateResult } from "../src/types";
import { reviewContext } from "../src/postRanking.ts";

export const job: ActiveJob = { mode: "custom", title: "Platform Engineer",
  description: "Build reliable Java services and relational data products.", required_skills: ["Java", "PostgreSQL"],
  preferred_skills: ["Docker"], experience_min: 3, experience_max: 10, scoring_notes: "fixture" };

export const context = reviewContext(job, { data_path: "fictional.json", is_sample: true });

export function candidate(id: string, rank: number, title: string, years: number, matches: string[]): CandidateResult {
  return { candidate_id: id, rank, current_title: title, years_of_experience: years,
    display_score: .99 - rank / 100, name: "Name must not be searched", headline: "Headline must not be searched",
    structured: { matched_skills: matches }, reasoning: "fictional reasoning" } as CandidateResult;
}

export const candidates = [candidate("F-1", 1, "Backend Engineer", 8, ["Java", "PostgreSQL"]),
  candidate("F-2", 4, "Data Engineer", 5, ["PostgreSQL", "Docker"]),
  candidate("F-3", 7, "Frontend Engineer", 2, ["JavaScript"]), candidate("F-4", 9, "Graduate", 0, [])];
