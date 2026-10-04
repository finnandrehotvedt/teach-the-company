const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const base = (process.env.TTC_PREVIEW_URL || "http://127.0.0.1:18574").replace(/\/$/, "");
const canonicalOrigin = (process.env.TTC_CANONICAL_ORIGIN || base).replace(/\/$/, "");
const slug = "esp32-bme280-planning-starter";
const outputDir = path.resolve("evidence/project-library");
fs.mkdirSync(outputDir, { recursive: true });

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function pageFacts(page) {
  return page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
    h1: document.querySelectorAll("h1").length,
    unlabelledButtons: [...document.querySelectorAll("button")].filter((item) => !item.textContent.trim() && !item.getAttribute("aria-label")).length,
    schemas: [...document.querySelectorAll('script[type="application/ld+json"]')].map((item) => JSON.parse(item.textContent)),
  }));
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const report = { base, canonicalOrigin, checkedAt: new Date().toISOString(), profiles: [] };
  try {
    for (const profile of [
      { name: "desktop", width: 1440, height: 1000 },
      { name: "tablet", width: 768, height: 1024 },
      { name: "mobile", width: 390, height: 844 },
      { name: "mobile-small", width: 320, height: 800 },
    ]) {
      const context = await browser.newContext({ viewport: { width: profile.width, height: profile.height }, acceptDownloads: true });
      await context.grantPermissions(["clipboard-read", "clipboard-write"], { origin: base });
      const page = await context.newPage();
      const errors = [];
      page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
      page.on("pageerror", (error) => errors.push(error.message));

      let response = await page.goto(base + "/projects/", { waitUntil: "networkidle" });
      assert(response && response.status() === 200, `${profile.name} project archive did not return 200`);
      await page.getByRole("heading", { name: "Confirm the hardware. Then write the code." }).waitFor();
      assert(await page.locator(".project-card").count() === 1, `${profile.name} archive did not render one published record`);
      let facts = await pageFacts(page);
      assert(facts.h1 === 1 && facts.scroll <= facts.viewport + 1, `${profile.name} archive heading/overflow failed: ${JSON.stringify(facts)}`);
      assert(facts.unlabelledButtons === 0, `${profile.name} archive has an unlabelled button`);
      await page.screenshot({ path: path.join(outputDir, `archive-${profile.name}.png`), fullPage: true });

      response = await page.goto(base + `/projects/${slug}/`, { waitUntil: "networkidle" });
      assert(response && response.status() === 200, `${profile.name} project detail did not return 200`);
      await page.getByRole("heading", { name: "ESP32 + BME280 planning starter", exact: true }).waitFor();
      await page.getByText("No project video is published yet.", { exact: true }).waitFor();
      const canonical = await page.locator('link[rel="canonical"]').getAttribute("href");
      assert(canonical === canonicalOrigin + `/projects/${slug}/`, `${profile.name} canonical is ${canonical}`);
      facts = await pageFacts(page);
      assert(facts.h1 === 1 && facts.scroll <= facts.viewport + 1, `${profile.name} detail heading/overflow failed: ${JSON.stringify(facts)}`);
      const schemaText = JSON.stringify(facts.schemas);
      for (const required of ["WebPage", "CreativeWork", "BreadcrumbList"]) assert(schemaText.includes(required), `${profile.name} schema lacks ${required}`);
      assert(!schemaText.includes("VideoObject"), `${profile.name} schema invents a VideoObject`);
      await page.getByText("Not hardware-verified", { exact: true }).first().waitFor();
      assert(await page.getByText("Not tested", { exact: true }).count() >= 1, `${profile.name} build status is missing`);
      assert(await page.getByText("Not observed", { exact: true }).count() >= 1, `${profile.name} upload status is missing`);
      assert(await page.locator('a[href="https://github.com/finnandrehotvedt/teach-the-company"]').count() === 1, "GitHub source link is missing");
      assert(await page.locator('a[href="https://gitlab.finnandre.no/finnandrehotvedt/teach-the-company"]').count() === 1, "GitLab source link is missing");

      const copyButton = page.getByRole("button", { name: "Copy prompt" });
      await copyButton.focus();
      await copyButton.press("Enter");
      await page.getByText("Prompt copied to the clipboard.", { exact: true }).waitFor();
      assert((await page.evaluate(() => navigator.clipboard.readText())).includes("Reply YES"), `${profile.name} copied prompt is incomplete`);
      await page.waitForTimeout(1900);
      await page.evaluate(() => { navigator.clipboard.writeText = async () => { throw new Error("clipboard denied for acceptance"); }; });
      await copyButton.focus();
      await copyButton.press("Space");
      await page.getByText("Clipboard access was unavailable. The prompt is selected for manual copy.", { exact: true }).waitFor();
      assert((await page.evaluate(() => window.getSelection().toString())).includes("Reply YES"), `${profile.name} manual-copy fallback did not select the prompt`);

      const downloadEvent = page.waitForEvent("download");
      await page.getByRole("link", { name: "Download prompt .txt" }).click();
      const download = await downloadEvent;
      assert(download.suggestedFilename().endsWith("prompt-v1.0.0.txt"), `${profile.name} prompt filename is incorrect`);
      await page.screenshot({ path: path.join(outputDir, `detail-${profile.name}.png`), fullPage: true });
      assert(errors.length === 0, `${profile.name} browser errors: ${errors.join(" | ")}`);

      const jsonResponse = await context.request.get(base + `/projects/${slug}.json`);
      const json = await jsonResponse.json();
      assert(jsonResponse.status() === 200 && json.title === "ESP32 + BME280 planning starter", "JSON detail is inconsistent");
      assert(!jsonResponse.headers()["set-cookie"], "Public JSON response unexpectedly creates a session cookie");
      assert(json.verification.physical_test === "not-hardware-verified" && json.video === null, "JSON truth status is inconsistent");
      const markdownResponse = await context.request.get(base + `/projects/${slug}.md`);
      const markdown = await markdownResponse.text();
      assert(markdownResponse.status() === 200 && markdown.includes("TTC-MCU-001") && markdown.includes("No real, accessible project video"), "Markdown detail is inconsistent");
      const sitemap = await (await context.request.get(base + "/sitemap.xml")).text();
      assert(sitemap.includes(`/projects/${slug}/`) && sitemap.includes("<lastmod>2026-10-04</lastmod>"), "Sitemap propagation is missing");

      const publicText = `${await page.locator("body").innerText()}\n${markdown}\n${JSON.stringify(json)}`;
      assert(!/\b(?:CT|VM)\d{2,3}\b/i.test(publicText), `${profile.name} public output exposes an infrastructure identifier`);
      assert(!/\/(?:srv|var\/backups)\//i.test(publicText), `${profile.name} public output exposes a private path`);
      report.profiles.push({ ...profile, archiveOverflow: 0, detailOverflow: 0, copy: "keyboard-pass", download: "pass", schema: "factual", video: "absent-honestly" });
      await context.close();
    }
    fs.writeFileSync(path.join(outputDir, "report.json"), JSON.stringify(report, null, 2) + "\n", { mode: 0o644 });
    console.log("PROJECT_LIBRARY_BROWSER_OK profiles=4 copy=enter-space-fallback download=pass overflow=0 schema=factual video=absent-honestly private_markers=0");
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(`PROJECT_LIBRARY_BROWSER_FAILED ${error.stack || error.message}`);
  process.exit(1);
});
