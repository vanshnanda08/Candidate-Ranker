import assert from "node:assert/strict";
import { test } from "node:test";
import { JSDOM } from "jsdom";
import { act, createElement } from "react";
import { candidate, job } from "./fixtures.ts";
import { STORAGE_KEY } from "../src/shortlist.ts";
import type { CandidateResult, RankRequest, RankResponse } from "../src/types";

const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', { url: "http://localhost:5173" });
Object.defineProperties(globalThis, {
  window: { value: dom.window, configurable: true }, document: { value: dom.window.document, configurable: true },
  navigator: { value: dom.window.navigator, configurable: true },
  HTMLElement: { value: dom.window.HTMLElement, configurable: true },
  HTMLInputElement: { value: dom.window.HTMLInputElement, configurable: true },
  IS_REACT_ACT_ENVIRONMENT: { value: true, configurable: true },
  ResizeObserver: { value: class { observe() {} unobserve() {} disconnect() {} }, configurable: true },
});
const { createRoot } = await import("react-dom/client");
const { default: App } = await import("../src/App.tsx");
const requests: RankRequest[] = [];
const responses: RankResponse[] = [];
const downloads: { filename: string; blob: Blob }[] = [];
const blobs = new Map<string, Blob>();
const nativeFetch = globalThis.fetch;
const nativeCreate = URL.createObjectURL, nativeRevoke = URL.revokeObjectURL;
const nativeStorage = dom.window.localStorage;
const builtin = { ...job, mode: "default" as const, title: "Senior AI Engineer", required_skills: ["Python", "FAISS"], preferred_skills: ["Docker"] };

function fullCandidate(id: string, rank: number, title: string, years: number, skills: string[]): CandidateResult {
  return { ...candidate(id, rank, title, years, skills), name: id, current_company: "Fictional Studio",
    location: "Fictional City", current_industry: "Software", current_company_size: "51-200", semantic_score: .5,
    structured: { skill_score: .5, structured_score: .5, career_score: .5, edu_score: .5, exp_score: .5,
      loc_score: .5, matched_skills: skills, must_have_skill_count: skills.length },
    behavioral: { behavioral_score: .5, open_to_work: 1, activity_score: 1, inactive_days: 1, response_rate: .5,
      interview_completion: .5, notice_days: 30, github_score: .5, trust_score: .5, demand_score: .5 },
    honeypot_flags: [], honeypot_penalty: 1 };
}
const fixtures = [fullCandidate("F-1", 1, "Backend Engineer", 8, ["Java", "PostgreSQL", "Docker"]),
  fullCandidate("F-2", 2, "Data Engineer", 5, ["PostgreSQL", "Docker"]),
  fullCandidate("F-3", 3, "Brand Designer", 6, ["Figma", "Illustrator"]),
  fullCandidate("F-4", 4, "Frontend Engineer", 2, ["JavaScript"])];

function setup() {
  requests.length = 0; responses.length = 0; downloads.length = 0;
  globalThis.fetch = async (url, init) => {
    if (String(url).endsWith("/api/datasets/demo")) return new Response(JSON.stringify({ dataset_id: "demo", fingerprint: "a".repeat(64), label: "Fictional demo", profile_count: 50, kind: "demo" }));
    if (String(url).endsWith("/api/jd")) return new Response(JSON.stringify({ raw_text: builtin.description,
      must_have_skills: builtin.required_skills, nice_to_have_skills: builtin.preferred_skills }));
    assert.ok(String(url).endsWith("/api/rank"));
    const payload = JSON.parse(String(init?.body)); requests.push(payload);
    const submitted = payload.job ? { ...payload.job, mode: "custom", scoring_notes: "fixture" } : builtin;
    const result = { job: submitted, total_candidates: 4, top_n: 4, honeypots_in_top: 0, top_score: .99,
      results: fixtures.map((entry) => ({ ...entry, structured: { ...entry.structured,
        matched_skills: entry.structured.matched_skills.filter((skill) => submitted.required_skills.includes(skill)
          || (submitted.mode === "custom" && submitted.preferred_skills.includes(skill))) } })) };
    responses.push(result);
    return new Response(JSON.stringify(result));
  };
  URL.createObjectURL = (blob) => { const key = `blob:fixture-${blobs.size}`; blobs.set(key, blob); return key; };
  URL.revokeObjectURL = () => {};
  dom.window.HTMLAnchorElement.prototype.click = function () { downloads.push({ filename: this.download, blob: blobs.get(this.href)! }); };
}

