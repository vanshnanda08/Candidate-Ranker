/** Opt-in React DOM workflow against the real local API and fictional demo file. */
import assert from "node:assert/strict";
import { test } from "node:test";
import { JSDOM } from "jsdom";
import { act, createElement } from "react";

test("real local API: custom ranking through filters, comparison, saved notes, refresh, job isolation and exports", async () => {
  const dataset = process.env.TALENTLENS_DEMO_DATASET;
  assert.ok(dataset, "Set TALENTLENS_DEMO_DATASET to the fictional file from scripts/make_post_ranking_demo.py");
  const dom = new JSDOM('<!doctype html><div id="root"></div>', { url: "http://127.0.0.1:5173" });
  Object.defineProperties(globalThis, { window: { value: dom.window, configurable: true },
    document: { value: dom.window.document, configurable: true }, navigator: { value: dom.window.navigator, configurable: true },
    HTMLElement: { value: dom.window.HTMLElement, configurable: true }, HTMLInputElement: { value: dom.window.HTMLInputElement, configurable: true },
    IS_REACT_ACT_ENVIRONMENT: { value: true, configurable: true },
    ResizeObserver: { value: class { observe() {} unobserve() {} disconnect() {} }, configurable: true } });
  const { createRoot } = await import("react-dom/client");
  const { default: App } = await import("../src/App.tsx");
  const nativeFetch = globalThis.fetch;
  let rankingCalls = 0;
  globalThis.fetch = (url, init) => {
    if (String(url).endsWith("/api/rank")) rankingCalls++;
    return nativeFetch(new URL(String(url), "http://127.0.0.1:8000"), init);
  };
  const downloads: { filename: string; blob: Blob }[] = [];
  const originalCreate = URL.createObjectURL, originalRevoke = URL.revokeObjectURL;
  const blobs = new Map<string, Blob>();
  URL.createObjectURL = (blob) => { const key = `blob:local-${blobs.size}`; blobs.set(key, blob); return key; };
  URL.revokeObjectURL = () => {};
  dom.window.HTMLAnchorElement.prototype.click = function () { downloads.push({ filename: this.download, blob: blobs.get(this.href)! }); };
  const element = (selector: string) => {
    const value = document.querySelector<HTMLElement>(selector); assert.ok(value, selector); return value;
  };
  const button = (label: string) => {
    const value = [...document.querySelectorAll("button")].find((node) => node.textContent?.trim() === label);
    assert.ok(value, label); return value;
  };
  const field = (label: string) => {
    const node = [...document.querySelectorAll("label")].find((entry) => entry.textContent?.trim().startsWith(label));
    assert.ok(node, label);
    return (node.htmlFor ? element(`#${node.htmlFor}`) : node.querySelector("input,textarea,select") ?? node.nextElementSibling) as HTMLInputElement;
  };
  async function enter(node: HTMLInputElement, value: string) {
    await act(async () => {
      const prototype = node.tagName === "SELECT" ? dom.window.HTMLSelectElement.prototype : node.tagName === "TEXTAREA"
        ? dom.window.HTMLTextAreaElement.prototype : dom.window.HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(prototype, "value")!.set!.call(node, value);
      node.dispatchEvent(new dom.window.Event(node.tagName === "SELECT" ? "change" : "input", { bubbles: true }));
    });
  }
  async function click(node: HTMLElement) { await act(async () => node.click()); }
  async function job(design = false) {
    await enter(field("Candidates file path"), dataset!);
    await enter(field("Job to rank for"), "custom"); await enter(field("Job title"), "Platform Engineer");
    await enter(field("Job description"), design ? "Create visual brand identities and accessible design assets." : "Build reliable Java services and relational data products.");
    await enter(field("Required skills"), design ? "Figma, Illustrator" : "Java, PostgreSQL");
    await enter(field("Preferred skills"), design ? "" : "Docker");
    await enter(field("Minimum experience"), "3"); await enter(field("Maximum experience"), "10");
  }
  async function run() {
    pendingRank = undefined;
    await act(async () => {
      element("#ranking-job").dispatchEvent(new dom.window.Event("submit", { bubbles: true, cancelable: true }));
      assert.ok(pendingRank, "Submitting the form must start an HTTP ranking request");
      await pendingRank;
    });
  }
  // Track HTTP completion without coupling tests to internal App state.
  let pendingRank: Promise<void> | undefined;
  const trackedFetch = globalThis.fetch;
  globalThis.fetch = (url, init) => {
    const pending = trackedFetch(url, init);
    if (String(url).endsWith("/api/rank")) pendingRank = pending.then(async (response) => {
      const body = await response.clone().text(); assert.equal(response.status, 200, body);
    });
    return pending;
  };
  let root = createRoot(element("#root"));
  try {
    await act(async () => root.render(createElement(App)));
    await job(); await run();
    assert.match(document.body.textContent!, /Results for: Platform Engineer/);
    await enter(field("Search title"), "PostgreSQL"); await enter(field("Minimum years"), "5");
    await enter(field("Maximum years"), "8"); await enter(field("Recorded match"), "PostgreSQL");
    assert.match(document.body.textContent!, /Showing 2 of 4 returned/);
    await click(element('input[aria-label="Compare F-BACKEND"]'));
    await click(element('input[aria-label="Compare F-DATA"]'));
    await enter(field("Search title"), "does not match");
    assert.match(document.body.textContent!, /No returned candidates match/);
    assert.match(element('[aria-label="Candidate comparison"]').textContent!, /Compare candidates \(2\/3\)/);
    assert.equal(rankingCalls, 1);
    await click(button("Reset filters"));
    await click(element('[aria-label="Add F-BACKEND to shortlist"]'));
    await click(element('[aria-label="Add F-DATA to shortlist from comparison"]'));
    await click(button("Shortlist"));
    const note = '=Follow up, "implementation"\nAsk about tests';
    await enter(field("Notes for F-BACKEND"), note);
    await click(button("Export shortlist.csv"));
    assert.equal(downloads[0].filename, "shortlist.csv");
    assert.match(await downloads[0].blob.text(), /"'=Follow up, ""implementation""\nAsk about tests"/);
    await act(async () => root.unmount()); root = createRoot(element("#root"));
    await act(async () => root.render(createElement(App)));
    assert.equal(field("Notes for F-BACKEND").value, note); assert.equal(rankingCalls, 1);
    await job(true); await run();
    assert.match(document.body.textContent!, /Compare candidates \(0\/3\)/);
    await click(button("Shortlist")); assert.match(document.body.textContent!, /No candidates saved for this job/);
    const selector = field("Shortlist job and dataset") as unknown as HTMLSelectElement;
    await enter(selector as unknown as HTMLInputElement, selector.options[0].value);
    assert.equal(field("Notes for F-BACKEND").value, note);
    await enter(field("Job to rank for"), "default"); await run();
    assert.match(document.body.textContent!, /Results for: Senior AI Engineer/);
    await enter(field("Search title"), "backend");
    await click(button("Download submission.csv (all returned)"));
    const submission = await downloads.at(-1)!.blob.text();
    assert.equal(downloads.at(-1)!.filename, "submission.csv");
    assert.equal(submission.split("\n").length, 5); assert.match(submission, /^candidate_id,rank,score,reasoning\n/);
    assert.equal(rankingCalls, 3);
  } finally {
    await act(async () => root.unmount()); globalThis.fetch = nativeFetch;
    URL.createObjectURL = originalCreate; URL.revokeObjectURL = originalRevoke;
  }
});
