import assert from "node:assert/strict";
import { test } from "node:test";
import { contextKey, reviewContext } from "../src/postRanking.ts";
import { editNote, NOTE_LIMIT, parseShortlists, readShortlists, removeSaved, STORAGE_KEY, toggleShortlist, writeShortlists } from "../src/shortlist.ts";
import type { SavedShortlist } from "../src/shortlist";
import { candidates, context, job } from "./fixtures.ts";

function memory() {
  const values = new Map<string, string>();
  return { values, getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => { values.set(key, value); } };
}

test("shortlist round-trips notes and minimal snapshots through a fresh page read", () => {
  const storage = memory();
  let scopes = toggleShortlist([], context, candidates[1]);
  scopes = editNote(scopes, contextKey(context), "F-2", 'Discuss, "ownership"\nSecond line.');
  assert.equal(writeShortlists(() => storage, scopes), null);
  const restored = readShortlists(() => storage);
  assert.deepEqual(restored.scopes, scopes); assert.equal(restored.warning, null);
  assert.deepEqual(Object.keys(restored.scopes[0].entries[0]).sort(), ["candidate_id", "notes", "original_rank", "title"]);
  assert.equal(restored.scopes[0].entries[0].original_rank, 4);
});

test("same-title jobs have separate entries and editing/removal never overwrites another job", () => {
  const other = reviewContext({ ...job, required_skills: ["Figma"] }, context.dataset);
  let scopes = toggleShortlist([], context, candidates[0]);
  scopes = editNote(scopes, contextKey(context), "F-1", "Keep the original note");
  scopes = toggleShortlist(scopes, other, candidates[0]);
  scopes = editNote(scopes, contextKey(other), "F-1", "A separate note");
  const original = structuredClone(scopes[0]);
  scopes = removeSaved(scopes, contextKey(other), "F-1");
  assert.deepEqual(scopes[0], original); assert.equal(scopes[1].entries.length, 0);
  assert.equal(original.entries[0].original_rank, candidates[0].rank);
});

test("add/remove is immutable and note editing cannot change another candidate", () => {
  const one = toggleShortlist([], context, candidates[0]);
  const two = toggleShortlist(one, context, candidates[1]);
  const changed = editNote(two, contextKey(context), "F-2", "x".repeat(NOTE_LIMIT + 1));
  assert.equal(changed[0].entries[1].notes.length, NOTE_LIMIT);
  assert.equal(changed[0].entries[0].notes, ""); assert.equal(two[0].entries[1].notes, "");
  assert.equal(one[0].entries.length, 1);
  assert.deepEqual(toggleShortlist(two, context, candidates[0])[0].entries.map((e) => e.candidate_id), ["F-2"]);
});

test("unavailable, denied, full and malformed storage degrade to safe in-memory use", () => {
  assert.ok(readShortlists(() => { throw new Error("SecurityError"); }).warning);
  const storage = memory();
  assert.deepEqual(readShortlists(() => storage), { scopes: [], warning: null });
  storage.values.set(STORAGE_KEY, "broken JSON");
  assert.ok(readShortlists(() => storage).warning);
  assert.equal(storage.values.get(STORAGE_KEY), "broken JSON"); // No automatic overwrite on mount.
  const scopes = toggleShortlist([], context, candidates[0]);
  assert.ok(writeShortlists(() => ({ getItem: storage.getItem, setItem: () => { throw new Error("QuotaExceededError"); } }), scopes));
  assert.equal(scopes[0].entries.length, 1);
  assert.equal(writeShortlists(() => storage, scopes), null);
});

test("invalid versions, shapes, duplicate IDs/scopes and impossible ranks are rejected", () => {
  const scopes = toggleShortlist([], context, candidates[0]);
  for (const value of [{ version: 2, scopes }, { version: 1 }, { version: 1, scopes: [scopes[0], scopes[0]] },
    { version: 1, scopes: [{ ...scopes[0], entries: [scopes[0].entries[0], scopes[0].entries[0]] }] }]) {
    assert.throws(() => parseShortlists(JSON.stringify(value)));
  }
  for (const change of [{ original_rank: 0 }, { original_rank: "1" }, { notes: {} }, { title: "" }, { candidate_id: null }]) {
    assert.throws(() => parseShortlists(JSON.stringify({ version: 1, scopes: [{ ...scopes[0], entries: [{ ...scopes[0].entries[0], ...change }] }] })));
  }
});

test("reader strips unrelated fields before future saves", () => {
  const scopes = toggleShortlist([], context, candidates[0]);
  const dirty = JSON.parse(JSON.stringify({ version: 1, scopes }));
  dirty.scopes[0].entries[0].profile = { sensitive: "do not store" };
  dirty.scopes[0].context.job.scoring_notes = "not necessary";
  const clean = parseShortlists(JSON.stringify(dirty));
  assert.equal("profile" in clean[0].entries[0], false);
  assert.equal("scoring_notes" in clean[0].context.job, false);
});

test("reading saved snapshots after a new ranking leaves saved rank and notes unchanged", () => {
  const storage = memory();
  const scopes: SavedShortlist[] = editNote(toggleShortlist([], context, candidates[1]), contextKey(context), "F-2", "Confirmed note");
  writeShortlists(() => storage, scopes);
  const rerankedCandidate = { ...candidates[1], rank: 1 };
  assert.equal(rerankedCandidate.rank, 1);
  const restored = readShortlists(() => storage).scopes[0].entries[0];
  assert.equal(restored.original_rank, 4); assert.equal(restored.notes, "Confirmed note");
});

test("content-scoped shortlist recovery preserves fingerprint while legacy lists remain readable", () => {
  const uploaded = { ...context, dataset: { ...context.dataset, fingerprint: "a".repeat(64), label: "same.json" } };
  const saved = toggleShortlist(toggleShortlist([],context,candidates[0]),uploaded,candidates[1]);
  const restored = parseShortlists(JSON.stringify({version:1,scopes:saved}));
  assert.equal(restored.length,2);assert.equal(restored[1].context.dataset.fingerprint,"a".repeat(64));
  assert.equal(restored[0].context.dataset.fingerprint,undefined);
});