function element<T extends Element>(selector: string): T {
  const value = document.querySelector(selector);
  assert.ok(value, `Missing ${selector}`);
  return value as T;
}
function button(label: string): HTMLButtonElement {
  const found = [...document.querySelectorAll("button")].find((entry) => entry.textContent?.trim() === label);
  assert.ok(found, `Missing button ${label}`); return found;
}
function field(label: string): HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement {
  const match = [...document.querySelectorAll("label")].find((entry) => entry.textContent?.trim().startsWith(label));
  assert.ok(match, `Missing label ${label}`);
  return match.htmlFor ? element(`#${match.htmlFor}`) : (match.querySelector("input,textarea,select") ?? match.nextElementSibling)! as HTMLInputElement;
}
async function enter(target: HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement, value: string) {
  await act(async () => {
    const prototype = target.tagName === "SELECT" ? dom.window.HTMLSelectElement.prototype : target.tagName === "TEXTAREA"
      ? dom.window.HTMLTextAreaElement.prototype : dom.window.HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(prototype, "value")!.set!.call(target, value);
    target.dispatchEvent(new dom.window.Event(target.tagName === "SELECT" ? "change" : "input", { bubbles: true }));
  });
}
async function click(target: HTMLElement) { await act(async () => target.click()); }
async function run() {
  await act(async () => element("#ranking-job").dispatchEvent(new dom.window.Event("submit", { bubbles: true, cancelable: true })));
}
async function fillCustom(required = "Java, PostgreSQL", description = job.description) {
  await enter(field("Candidates file path"), "fictional.json");
  await enter(field("Job to rank for"), "custom");
  await enter(field("Job title"), "Platform Engineer");
  await enter(field("Job description"), description);
  await enter(field("Required skills"), required);
  await enter(field("Preferred skills"), required.includes("Java") ? "Docker" : "");
}

