const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const base = process.env.TTC_SCHOOL_CANDIDATE_URL || "http://127.0.0.1:18577";
const canonicalOrigin = process.env.TTC_CANONICAL_ORIGIN || "https://teachthecompany.com";
const repository = "https://gitlab.finnandre.no/finnandrehotvedt/teach-the-company-public-manuals";
const outputDir = path.resolve("evidence/browser");
fs.mkdirSync(outputDir, { recursive: true });

async function acceptPage(page, route, expectedText) {
  const errors = [];
  const onConsole = (message) => { if (message.type() === "error") errors.push(message.text()); };
  const onPageError = (error) => errors.push(error.message);
  page.on("console", onConsole);
  page.on("pageerror", onPageError);
  const response = await page.goto(base + route, { waitUntil: "networkidle" });
  if (!response || response.status() !== 200) throw new Error(`${route} returned ${response && response.status()}`);
  await page.getByText(expectedText, { exact: false }).first().waitFor();
  const facts = await page.evaluate(() => {
    const fields = [...document.querySelectorAll('input:not([type="hidden"]), select, textarea')];
    return {
      h1: document.querySelectorAll("h1").length,
      viewport: document.documentElement.clientWidth,
      scroll: document.documentElement.scrollWidth,
      unlabelled: fields.filter((field) => {
        if (field.getAttribute("aria-label") || field.getAttribute("aria-labelledby")) return false;
        return !field.id || !document.querySelector(`label[for="${CSS.escape(field.id)}"]`);
      }).length,
      jsonLd: [...document.querySelectorAll('script[type="application/ld+json"]')].map((item) => JSON.parse(item.textContent)),
    };
  });
  if (facts.h1 !== 1) throw new Error(`${route} has ${facts.h1} H1 elements`);
  if (facts.scroll > facts.viewport + 1) throw new Error(`${route} overflows ${facts.scroll}/${facts.viewport}`);
  if (facts.unlabelled) throw new Error(`${route} has ${facts.unlabelled} unlabelled form controls`);
  if (!facts.jsonLd.length) throw new Error(`${route} has no valid JSON-LD`);
  const canonical = await page.locator('link[rel="canonical"]').getAttribute("href");
  if (canonical !== canonicalOrigin + route) throw new Error(`${route} canonical is ${canonical}`);
  if (errors.length) throw new Error(`${route} browser errors: ${errors.join(" | ")}`);
  page.off("console", onConsole);
  page.off("pageerror", onPageError);
  return facts;
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const report = { base, canonicalOrigin, repository, checkedAt: new Date().toISOString(), profiles: [] };
  try {
    for (const profile of [
      { name: "desktop", width: 1440, height: 1000 },
      { name: "mobile", width: 390, height: 844 },
    ]) {
      const context = await browser.newContext({
        viewport: { width: profile.width, height: profile.height },
        userAgent: `TeachSchoolReleaseAcceptance/${profile.name}`,
        acceptDownloads: true,
      });
      const page = await context.newPage();

      await acceptPage(page, "/", "Can you teach it?");
      await page.keyboard.press("Tab");
      if (!(await page.evaluate(() => document.activeElement?.classList.contains("skip-link")))) {
        throw new Error(`${profile.name} skip link is not first focus`);
      }
      await page.locator("[data-chalk-board]").scrollIntoViewIfNeeded();
      await page.locator("[data-chalk-board].chalk-written").waitFor({ timeout: 9000 });
      await page.screenshot({ path: path.join(outputDir, `release-home-${profile.name}.png`), fullPage: true });

      await acceptPage(page, "/school/", "Understand AI");
      if (await page.locator(".school-card").count() !== 20) throw new Error("School does not render twenty lesson cards");

      await acceptPage(page, "/manuals/", "Use the method");
      if (await page.locator(".manual-card").count() !== 5) throw new Error("Manual index does not render five manuals");
      if (await page.locator(`a[href="${repository}"]`).count() !== 1) throw new Error("Dedicated public manual repository link is missing");
      await page.screenshot({ path: path.join(outputDir, `release-manuals-${profile.name}.png`), fullPage: true });

      await acceptPage(page, "/manuals/context-rules-and-memory/", "Build context, rules");
      if (await page.locator(".manual-section").count() !== 3) throw new Error("Manual detail section count is incorrect");
      await page.screenshot({ path: path.join(outputDir, `release-manual-detail-${profile.name}.png`), fullPage: true });

      await acceptPage(page, "/knowledge/freshness/", "Detect changes");
      await page.getByText("No source-change review has been published yet", { exact: false }).waitFor();
      await page.screenshot({ path: path.join(outputDir, `release-freshness-${profile.name}.png`), fullPage: true });

      await acceptPage(page, "/compose/", "Build a learning pack");
      await page.locator('select[name="goal"]').selectOption("teach-agent");
      await page.locator('select[name="experience_level"]').selectOption("practitioner");
      await page.locator('input[name="subjects"][value="TTC-108"]').check();
      await page.locator('textarea[name="use_case"]').fill("Prepare a reviewable summary from approved fictional notes.");
      await page.locator('select[name="provider"]').selectOption("neutral");
      await page.locator('select[name="hosting"]').selectOption("self-hosted");
      await page.locator('select[name="privacy"]').selectOption("standard");
      await page.locator('select[name="autonomy"]').selectOption("approval");
      await page.locator('input[name="tools"]').fill("Django and a local model");
      await page.getByRole("button", { name: "Generate my pack" }).click();
      await page.getByText("Your learning", { exact: false }).first().waitFor();
      const pack = await page.locator("#composition-copy").innerText();
      if (!pack.includes(`${canonicalOrigin}/school/`) || pack.includes("127.0.0.1") || pack.includes("localhost")) {
        throw new Error("Composer pack contains a staging URL or lacks the canonical school URL");
      }
      const downloadPromise = page.waitForEvent("download");
      await page.getByRole("button", { name: "Download Markdown" }).click();
      const download = await downloadPromise;
      if (download.suggestedFilename() !== "teach-the-company-agent-pack.md") throw new Error("Unexpected pack filename");
      await page.screenshot({ path: path.join(outputDir, `release-compose-${profile.name}.png`), fullPage: true });

      report.profiles.push({ ...profile, h1: 1, overflow: 0, unlabelled: 0, manuals: 5, lessons: 20, pack: "canonical" });
      await context.close();
    }
    fs.writeFileSync(path.join(outputDir, "school-release-report.json"), JSON.stringify(report, null, 2) + "\n", { mode: 0o644 });
    console.log("SCHOOL_RELEASE_BROWSER_OK profiles=2 lessons=20 manuals=5 canonical_pack=1 overflow=0 labels=pass chalk=complete");
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error.stack || error.message);
  process.exit(1);
});
