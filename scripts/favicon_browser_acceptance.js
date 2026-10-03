const { chromium } = require("playwright");

const baseUrl = (process.env.BASE_URL || "http://127.0.0.1:18576").replace(/\/$/, "");
const expectedGitlabUrl = process.env.EXPECTED_GITLAB_URL || "https://gitlab.finnandre.no/finnandrehotvedt/teach-the-company";
const expectedGithubUrl = process.env.EXPECTED_GITHUB_URL || "https://github.com/finnandrehotvedt/teach-the-company";

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext({
      viewport: { width: 390, height: 844 },
      userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1",
    });
    const page = await context.newPage();
    await page.goto(`${baseUrl}/`, { waitUntil: "networkidle" });

    const links = await page.locator('link[rel~="icon"]').evaluateAll((nodes) =>
      nodes.map((node) => ({ rel: node.rel, type: node.type, href: node.href }))
    );
    assert(links.length === 3, `Expected three declared favicon links, found ${links.length}`);
    const appleHref = await page.locator('link[rel="apple-touch-icon"]').getAttribute("href");
    const manifestHref = await page.locator('link[rel="manifest"]').getAttribute("href");
    assert(appleHref && /\/static\/img\/apple-touch-icon(?:\.[0-9a-f]+)?\.png$/.test(appleHref), "Apple touch icon is missing or invalid");
    assert(manifestHref === "/site.webmanifest", "Web manifest link is missing");

    const results = await page.evaluate(async () => {
      const read = async (path) => {
        const response = await fetch(path, { cache: "reload", redirect: "follow" });
        const bytes = new Uint8Array(await response.arrayBuffer());
        return {
          path,
          status: response.status,
          type: response.headers.get("content-type"),
          size: bytes.length,
          firstFour: Array.from(bytes.slice(0, 4)),
          textStart: new TextDecoder().decode(bytes.slice(0, 80)),
          finalUrl: response.url,
        };
      };
      return Promise.all([read("/favicon.ico"), read("/favicon.svg"), read("/apple-touch-icon.png")]);
    });

    const ico = results.find((item) => item.path === "/favicon.ico");
    const svg = results.find((item) => item.path === "/favicon.svg");
    const apple = results.find((item) => item.path === "/apple-touch-icon.png");
    assert(ico.status === 200 && ico.type === "image/x-icon", "ICO fallback did not resolve as image/x-icon");
    assert(ico.size === 4286, `Unexpected ICO size ${ico.size}`);
    assert(ico.firstFour.join(",") === "0,0,1,0", "ICO magic bytes are invalid");
    assert(svg.status === 200 && svg.type === "image/svg+xml", "SVG fallback did not resolve as image/svg+xml");
    assert(svg.size === 867, `Unexpected SVG size ${svg.size}`);
    assert(svg.textStart.includes("<svg"), "SVG payload is invalid");
    assert(apple.status === 200 && apple.type === "image/png", "Apple touch icon did not resolve as image/png");
    assert(apple.size === 8739, `Unexpected Apple touch icon size ${apple.size}`);
    assert(apple.firstFour.join(",") === "137,80,78,71", "Apple touch icon signature is invalid");
    const manifestResponse = await page.request.get(`${baseUrl}/site.webmanifest`);
    assert(manifestResponse.status() === 200, "Web manifest did not return HTTP 200");
    assert((manifestResponse.headers()["content-type"] || "").startsWith("application/manifest+json"), "Web manifest MIME is invalid");
    const manifest = await manifestResponse.json();
    assert(manifest.icons.length === 2, "Web manifest does not declare two mobile icons");
    assert(manifest.icons.map((icon) => icon.sizes).join(",") === "192x192,512x512", "Web manifest icon sizes are invalid");
    await page.goto(`${baseUrl}/self-host/`, { waitUntil: "networkidle" });
    const sourceHref = await page.getByRole("link", { name: "Clone from GitLab", exact: false }).getAttribute("href");
    const githubHref = await page.getByRole("link", { name: "Mirror on GitHub", exact: false }).getAttribute("href");
    const manualsHref = await page.getByRole("link", { name: "Public manuals", exact: false }).getAttribute("href");
    assert(sourceHref === expectedGitlabUrl, "Self-host GitLab source link is missing or incorrect");
    assert(githubHref === expectedGithubUrl, "Self-host GitHub source link is missing or incorrect");
    assert(manualsHref === "https://gitlab.finnandre.no/finnandrehotvedt/teach-the-company-public-manuals", "Public manuals link is missing or incorrect");
    const geometry = await page.evaluate(() => ({ width: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
    assert(geometry.scroll <= geometry.width + 1, `Self-host page overflows on mobile (${geometry.scroll}/${geometry.width})`);
    assert((await context.cookies()).length === 0, "Public favicon load created a cookie");

    console.log(JSON.stringify({ status: "MOBILE_ICON_BROWSER_OK", declared: links.length, apple: appleHref, manifest: manifest.icons, sourceHref, githubHref, manualsHref, fallbacks: results }));
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error.stack || error.message);
  process.exit(1);
});
