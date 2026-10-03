const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const base = process.env.ACCEPTANCE_BASE_URL || "https://teachthecompany.com";
const suffix = process.env.PUBLIC_EVIDENCE_SUFFIX || "live";
const outputDir = path.resolve("evidence/live");
fs.mkdirSync(outputDir, { recursive: true });

async function navigate(page, url) {
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    try {
      return await page.goto(url, { waitUntil: "networkidle" });
    } catch (error) {
      if (!String(error.message).includes("ERR_NETWORK_CHANGED") || attempt === 3) throw error;
      await page.waitForTimeout(400 * attempt);
    }
  }
}

async function open(page, route, expectedText) {
  const errors = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  const response = await navigate(page, base + route);
  if (!response || response.status() !== 200) {
    throw new Error(`${route} returned ${response && response.status()}`);
  }
  await page.getByText(expectedText, { exact: false }).first().waitFor();
  const geometry = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
  }));
  if (geometry.scroll > geometry.viewport + 1) {
    throw new Error(`${route} overflows ${geometry.scroll}/${geometry.viewport}`);
  }
  if (errors.length) throw new Error(`${route} browser errors: ${errors.join(" | ")}`);
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const report = { base, checked_at: new Date().toISOString(), profiles: [] };
  try {
    for (const profile of [
      { name: "desktop", width: 1440, height: 1000 },
      { name: "mobile", width: 390, height: 844 },
    ]) {
      const context = await browser.newContext({
        viewport: { width: profile.width, height: profile.height },
        userAgent: `TeachCompanyPublicAcceptance/${profile.name}/${report.checked_at}`,
      });
      const page = await context.newPage();

      await open(page, "/", "Your work has a method");
      if (await page.locator(".agent-card").count() !== 3) throw new Error("Homepage demo count is not three");
      const homeText = await page.locator("body").innerText();
      const normalizedHomeText = homeText.toLowerCase();
      if (!normalizedHomeText.includes("one private agent") || /\bron\b/i.test(homeText)) {
        throw new Error("Homepage product boundary is incorrect");
      }
      await page.locator("[data-chalk-board]").scrollIntoViewIfNeeded();
      await page.locator("[data-chalk-board].chalk-written").waitFor({ timeout: 9000 });
      await page.screenshot({ path: path.join(outputDir, `${suffix}-home-${profile.name}.png`), fullPage: true });

      await open(page, "/demos/", "See every lesson");
      if (await page.locator(".agent-card").count() !== 3) throw new Error("Demo gallery count is not three");
      await open(page, "/challenge/northstar-workshop-apprentice/", "Watch a workshop agent learn");
      if (await page.locator(".public-file").count() !== 7) throw new Error("Public demo file count is not seven");
      if (await page.locator(".public-question-grid article").count() !== 2) throw new Error("Public demo question count is not two");
      if (await page.locator(".public-artifact-grid article").count() !== 2) throw new Error("Public output count is not two");
      const publicText = await page.locator("body").innerText();
      if (publicText.includes("@example.invalid") || publicText.includes("Fictional teacher")) {
        throw new Error("Private demo identity leaked");
      }
      await page.screenshot({ path: path.join(outputDir, `${suffix}-demo-${profile.name}.png`), fullPage: true });

      await open(page, "/self-host/", "On your server");
      await open(page, "/request-access/", "Request one");
      const startResponse = await navigate(page, base + "/start/");
      if (!startResponse || startResponse.status() !== 200 || !page.url().endsWith("/request-access/")) {
        throw new Error("Hosted start route did not close to invitation requests");
      }

      report.profiles.push({ ...profile, demos: 3, files: 7, outputs: 2, signup: "invite-only" });
      await context.close();
    }
    fs.writeFileSync(path.join(outputDir, `${suffix}-report.json`), JSON.stringify(report, null, 2) + "\n", { mode: 0o644 });
    console.log(`PUBLIC_BROWSER_OK base=${base} profiles=2 demos=3 signup=invite-only overflow=0`);
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error.stack || error.message);
  process.exit(1);
});
