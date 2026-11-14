import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = fileURLToPath(new URL("../../", import.meta.url));
const profiles = JSON.parse(execFileSync(path.join(root, ".venv/bin/python"), ["-c",
  "import json; from pipeline.demo_data import four_candidates; print(json.dumps(four_candidates()))"], { cwd: root, encoding: "utf8" }));

test("first-user upload errors, contrasting jobs and failed-request retry keep original results", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("Accepted 50 profiles", { exact: false })).toBeVisible();
  await page.getByLabel("Candidate dataset", { exact: true }).selectOption("upload");
  const file = page.getByLabel("Upload candidate JSON", { exact: false });
  await file.setInputFiles({ name: "broken.json", mimeType: "application/json", buffer: Buffer.from("{not JSON") });
  await expect(page.getByRole("alert")).toContainText("valid UTF-8 JSON");
  await file.setInputFiles({ name: "invalid.json", mimeType: "application/json", buffer: Buffer.from('[{}]') });
  await expect(page.getByRole("alert")).toContainText("Profile 1");
  let uploads = 0;
  page.on("request", (request) => { if (request.method() === "POST" && request.url().endsWith("/api/datasets")) uploads++; });
  await file.setInputFiles({ name: "large.json", mimeType: "application/json", buffer: Buffer.alloc(10 * 1024 * 1024 + 1, " ") });
  await expect(page.getByRole("alert")).toContainText("no larger than 10 MiB");
  expect(uploads).toBe(0);
  await expect(page.getByRole("button", { name: "Run Ranking", exact: true })).toBeDisabled();
  await file.setInputFiles({ name: "fictional.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(profiles)) });
  await expect(page.getByText("Accepted 4 profiles", { exact: false })).toBeVisible();
  async function job(designer: boolean) {
    await page.getByLabel("Job to rank for").selectOption("custom");
    await page.getByLabel("Job title (required)", { exact: true }).fill(designer ? "Brand Designer" : "Backend Engineer");
    await page.getByLabel("Job description (required", { exact: false }).fill(designer
      ? "Create visual brand identities and accessible design assets with Figma and Illustrator."
      : "Build reliable production Java services with PostgreSQL and Docker deployment.");
    await page.getByLabel("Required skills", { exact: true }).fill(designer ? "Figma, Illustrator" : "Java, PostgreSQL");
    await page.getByLabel("Preferred skills", { exact: true }).fill(designer ? "" : "Docker");
  }
  async function run() {
    const pending = page.waitForResponse((response) => response.url().endsWith("/api/rank") && response.request().method() === "POST");
    await page.getByRole("button", { name: "Run Ranking", exact: true }).click();
    const response = await pending; expect(response.ok()).toBe(true); return response.json();
  }
  await job(false);
  const backend = await run();
  expect(backend.results[0].candidate_id).toBe("F-BACKEND");
  expect(backend.results[0].structured.matched_skills).toEqual(["Java", "PostgreSQL", "Docker"]);
  expect(backend.results[0].reasoning).toContain("Backend Engineer");
  expect(backend.results[0].reasoning).toContain("Java");
  const oldId = backend.results[0].candidate_id;
  await job(true);
  await page.route("**/api/rank", (route) => route.abort("failed"), { times: 1 });
  await page.getByRole("button", { name: "Run Ranking", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Check that the local API is running");
  await expect(page.getByLabel("Result job", { exact: true })).toContainText("Backend Engineer");
  await expect(page.locator("[data-candidate-id]").first()).toHaveAttribute("data-candidate-id", oldId);
  await expect(page.getByRole("button", { name: "Run Ranking", exact: true })).toBeEnabled();
  const design = await run();
  expect(design.results[0].candidate_id).toBe("F-DESIGN");
  expect(design.results[0].structured.matched_skills).toEqual(["Figma", "Illustrator"]);
  expect(design.results[0].reasoning).toContain("Brand Designer");
  expect(design.results[0].reasoning).toContain("Figma");
  expect(design.results[0].reasoning).not.toContain("Java");
  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(page.getByLabel("Result job", { exact: true })).toContainText("Brand Designer");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
