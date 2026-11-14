import { contextKey } from "./postRanking.ts";
import type { ReviewContext } from "./postRanking";
import type { CandidateResult } from "./types";

export interface ShortlistEntry { candidate_id: string; title: string; original_rank: number; notes: string }
export interface SavedShortlist { context: ReviewContext; entries: ShortlistEntry[] }
export interface StorageLike { getItem(key: string): string | null; setItem(key: string, value: string): void }
export const STORAGE_KEY = "talentlens.shortlists.v1";
export const NOTE_LIMIT = 5000;

function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Expected an object");
  return value as Record<string, unknown>;
}
function text(value: unknown, max: number, blank = false): string {
  if (typeof value !== "string" || (!blank && !value.trim()) || value.length > max) throw new Error("Invalid text");
  return value;
}
function skills(value: unknown): string[] {
  if (!Array.isArray(value) || value.length > 100) throw new Error("Invalid skills");
  return value.map((skill) => text(skill, 100));
}
function bound(value: unknown): number | null {
  if (value === null) return null;
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0 || value > 80) throw new Error("Invalid experience");
  return value;
}

export function parseShortlists(raw: string): SavedShortlist[] {
  const saved = object(JSON.parse(raw));
  if (saved.version !== 1 || !Array.isArray(saved.scopes)) throw new Error("Unknown shortlist format");
  const keys = new Set<string>();
  return saved.scopes.map((value) => {
    const scope = object(value), context = object(scope.context), job = object(context.job), dataset = object(context.dataset);
    if (job.mode !== "default" && job.mode !== "custom") throw new Error("Invalid job mode");
    if (typeof dataset.is_sample !== "boolean" || !Array.isArray(scope.entries)) throw new Error("Invalid scope");
    const parsed: SavedShortlist = { context: { job: {
      mode: job.mode, title: text(job.title, 160), description: text(job.description, 20000),
      required_skills: skills(job.required_skills), preferred_skills: skills(job.preferred_skills),
      experience_min: bound(job.experience_min), experience_max: bound(job.experience_max),
    }, dataset: { data_path: text(dataset.data_path, 4096), is_sample: dataset.is_sample } }, entries: [] };
    const { experience_min: min, experience_max: max } = parsed.context.job;
    if (dataset.fingerprint !== undefined) {
      if (typeof dataset.fingerprint !== "string" || !/^[0-9a-f]{64}$/.test(dataset.fingerprint)) throw new Error("Invalid fingerprint");
      parsed.context.dataset.fingerprint = dataset.fingerprint;
    }
    if (dataset.label !== undefined) parsed.context.dataset.label = text(dataset.label, 200);
    if (min !== null && max !== null && min > max) throw new Error("Invalid experience range");
    const key = contextKey(parsed.context);
    if (keys.has(key)) throw new Error("Duplicate shortlist scope");
    keys.add(key);
    const ids = new Set<string>();
    parsed.entries = scope.entries.map((value) => {
      const entry = object(value);
      const id = text(entry.candidate_id, 200);
      if (ids.has(id) || !Number.isSafeInteger(entry.original_rank) || (entry.original_rank as number) < 1) {
        throw new Error("Duplicate candidate or invalid rank");
      }
      ids.add(id);
      // Discard everything except the fields required by the shortlist/export.
      return { candidate_id: id, title: text(entry.title, 500), original_rank: entry.original_rank as number,
        notes: text(entry.notes, NOTE_LIMIT, true) };
    });
    return parsed;
  });
}

export function readShortlists(getStorage: () => StorageLike): { scopes: SavedShortlist[]; warning: string | null } {
  try {
    const raw = getStorage().getItem(STORAGE_KEY);
    if (raw === null) return { scopes: [], warning: null };
    try { return { scopes: parseShortlists(raw), warning: null }; }
    catch { return { scopes: [], warning: "Saved shortlist data is invalid and could not be restored. Storage has not been changed. You can still rank and create a new shortlist." }; }
  } catch {
    return { scopes: [], warning: "Browser storage is unavailable. You can use shortlists in this tab and export them, but they may not survive refresh." };
  }
}

export function writeShortlists(getStorage: () => StorageLike, scopes: SavedShortlist[]): string | null {
  try {
    const payload = JSON.stringify({ version: 1, scopes });
    const clean = parseShortlists(payload);
    getStorage().setItem(STORAGE_KEY, JSON.stringify({ version: 1, scopes: clean }));
    return null;
  } catch {
    return "Could not save to browser storage (unavailable or full). Your changes remain in this tab; export the shortlist before closing or refreshing.";
  }
}

export function toggleShortlist(scopes: SavedShortlist[], context: ReviewContext, candidate: CandidateResult): SavedShortlist[] {
  const key = contextKey(context), existing = scopes.find((scope) => contextKey(scope.context) === key);
  const entries = existing?.entries ?? [];
  const updated = entries.some((entry) => entry.candidate_id === candidate.candidate_id)
    ? entries.filter((entry) => entry.candidate_id !== candidate.candidate_id)
    : [...entries, { candidate_id: candidate.candidate_id, title: candidate.current_title,
      original_rank: candidate.rank, notes: "" }];
  const next = { context, entries: updated };
  return existing ? scopes.map((scope) => contextKey(scope.context) === key ? next : scope) : [...scopes, next];
}

export function editNote(scopes: SavedShortlist[], key: string, id: string, notes: string): SavedShortlist[] {
  return scopes.map((scope) => contextKey(scope.context) !== key ? scope : { ...scope,
    entries: scope.entries.map((entry) => entry.candidate_id === id ? { ...entry, notes: notes.slice(0, NOTE_LIMIT) } : entry) });
}

export function removeSaved(scopes: SavedShortlist[], key: string, id: string): SavedShortlist[] {
  return scopes.map((scope) => contextKey(scope.context) !== key ? scope : { ...scope,
    entries: scope.entries.filter((entry) => entry.candidate_id !== id) });
}
