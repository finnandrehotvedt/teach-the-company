const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const publicBase = process.env.TTC_PREVIEW_URL || "http://127.0.0.1:18576";
const agentBase = process.env.TTC_AGENT_PREVIEW_URL || "http://agent.localhost:18576";
const outputDir = path.resolve("evidence/domain-suite");
fs.mkdirSync(outputDir, { recursive: true });

function overlaps(first, second) {
  return !(
    first.right <= second.left ||
    first.left >= second.right ||
    first.bottom <= second.top ||
    first.top >= second.bottom
  );
}

async function assertPage(page, url, expectedText) {
  const errors = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  const response = await page.goto(url, { waitUntil: "networkidle" });
  if (!response || response.status() !== 200) throw new Error(`${url} returned ${response && response.status()}`);
  await page.getByText(expectedText, { exact: false }).first().waitFor();
  const width = await page.evaluate(() => ({ viewport: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
  if (width.scroll > width.viewport + 1) throw new Error(`${url} overflows ${width.scroll}/${width.viewport}`);
  if (errors.length) throw new Error(`${url} browser errors: ${errors.join(" | ")}`);
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const report = { checked_at: new Date().toISOString(), publicBase, agentBase, profiles: [] };
  try {
    for (const profile of [
      { name: "desktop", width: 1440, height: 1000, reducedMotion: "no-preference" },
      { name: "mobile", width: 390, height: 844, reducedMotion: "reduce" },
    ]) {
      const context = await browser.newContext({
        viewport: { width: profile.width, height: profile.height },
        reducedMotion: profile.reducedMotion,
        userAgent: `TeachDomainSuiteAcceptance/${profile.name}`,
      });
      const page = await context.newPage();
      await assertPage(page, publicBase + "/", "Your work has a method");
      await page.getByText("Three clear rooms", { exact: true }).waitFor();
      await page.locator("[data-chalk-board]").scrollIntoViewIfNeeded();
      await page.waitForFunction(() => document.querySelector("[data-chalk-board]")?.classList.contains("chalk-animated"));

      if (profile.name === "desktop") {
        await page.waitForTimeout(1150);
        const writingState = await page.evaluate(() => ({
          visibleLetters: [...document.querySelectorAll(".chalk-letter")].filter((item) => Number.parseFloat(getComputedStyle(item).opacity) > 0.15).length,
          chalkOpacity: Number.parseFloat(getComputedStyle(document.querySelector(".chalk-stick")).opacity),
        }));
        if (writingState.visibleLetters < 1 || writingState.visibleLetters >= 16) throw new Error(`Desktop chalk did not reveal progressively: ${JSON.stringify(writingState)}`);
        if (writingState.chalkOpacity < 0.2) throw new Error(`Desktop chalk tip is not moving visibly: ${JSON.stringify(writingState)}`);
        await page.screenshot({ path: path.join(outputDir, "home-chalk-writing-desktop.png"), fullPage: false });
      }

      await page.waitForFunction(() => document.querySelector("[data-chalk-board]")?.classList.contains("chalk-written"), null, { timeout: 9000 });
      const board = await page.evaluate(() => {
        const rect = (selector) => {
          const value = document.querySelector(selector).getBoundingClientRect();
          return { left: value.left, right: value.right, top: value.top, bottom: value.bottom };
        };
        return {
          writing: rect(".chalk-writing"),
          blueCard: rect(".desk-card-two"),
          visibleLetters: [...document.querySelectorAll(".chalk-letter")].filter((item) => Number.parseFloat(getComputedStyle(item).opacity) > 0.95).length,
          replayVisible: getComputedStyle(document.querySelector("[data-chalk-motion]")).display !== "none",
        };
      });
      if (board.visibleLetters !== 16) throw new Error(`${profile.name} final chalk text is incomplete: ${JSON.stringify(board)}`);
      if (overlaps(board.writing, board.blueCard)) throw new Error(`${profile.name} blue card covers chalk writing: ${JSON.stringify(board)}`);
      if (profile.name === "desktop" && !board.replayVisible) throw new Error("Desktop replay control is not visible");

      await page.screenshot({ path: path.join(outputDir, `home-${profile.name}.png`), fullPage: true });
      await assertPage(page, publicBase + "/agent-memory/", "Agent memory should be visible");
      const canonical = await page.locator('link[rel="canonical"]').getAttribute("href");
      if (canonical !== publicBase + "/agent-memory/") throw new Error(`Unexpected canonical: ${canonical}`);
      await page.screenshot({ path: path.join(outputDir, `agent-memory-${profile.name}.png`), fullPage: true });

      await assertPage(page, agentBase + "/", "The private room where");
      const robots = await page.locator('meta[name="robots"]').getAttribute("content");
      if (robots !== "noindex, nofollow") throw new Error(`Agent host robots metadata is ${robots}`);
      await page.screenshot({ path: path.join(outputDir, `agent-home-${profile.name}.png`), fullPage: true });

      report.profiles.push({
        name: profile.name,
        viewport: `${profile.width}x${profile.height}`,
        overflow: 0,
        chalk: "progressive-and-clear",
        agentHost: "noindex",
      });
      await context.close();
    }
    fs.writeFileSync(path.join(outputDir, "report.json"), JSON.stringify(report, null, 2) + "\n", { mode: 0o644 });
    console.log("DOMAIN_SUITE_BROWSER_OK profiles=2 chalk=progressive card_overlap=0 overflow=0 agent_noindex=1");
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error.stack || error.message);
  process.exit(1);
});
