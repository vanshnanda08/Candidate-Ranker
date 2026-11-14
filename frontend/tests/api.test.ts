import assert from "node:assert/strict";
import { test } from "node:test";
import { ApiError, runRanking } from "../src/api.ts";

const payload = { dataset_id: "demo", data_path: "sample_candidates.json", is_sample: true,
  top_n: 20, coarse_n: 500, llm_n: 0, use_llm: false };

test("a network failure gives actionable guidance and does not prevent a fresh retry", async () => {
  const original = globalThis.fetch;
  const submitted: string[] = [];
  try {
    globalThis.fetch = async (_url, options) => { submitted.push(String(options?.body)); throw new TypeError("Failed to fetch"); };
    await assert.rejects(runRanking(payload), (error: unknown) => {
      assert.ok(error instanceof ApiError);
      assert.match(error.message, /Check that the local API is running, then try again/);
      assert.deepEqual(error.fieldErrors, {});
      return true;
    });
    const expected = { job: { title: "Fictional role" }, results: [] };
    globalThis.fetch = async (_url, options) => { submitted.push(String(options?.body)); return new Response(JSON.stringify(expected)); };
    assert.deepEqual(await runRanking(payload), expected);
    assert.deepEqual(submitted, [JSON.stringify(payload), JSON.stringify(payload)]);
  } finally { globalThis.fetch = original; }
});

test("intentional request cancellation retains its identity", async () => {
  const original = globalThis.fetch;
  const error = new Error("Cancelled"); error.name = "AbortError";
  try {
    globalThis.fetch = async () => { throw error; };
    await assert.rejects(runRanking(payload), (actual: unknown) => actual === error);
  } finally { globalThis.fetch = original; }
});
