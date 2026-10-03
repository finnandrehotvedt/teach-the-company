const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const base = process.env.SECURITY_LAB_BASE_URL || "http://127.0.0.1:18575";
const outputDir = path.resolve("evidence/security-lab");
fs.mkdirSync(outputDir, { recursive: true });

async function open(page, route, expectedText) {
  const errors = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  const response = await page.goto(base + route, { waitUntil: "networkidle" });
  if (!response || response.status() !== 200) throw new Error(route + " returned " + (response && response.status()));
  await page.getByText(expectedText, { exact: false }).first().waitFor();
  const geometry = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
  }));
  if (geometry.scroll > geometry.viewport + 1) throw new Error(route + " overflows " + geometry.scroll + "/" + geometry.viewport);
  if (errors.length) throw new Error(route + " browser errors: " + errors.join(" | "));
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
        userAgent: "TeachSecurityLabAcceptance/" + profile.name,
        reducedMotion: profile.name === "mobile" ? "reduce" : "no-preference",
      });
      const page = await context.newPage();
      await open(page, "/", "Give the agent the task");

      await page.getByRole("button", { name: "Run policy check" }).click();
      await page.getByText("3 fields released", { exact: true }).waitFor();
      await page.getByText("The fictional invoice is overdue", { exact: false }).first().waitFor();
      await page.screenshot({ path: path.join(outputDir, "invoice-minimum-" + profile.name + ".png"), fullPage: true });

      await page.getByRole("button", { name: "Injection attempt", exact: false }).click();
      await page.getByRole("button", { name: "Run policy check" }).click();
      await page.getByText("0 fields released", { exact: true }).waitFor();
      await page.getByText("The request includes prohibited", { exact: false }).waitFor();

      await page.getByRole("button", { name: "Approval boundary", exact: false }).click();
      await page.getByRole("button", { name: "Run policy check" }).click();
      await page.getByRole("button", { name: "Approve one-time correspondence access" }).waitFor();
      await page.getByRole("button", { name: "Approve one-time correspondence access" }).click();
      await page.getByText("approved with owner approval", { exact: false }).waitFor();

      const share = page.locator("[data-share]");
      const sharePath = await share.getAttribute("href");
      if (!sharePath || !sharePath.startsWith("/receipt/")) throw new Error("Shareable receipt path missing");
      await open(page, sharePath, "Synthetic privacy receipt");
      const robots = await page.locator('meta[name="robots"]').getAttribute("content");
      if (robots !== "noindex, nofollow") throw new Error("Receipt must be noindex");
      if ((await context.cookies()).length !== 0) throw new Error("Security lab set a browser cookie");

      await open(page, "/limitations/", "What this lab does not prove");
      report.profiles.push({ ...profile, minimum: "approved", injection: "denied", approval: "explicit", receipt: "noindex", cookies: 0 });
      await context.close();
    }
    fs.writeFileSync(path.join(outputDir, "report.json"), JSON.stringify(report, null, 2) + "\n", { mode: 0o644 });
    console.log("SECURITY_LAB_BROWSER_OK profiles=2 minimum=approved injection=denied approval=explicit cookies=0 overflow=0");
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error.stack || error.message);
  process.exit(1);
});
