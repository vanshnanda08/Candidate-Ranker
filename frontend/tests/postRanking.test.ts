import assert from "node:assert/strict";
import { test } from "node:test";
import { contextKey, filterResults, hasRecordedMatch, reviewContext, toggleComparison } from "../src/postRanking.ts";
import { candidates, context, job } from "./fixtures.ts";

const blank = { search: "", requirement: "", minimum: "", maximum: "" };

test("filters search title and recorded skills only, preserving original objects, ranks and order", () => {
  const before = JSON.stringify(candidates);
  assert.deepEqual(filterResults(candidates, { ...blank, search: " DATA " }).rows, [candidates[1]]);
  assert.deepEqual(filterResults(candidates, { ...blank, search: "POSTGRESQL" }).rows, candidates.slice(0, 2));
  assert.equal(filterResults(candidates, { ...blank, search: "Name must not" }).rows.length, 0);
  assert.deepEqual(filterResults(candidates, { ...blank, requirement: "Docker" }).rows.map((c) => c.rank), [4]);
  assert.equal(JSON.stringify(candidates), before);
  assert.deepEqual(filterResults(candidates, blank).rows, candidates);
});

test("experience bounds are inclusive, support zero and combine with query and requirement", () => {
  assert.deepEqual(filterResults(candidates, { ...blank, minimum: "5", maximum: "8" }).rows, candidates.slice(0, 2));
  assert.deepEqual(filterResults(candidates, { ...blank, maximum: "0" }).rows, [candidates[3]]);
  assert.deepEqual(filterResults(candidates, { ...blank, minimum: "3", requirement: "PostgreSQL", search: "data" }).rows, [candidates[1]]);
  assert.deepEqual(filterResults(candidates, { ...blank, minimum: "99" }).rows, []);
});

test("invalid experience bounds are actionable and reset returns all results", () => {
  for (const bounds of [{ minimum: "-1" }, { maximum: "Infinity" }, { minimum: "nope" }, { minimum: "8", maximum: "2" }]) {
    const result = filterResults(candidates, { ...blank, ...bounds });
    assert.ok(result.error); assert.deepEqual(result.rows, []);
  }
  assert.equal(filterResults([], blank).error, null);
  assert.equal(filterResults(candidates, blank).rows.length, 4);
});

test("requirement evidence is recorded exact matching, not inferred from a title or substring", () => {
  assert.equal(hasRecordedMatch(candidates[2], "Java"), false);
  assert.equal(hasRecordedMatch(candidates[0], " java "), true);
  assert.equal(hasRecordedMatch(candidates[1], "Data Engineer"), false);
  assert.equal(hasRecordedMatch(candidates[0], "Docker"), false);
});

test("comparison is capped at three and independent of filters", () => {
  let ids: string[] = [];
  for (const id of ["F-1", "F-2", "F-3", "F-4"]) ids = toggleComparison(ids, id);
  assert.deepEqual(ids, ["F-1", "F-2", "F-3"]);
  filterResults(candidates, { ...blank, search: "nothing" });
  assert.deepEqual(ids, ["F-1", "F-2", "F-3"]);
  assert.deepEqual(toggleComparison(ids, "F-2"), ["F-1", "F-3"]);
  assert.deepEqual(ids, ["F-1", "F-2", "F-3"]);
});

test("submitted context is a copy; draft changes and response explanations do not change its identity", () => {
  const responseJob = structuredClone(job);
  const snapshot = reviewContext(responseJob, { data_path: "fictional.json", is_sample: true });
  responseJob.required_skills.push("Python");
  assert.deepEqual(snapshot, context);
  assert.equal("scoring_notes" in snapshot.job, false);
  assert.equal(contextKey(reviewContext({ ...job, scoring_notes: "new explanation" }, context.dataset)), contextKey(context));
});

test("same-title jobs and distinct datasets get distinct shortlist identities", () => {
  for (const change of [{ description: "A different description for the same job title." }, { required_skills: ["Figma"] },
    { preferred_skills: ["Kubernetes"] }, { experience_min: 4 }, { experience_max: null }, { mode: "default" as const }]) {
    assert.notEqual(contextKey(context), contextKey(reviewContext({ ...job, ...change }, context.dataset)));
  }
  assert.notEqual(contextKey(context), contextKey(reviewContext(job, { ...context.dataset, data_path: "another.json" })));
  assert.notEqual(contextKey(context), contextKey(reviewContext(job, { ...context.dataset, is_sample: false })));
  assert.equal(contextKey(context), contextKey({ dataset: context.dataset, job: context.job }));
});

test("content scope separates same-name uploads, shares identical content, and leaves legacy keys unchanged", () => {
  const a = reviewContext(job, { data_path: "same.json", is_sample: true, fingerprint: "a".repeat(64), label: "same.json" });
  const b = reviewContext(job, { ...a.dataset, fingerprint: "b".repeat(64) });
  assert.notEqual(contextKey(a), contextKey(b));
  assert.equal(contextKey(a), contextKey(reviewContext(job, { ...a.dataset, data_path: "renamed.json", label: "renamed.json" })));
  assert.equal(JSON.parse(contextKey(context))[0], 1);
});
