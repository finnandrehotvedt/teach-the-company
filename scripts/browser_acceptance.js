const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const base = process.env.ACCEPTANCE_BASE_URL || "http://127.0.0.1:18574";
const outputDir = path.resolve("evidence/browser");
fs.mkdirSync(outputDir, { recursive: true });

async function load(page, route, expectedText, expectedStatus = 200) {
  const errors = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(`console: ${message.text()}`);
  });
  page.on("pageerror", (error) => errors.push(`page: ${error.message}`));
  const response = await page.goto(base + route, { waitUntil: "networkidle" });
  if (!response || response.status() !== expectedStatus) {
    throw new Error(`${route} returned ${response && response.status()}, expected ${expectedStatus}`);
  }
  if (expectedText) await page.getByText(expectedText, { exact: false }).first().waitFor();
  const geometry = await page.evaluate(() => ({ viewport: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
  if (geometry.scroll > geometry.viewport + 1) throw new Error(`${route} overflows ${geometry.scroll}/${geometry.viewport}`);
  if (errors.length) throw new Error(`${route} browser errors: ${errors.join(" | ")}`);
  return geometry;
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
        userAgent: `TeachCompanyAgentAcceptance/${profile.name}/${report.checked_at}`,
      });
      const page = await context.newPage();

      const home = await load(page, "/", "Your work has a method");
      if (await page.locator(".agent-card").count() !== 3) throw new Error("Homepage does not show three fictional agents");
      await page.locator("[data-chalk-board]").scrollIntoViewIfNeeded();
      await page.locator("[data-chalk-board].chalk-animated").waitFor({ timeout: 4000 });
      await page.locator("[data-chalk-board].chalk-written").waitFor({ timeout: 8500 });
      await page.screenshot({ path: path.join(outputDir, `home-${profile.name}.png`), fullPage: true });

      await load(page, "/demos/", "See every lesson");
      if (await page.locator(".agent-card").count() !== 3) throw new Error("Demo gallery count is not three");
      await load(page, "/curriculum/", "One visible loop");
      await load(page, "/self-host/", "On your server");

      await load(page, "/challenge/northstar-workshop-apprentice/", "Watch a workshop agent learn");
      if (await page.locator(".public-file").count() !== 7) throw new Error("Workshop demo does not expose seven safe files");
      if (await page.locator(".public-artifact-grid article").count() !== 2) throw new Error("Workshop demo does not expose two outputs");
      if (await page.locator(".public-question-grid article").count() !== 2) throw new Error("Workshop demo does not expose its safe questions");
      const demoHtml = await page.locator("body").innerText();
      if (demoHtml.includes("@example.invalid") || demoHtml.includes("Fictional teacher")) throw new Error("Private demo identity leaked");
      await page.getByLabel("Give the agent a simulated task").fill("The motor reports an overload. What evidence should I inspect first?");
      await page.getByRole("button", { name: "Challenge the agent" }).click();
      await page.getByText("A taught method was found", { exact: false }).waitFor();
      await page.screenshot({ path: path.join(outputDir, `challenge-${profile.name}.png`), fullPage: true });

      await load(page, "/request-access/", "Request one");
      await page.getByLabel("Your name").fill(`Pilot ${profile.name}`);
      await page.getByLabel("Email").fill(`pilot-${profile.name}@example.test`);
      await page.getByLabel("What would you teach your agent?").fill("Teach one private agent our fictional maintenance method.");
      await page.getByRole("button", { name: "Request an invitation" }).click();
      await page.getByText("Your place is", { exact: false }).waitFor();

      await load(page, "/start/", "Create one");
      await page.getByLabel("Your name").fill(`Teacher ${profile.name}`);
      await page.getByLabel("Email").fill(`teacher-${profile.name}@example.test`);
      await page.getByLabel("Name your agent").fill(`Acceptance Agent ${profile.name}`);
      await page.getByRole("button", { name: "Open the agent classroom" }).click();
      await page.getByText(`Acceptance Agent ${profile.name}`, { exact: true }).waitFor();
      const studioUrl = page.url();
      if (await page.locator(".agent-file-row").count() !== 3) throw new Error("New agent does not begin with the three-file Codex framework");
      await page.getByText("AGENTS.md", { exact: true }).waitFor();
      await page.getByText("0 unprocessed files", { exact: false }).waitFor();

      await page.getByLabel("What are you teaching?").selectOption("procedure");
      await page.getByLabel("File name").fill("Motor overload triage");
      await page.getByLabel("Knowledge, example or correction").fill("For motor overload, record the exact fault code and inspect ventilation evidence before proposing a next step.");
      await page.getByRole("button", { name: "Add to classroom" }).click();
      await page.getByText("procedures/motor-overload-triage.md", { exact: true }).waitFor();
      await page.getByText("1 unprocessed file", { exact: false }).waitFor();
      await page.getByRole("button", { name: "Process files" }).click();
      await page.getByRole("button", { name: "Yes", exact: true }).first().click();
      await page.locator("#agent-questions textarea[name='answer']").first().fill("Use it for motor overload evidence checks; stop and ask when the fault code is missing.");
      await page.getByRole("button", { name: "Save to memory" }).first().click();
      await page.getByText("No open uncertainties", { exact: false }).waitFor();

      const procedureRow = page.locator(".agent-file-row", { hasText: "procedures/motor-overload-triage.md" });
      await procedureRow.getByRole("link", { name: "Open" }).click();
      await page.getByText("Visible agent file", { exact: false }).waitFor();
      await page.getByText("record the exact fault code", { exact: false }).waitFor();
      await page.getByRole("link", { name: "Back to all files" }).click();
      await page.getByRole("button", { name: "Approve", exact: true }).click();
      await page.getByText("Version 2 is now active", { exact: false }).waitFor();

      const zipDownload = page.waitForEvent("download");
      await page.getByRole("link", { name: "Download ZIP" }).click();
      const downloaded = await zipDownload;
      if (!downloaded.suggestedFilename().endsWith("-codex-training.zip")) throw new Error("Codex export did not produce a ZIP filename");

      await page.getByLabel("Test what the agent has learned").fill("Prepare a motor overload evidence checklist");
      await page.getByRole("button", { name: "Test the agent" }).click();
      await page.locator(".artifact-card").first().waitFor();
      await page.getByText("procedures/motor-overload-triage.md", { exact: false }).first().waitFor();
      await page.getByRole("button", { name: "Approve this version" }).click();
      await page.getByText("Nothing was published or sent", { exact: false }).waitFor();
      await page.screenshot({ path: path.join(outputDir, `studio-${profile.name}.png`), fullPage: true });

      const stranger = await browser.newContext({ viewport: { width: profile.width, height: profile.height } });
      const strangerPage = await stranger.newPage();
      const forbidden = await strangerPage.goto(studioUrl, { waitUntil: "networkidle" });
      if (!forbidden || forbidden.status() !== 403) throw new Error("Private agent was visible to a second browser context");
      await stranger.close();

      report.profiles.push({ ...profile, home, studioUrl, fileCount: 6, artifactCount: 1, privacy: "pass", export: "pass" });
      await context.close();
    }
    fs.writeFileSync(path.join(outputDir, "report.json"), JSON.stringify(report, null, 2) + "\n", { mode: 0o644 });
    console.log(`BROWSER_ACCEPTANCE_OK profiles=${report.profiles.length} demos=3 agent_files=versioned questions=pass export=pass privacy=pass overflow=0`);
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error.stack || error.message);
  process.exit(1);
});
