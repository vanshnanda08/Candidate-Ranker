import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = fileURLToPath(new URL("../../", import.meta.url));
const python = path.join(root, ".venv/bin/python");
const profiles = JSON.parse(execFileSync(python, ["-c", "import json; from pipeline.demo_data import four_candidates; print(json.dumps(four_candidates()))"], { cwd: root, encoding: "utf8" }));
const parseCsv = (filename: string) => JSON.parse(execFileSync(python,
  ["-c", "import csv,json,sys; print(json.dumps(list(csv.DictReader(sys.stdin))))"], { input: readFileSync(filename), encoding: "utf8" }));

test("fictional upload through review, real refresh, isolation and both downloads", async ({ page }, info) => {
  const failures: string[] = [];
  page.on("pageerror", (error) => failures.push(error.message));
  let calls = 0;
  page.on("request", (request) => { if (request.method() === "POST" && request.url().endsWith("/api/rank")) calls++; });
  await page.goto("/");
  await expect(page.getByText("Accepted 50 profiles", { exact: false })).toBeVisible();
  await page.getByLabel("Candidate dataset", { exact: true }).selectOption("upload");
  const file = page.getByLabel("Upload candidate JSON", { exact: false });
  await file.setInputFiles({ name: "invalid.json", mimeType: "application/json", buffer: Buffer.from('[{}]') });
  await expect(page.getByRole("alert")).toContainText("Profile 1");
  await expect(page.getByRole("button", { name: "Run Ranking" })).toBeDisabled();
  async function upload(rows = profiles) {
    await file.setInputFiles({ name: "same.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(rows)) });
    await expect(page.getByText("Accepted 4 profiles", { exact: false })).toBeVisible();
  }
  async function custom(design = false) {
    await page.getByLabel("Job to rank for").selectOption("custom");
    await page.getByLabel("Job title (required)", { exact: true }).fill("Platform Engineer");
    await page.getByLabel("Job description (required", { exact: false }).fill(design
      ? "Create visual brand identities and accessible design assets." : "Build reliable Java services and relational data products.");
    await page.getByLabel("Required skills", { exact: true }).fill(design ? "Figma, Illustrator" : "Java, PostgreSQL");
    await page.getByLabel("Preferred skills", { exact: true }).fill(design ? "" : "Docker");
    await page.getByLabel("Minimum experience (optional years)", { exact: true }).fill("3");
    await page.getByLabel("Maximum experience (optional years)", { exact: true }).fill("10");
  }
  async function run() {
    const response = page.waitForResponse((res) => res.url().endsWith("/api/rank") && res.request().method() === "POST");
    await page.getByRole("button", { name: "Run Ranking" }).click();
    const res = await response; expect(res.status()).toBe(200);
    await expect(page.getByLabel("Filters for returned results", { exact: true })).toBeVisible();
    return res.json();
  }
  await upload(); await custom();
  const initial = await run();
  const ranks = new Map(initial.results.map((r: { candidate_id: string; rank: number }) => [r.candidate_id, String(r.rank)]));
  const search = page.getByLabel("Search title or matched skill", { exact: true });
  await search.fill("PostgreSQL");
  await page.getByLabel("Minimum years of experience", { exact: true }).fill("5");
  await page.getByLabel("Maximum years of experience", { exact: true }).fill("8");
  await page.getByRole("combobox", { name: "Recorded match for job requirement", exact: true }).selectOption("PostgreSQL");
  await expect(page.getByText("Showing 2 of 4 returned candidates", { exact: false })).toBeVisible();
  for (const id of ["F-BACKEND", "F-DATA"]) {
    await expect(page.locator(`[data-candidate-id="${id}"]`)).toHaveAttribute("data-original-rank", ranks.get(id) as string);
  }
  const compare = page.getByLabel("Compare F-BACKEND", { exact: true });
  await compare.focus(); await page.keyboard.press("Space");
  await expect(compare).toBeChecked(); await expect(compare).toHaveCSS("outline-style", "solid");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Add F-BACKEND to shortlist", exact: true })).toBeFocused();
  await page.getByLabel("Compare F-DATA", { exact: true }).check();
  await search.fill("no such profile");
  await expect(page.getByText("No returned candidates match", { exact: false })).toBeVisible();
  const comparison = page.getByLabel("Candidate comparison", { exact: true });
  await expect(comparison.locator("article")).toHaveCount(2);
  await expect(comparison.getByText("No matching evidence", { exact: true })).toHaveCount(1);
  expect(calls).toBe(1);
  await page.getByRole("button", { name: "Reset filters", exact: true }).click();
  await page.getByLabel("Compare F-DESIGN", { exact: true }).check();
  await expect(page.getByLabel("Compare F-JUNIOR", { exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "Remove F-DESIGN from comparison", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(comparison.locator("article")).toHaveCount(2);
  const boxes = await comparison.locator("article").evaluateAll((nodes) => nodes.map((node) => {
    const { x, y, width, height } = node.getBoundingClientRect(); return { x, y, width, height };
  }));
  if (info.project.name === "narrow") expect(boxes[1].y).toBeGreaterThan(boxes[0].y + boxes[0].height);
  else expect(boxes[1].x).toBeGreaterThan(boxes[0].x);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await comparison.screenshot({ path: info.outputPath("comparison.png") });
  await page.getByRole("button", { name: "Add F-BACKEND to shortlist", exact: true }).click();
  await page.getByRole("button", { name: "Add F-DATA to shortlist from comparison", exact: true }).click();
  await page.getByRole("button", { name: "Shortlist", exact: true }).click();
  const note = '=Discuss, "ownership"\nAsk about tests';
  await page.getByRole("textbox", { name: "Notes for F-BACKEND", exact: true }).fill(note);
  await page.reload();
  await expect(page.getByRole("textbox", { name: "Notes for F-BACKEND", exact: true })).toHaveValue(note);
  expect(calls).toBe(1);
  const dl = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export shortlist.csv", exact: true }).click();
  const download = await dl; const shortlist = info.outputPath("shortlist.csv"); await download.saveAs(shortlist);
  expect(download.suggestedFilename()).toBe("shortlist.csv");
  const saved = parseCsv(shortlist); expect(saved).toHaveLength(2);
  expect(saved.find((row: { candidate_id: string }) => row.candidate_id === "F-BACKEND").notes).toBe("'" + note);
  await page.getByLabel("Candidate dataset", { exact: true }).selectOption("upload");
  await upload(); await custom(true); await run();
  await expect(comparison.locator("article")).toHaveCount(0);
  await page.getByRole("button", { name: "Shortlist", exact: true }).click();
  await expect(page.getByText("No candidates saved for this job", { exact: false })).toBeVisible();
  await page.getByRole("combobox", { name: "Shortlist job and dataset", exact: true }).selectOption({ index: 0 });
  await expect(page.getByRole("textbox", { name: "Notes for F-BACKEND", exact: true })).toHaveValue(note);
  const changed = structuredClone(profiles); changed[0].profile.summary += " Maintained a separate fictional API.";
  await upload(changed); await custom(); const other = await run();
  expect(other.dataset.dataset_id).not.toBe(initial.dataset.dataset_id);
  await page.getByRole("button", { name: "Shortlist", exact: true }).click();
  await expect(page.getByText("No candidates saved for this job", { exact: false })).toBeVisible();
  await page.getByRole("combobox", { name: "Shortlist job and dataset", exact: true }).selectOption({ index: 0 });
  await expect(page.getByRole("textbox", { name: "Notes for F-BACKEND", exact: true })).toHaveValue(note);
  await page.getByLabel("Candidate dataset", { exact: true }).selectOption("demo");
  await page.getByLabel("Job to rank for").selectOption("default");
  await expect(page.getByText("Accepted 50 profiles", { exact: false })).toBeVisible();
  const builtin = await run(); expect(builtin.total_candidates).toBe(50);
  await search.fill("AI");
  const submissionEvent = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download submission.csv", exact: false }).click();
  const submission = await submissionEvent; const exported = info.outputPath("submission.csv"); await submission.saveAs(exported);
  expect(submission.suggestedFilename()).toBe("submission.csv");
  const rows = parseCsv(exported); expect(rows).toHaveLength(builtin.results.length);
  expect(rows.map((r: { candidate_id: string }) => r.candidate_id)).toEqual(builtin.results.map((r: { candidate_id: string }) => r.candidate_id));
  expect(rows.map((r: { candidate_id: string; rank: string; score: string }) => [r.candidate_id, Number(r.rank), Number(r.score)]))
    .toEqual(builtin.results.map((r: { candidate_id: string; rank: number; display_score: number }) => [r.candidate_id, r.rank, r.display_score]));
  expect(Object.keys(rows[0])).toEqual(["candidate_id", "rank", "score", "reasoning"]);
  await page.getByRole("button", { name: "Benchmark", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Single-role benchmark", exact: false })).toBeVisible();
  await expect(page.getByText("71-profile judged pool", { exact: false })).toBeVisible();
  await expect(page.getByText("0.974410", { exact: true }).filter({ visible: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath("benchmark.png"), fullPage: true });
  expect(failures).toEqual([]);
});
