const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const sourcePath = process.argv[2];
const outputDir = process.argv[3];

if (!sourcePath || !outputDir) {
  throw new Error("Usage: node generate_mobile_icons.js SOURCE_SVG OUTPUT_DIR");
}

const targets = [
  ["apple-touch-icon.png", 180],
  ["icon-192.png", 192],
  ["icon-512.png", 512],
];

(async () => {
  const source = fs.readFileSync(sourcePath, "utf8");
  const dataUrl = `data:image/svg+xml;base64,${Buffer.from(source).toString("base64")}`;
  fs.mkdirSync(outputDir, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  try {
    for (const [filename, size] of targets) {
      const context = await browser.newContext({
        viewport: { width: size, height: size },
        deviceScaleFactor: 1,
      });
      const page = await context.newPage();
      await page.setContent(
        `<style>html,body{margin:0;width:100%;height:100%;background:transparent}img{display:block;width:100%;height:100%}</style><img alt="" src="${dataUrl}">`,
        { waitUntil: "load" }
      );
      await page.locator("img").evaluate((image) => image.decode());
      await page.screenshot({
        path: path.join(outputDir, filename),
        omitBackground: true,
      });
      await context.close();
    }
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error.stack || error.message);
  process.exit(1);
});
