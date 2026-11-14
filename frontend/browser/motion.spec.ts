import { test, expect } from "@playwright/test";

for (const reducedMotion of ["no-preference", "reduce"] as const) {
  test(`ranking and review remain immediate with motion ${reducedMotion}`, async ({ page }) => {
    await page.emulateMedia({ reducedMotion });
    await page.goto("/");
    await expect(page.getByText("Accepted 50 profiles", { exact: false })).toBeVisible();
    await page.evaluate(() => document.fonts.ready);
    const fonts = await page.evaluate(() => ({ sans: document.fonts.check('14px "Instrument Sans"'), serif: document.fonts.check('40px "Instrument Serif"') }));
    expect(fonts).toEqual({ sans: true, serif: true });
    const contrast = await page.evaluate(() => {
      const styles = getComputedStyle(document.documentElement);
      const luminance = (hex: string) => {
        const rgb = hex.trim().replace("#", "").match(/../g)!.map((channel) => {
          const value = parseInt(channel, 16) / 255;
          return value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4;
        });
        return rgb[0] * .2126 + rgb[1] * .7152 + rgb[2] * .0722;
      };
      const ratio = (foreground: string, background: string) => {
        const a = luminance(styles.getPropertyValue(foreground));
        const b = luminance(styles.getPropertyValue(background));
        return (Math.max(a, b) + .05) / (Math.min(a, b) + .05);
      };
      return { ink: ratio("--ink", "--paper"), muted: ratio("--muted", "--paper"),
        primary: ratio("--forest", "--surface"), warning: ratio("--warning", "--warning-bg"),
        error: ratio("--error", "--error-bg"), inputBorder: ratio("--line-strong", "--surface") };
    });
    for (const key of ["ink", "muted", "primary", "warning", "error"] as const) expect(contrast[key]).toBeGreaterThanOrEqual(4.5);
    expect(contrast.inputBorder).toBeGreaterThanOrEqual(3);
    // Hold the actual request, not a fabricated response, to observe the real loading state.
    let release!: () => void;
    const held = new Promise<void>((resolve) => { release = resolve; });
    await page.route("**/api/rank", async (route) => { await held; await route.continue(); }, { times: 1 });
    const pending = page.waitForResponse((response) => response.url().endsWith("/api/rank") && response.request().method() === "POST");
    await page.getByRole("button", { name: "Run Ranking", exact: true }).click();
    const busy = page.getByRole("button", { name: "Ranking…", exact: false });
    await expect(busy).toBeDisabled();
    await expect(busy).toHaveAttribute("aria-busy", "true");
    await expect(page.getByText("Ranking candidates…", { exact: false })).toBeVisible();
    release();
    const response = await pending; expect(response.ok()).toBe(true);
    const ranking = await response.json();
    const fresh = page.locator(".fresh-results");
    await expect(fresh).toBeVisible();
    await expect(fresh).toHaveCSS("animation-name", reducedMotion === "reduce" ? "none" : "results-enter");
    if (reducedMotion !== "reduce") await expect(fresh).toHaveCSS("animation-duration", "0.22s");
    // Capture animation identity. Filtering must not remount or restart the entrance.
    const entrance = await fresh.evaluate((element) => {
      const animation = element.getAnimations()[0];
      if (animation) { (window as unknown as { initialEntrance: Animation }).initialEntrance = animation; }
      return Boolean(animation);
    });
    const search = page.getByLabel("Search title or matched skill", { exact: true });
    await search.scrollIntoViewIfNeeded(); await search.focus();
    const before = await page.evaluate(() => scrollY);
    await search.fill("AI");
    await expect(search).toBeFocused();
    expect(Math.abs(await page.evaluate(() => scrollY) - before)).toBeLessThanOrEqual(2);
    const sameAnimation = await fresh.evaluate((element) => {
      const previous = (window as unknown as { initialEntrance?: Animation }).initialEntrance;
      const active = element.getAnimations();
      return !previous || active.length === 0 || active.includes(previous);
    });
    expect(sameAnimation).toBe(true);
    if (reducedMotion === "reduce") expect(entrance).toBe(false);
    await page.getByRole("button", { name: "Reset filters", exact: true }).click();
    const row = page.locator("[data-candidate-id]").first();
    const toggle = row.getByRole("button", { name: "Details", exact: false });
    await toggle.focus(); await page.keyboard.press("Enter");
    await expect(toggle).toHaveAttribute("aria-expanded", "true");
    await expect(row.locator(".detail-reveal")).toHaveAttribute("data-open", "true");
    await expect(toggle).toBeFocused();
    const duration = await row.locator(".detail-reveal").evaluate((element) => getComputedStyle(element).transitionDuration);
    expect(duration).toBe(reducedMotion === "reduce" ? "0s" : "0.22s, 0.22s");
    await page.keyboard.press("Enter");
    await expect(row.locator(".detail-reveal")).toHaveAttribute("inert", "");
    const id = ranking.results[0].candidate_id;
    await page.getByLabel(`Compare ${id}`, { exact: true }).check();
    const comparison = page.getByLabel("Candidate comparison", { exact: true });
    await expect(comparison.locator("article")).toHaveCount(1);
    await expect(comparison.locator("article")).toHaveCSS("animation-name", reducedMotion === "reduce" ? "none" : "panel-enter");
    if (reducedMotion === "reduce") expect(await comparison.evaluate((element) => element.getAnimations({ subtree: true }).length)).toBe(0);
    await page.getByRole("button", { name: `Add ${id} to shortlist`, exact: true }).click();
    await expect(page.getByRole("button", { name: `Remove ${id} from shortlist`, exact: true })).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator(".shortlist-feedback")).toContainText("added to shortlist");
    // Stress the form and returned-requirement control with a long fictional requirement.
    await page.getByLabel("Job to rank for").selectOption("custom");
    await page.getByLabel("Job title (required)", { exact: true }).fill("Fictional search infrastructure engineer");
    await page.getByLabel("Job description (required", { exact: false }).fill("Build and evaluate reliable production search infrastructure and retrieval services.");
    await page.getByLabel("Required skills", { exact: true }).fill("Production information retrieval and recommendation evaluation ownership");
    const next = page.waitForResponse((res) => res.url().endsWith("/api/rank") && res.request().method() === "POST");
    await page.getByRole("button", { name: "Run Ranking", exact: true }).click();
    expect((await next).ok()).toBe(true);
    await expect(page.getByRole("combobox", { name: "Recorded match for job requirement", exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}
