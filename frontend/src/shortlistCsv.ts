import type { ShortlistEntry } from "./shortlist";

export function safeCsvText(text: string): string {
  // Quoting alone does not prevent a spreadsheet from treating text as a formula.
  // Include leading whitespace/control characters before a formula prefix.
  let start = 0;
  while (start < text.length && (/\s/.test(text[start]) || text.charCodeAt(start) < 32)) start++;
  const formula = start < text.length && "=+-@".includes(text[start]);
  const leadingControl = ["\t", "\r", "\n"].some((prefix) => text.startsWith(prefix));
  const safe = formula || leadingControl ? "'" + text : text;
  return '"' + safe.replace(/"/g, '""') + '"';
}

export function buildShortlistCsv(entries: ShortlistEntry[]): string {
  return ["candidate_id,title,original_rank,notes", ...entries.map((entry) =>
    [safeCsvText(entry.candidate_id), safeCsvText(entry.title), entry.original_rank,
      safeCsvText(entry.notes)].join(","))].join("\r\n");
}