test("dashboard full workflow: custom ranking, local filters, comparison, notes, refresh, same-title isolation and exports", async () => {
  setup(); nativeStorage.clear();
  let root = createRoot(element("#root"));
  try {
    await act(async () => root.render(createElement(App)));
    await fillCustom(); await run();
    assert.equal(requests.length, 1); assert.equal(requests[0].job?.title, "Platform Engineer");
    assert.match(document.body.textContent!, /Results for: Platform Engineer/);
    await enter(field("Search title"), "PostgreSQL");
    assert.match(document.body.textContent!, /Showing 2 of 4 returned/);
    await enter(field("Minimum years"), "5"); await enter(field("Maximum years"), "8");
    await enter(field("Recorded match"), "PostgreSQL");
    await click(element('input[aria-label="Compare F-1"]'));
    await click(element('input[aria-label="Compare F-2"]'));
    await enter(field("Search title"), "not present");
    assert.match(document.body.textContent!, /No returned candidates match/);
    assert.match(document.body.textContent!, /Compare candidates \(2\/3\)/);
    assert.match(element('[aria-label="Candidate comparison"]').textContent!, /Original rank #2/);
    assert.match(element('[aria-label="Candidate comparison"]').textContent!, /No matching evidence/);
    assert.equal(requests.length, 1, "Filters/comparison must not call the ranker");
    await click(button("Reset filters"));
    await click(element('input[aria-label="Compare F-3"]'));
    assert.equal(element<HTMLInputElement>('input[aria-label="Compare F-4"]').disabled, true);
    element<HTMLInputElement>('input[aria-label="Compare F-1"]').focus();
    assert.equal(document.activeElement?.getAttribute("aria-label"), "Compare F-1");
    await click(element('input[aria-label="Compare F-3"]'));
    await click(element('[aria-label="Add F-1 to shortlist"]'));
    await click(element('[aria-label="Add F-2 to shortlist from comparison"]'));
    await click(button("Shortlist"));
    const note = '=Discuss, "ownership"\nSecond line';
    await enter(field("Notes for F-1"), note);
    await click(button("Export shortlist.csv"));
    assert.match(await downloads[0].blob.text(), /"'=Discuss, ""ownership""\nSecond line"/);
    assert.equal(downloads[0].filename, "shortlist.csv");
    const saved = JSON.parse(nativeStorage.getItem(STORAGE_KEY)!);
    assert.equal(saved.scopes[0].entries.length, 2);
    assert.deepEqual(Object.keys(saved.scopes[0].entries[0]).sort(), ["candidate_id", "notes", "original_rank", "title"]);
    await act(async () => root.unmount());
    root = createRoot(element("#root"));
    await act(async () => root.render(createElement(App)));
    assert.equal(field("Notes for F-1").value, note);
    assert.equal(requests.length, 1, "Refresh recovery must not call the ranker");
    await fillCustom(); await run();
    await click(element('input[aria-label="Compare F-1"]'));
    await enter(field("Search title"), "backend");
    await fillCustom("Figma, Illustrator", "Create visual brand identities and accessible design assets.");
    await run();
    assert.match(element('[aria-label="Candidate comparison"]').textContent!, /Compare candidates \(0\/3\)/);
    assert.equal(field("Search title").value, "");
    await click(button("Shortlist"));
    assert.match(document.body.textContent!, /No candidates saved for this job/);
    const select = field("Shortlist job and dataset");
    await enter(select, (select as HTMLSelectElement).options[0].value);
    assert.equal(field("Notes for F-1").value, note);
    await click(button("Returned results"));
    await click(element('input[aria-label="Compare F-3"]'));
    await click(element('[aria-label="Add F-3 to shortlist from comparison"]'));
    await click(element('[aria-label="Remove F-3 from shortlist from comparison"]'));
    await click(element('[aria-label="Add F-3 to shortlist"]'));
    assert.equal(JSON.parse(nativeStorage.getItem(STORAGE_KEY)!).scopes.length, 2);
    await enter(field("Job to rank for"), "default"); await run();
    assert.equal(responses.at(-1)!.job.mode, "default");
    assert.match(document.body.textContent!, /Results for: Senior AI Engineer/);
    await enter(field("Search title"), "backend");
    await click(button("Download submission.csv (all returned)"));
    const submission = await downloads.at(-1)!.blob.text();
    assert.equal(downloads.at(-1)!.filename, "submission.csv");
    assert.equal(submission.split("\n")[0], "candidate_id,rank,score,reasoning");
    assert.equal(submission.split("\n").length, 5, "Submission includes four unfiltered rows");
    assert.equal(requests.length, 4); // A, A after refresh, B, built-in; never filter/save requests.
  } finally { await act(async () => root.unmount()); }
});

test("dashboard remains usable with denied or malformed storage", async () => {
  for (const denied of [true, false]) {
    setup(); nativeStorage.clear();
    if (denied) Object.defineProperty(dom.window, "localStorage", { configurable: true, get() { throw new Error("denied"); } });
    else {
      Object.defineProperty(dom.window, "localStorage", { configurable: true, value: nativeStorage });
      nativeStorage.setItem(STORAGE_KEY, "invalid JSON");
    }
    const root = createRoot(element("#root"));
    try {
      await act(async () => root.render(createElement(App)));
      assert.match(document.body.textContent!, denied ? /Browser storage is unavailable/ : /Saved shortlist data is invalid/);
      await run();
      await click(element('[aria-label="Add F-1 to shortlist"]'));
      await click(button("Shortlist"));
      await enter(field("Notes for F-1"), "Session note");
      await click(button("Export shortlist.csv"));
      assert.match(await downloads[0].blob.text(), /Session note/);
    } finally { await act(async () => root.unmount()); }
  }
  Object.defineProperty(dom.window, "localStorage", { configurable: true, value: nativeStorage });
  globalThis.fetch = nativeFetch; URL.createObjectURL = nativeCreate; URL.revokeObjectURL = nativeRevoke;
});
