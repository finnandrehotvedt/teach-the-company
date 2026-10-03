const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const base = process.env.ACCEPTANCE_BASE_URL || "http://127.0.0.1:18574";
const suffix = process.env.CHALK_EVIDENCE_SUFFIX || "local";
const outputDir = path.resolve("evidence/chalk");
fs.mkdirSync(outputDir, { recursive: true });

function intersectionArea(a, b) {
  const width = Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left));
  const height = Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top));
  return width * height;
}

async function finalGeometry(page) {
  return page.locator("[data-chalk-board]").evaluate((board) => {
    const box = (selector) => {
      const rect = board.querySelector(selector).getBoundingClientRect();
      return { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom, width: rect.width, height: rect.height };
    };
    const boardRect = board.getBoundingClientRect();
    const style = getComputedStyle(board);
    return {
      board: { left: boardRect.left, right: boardRect.right, top: boardRect.top, bottom: boardRect.bottom },
      note: box(".chalk-hand-note"),
      first: box(".chalk-script-one"),
      second: box(".chalk-script-two"),
      flow: box(".chalk-flow"),
      answer: box(".chalk-answer"),
      stamp: (() => { const rect = document.querySelector(".teacher-stamp").getBoundingClientRect(); return { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom }; })(),
      cards: [...document.querySelectorAll(".desk-card")].map((card) => { const rect = card.getBoundingClientRect(); return { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom }; }),
      firstTravel: parseFloat(style.getPropertyValue("--chalk-line-one-x")),
      secondTravel: parseFloat(style.getPropertyValue("--chalk-line-two-x")),
      lineGap: parseFloat(style.getPropertyValue("--chalk-line-gap")),
      firstClip: getComputedStyle(board.querySelector(".chalk-script-one")).clipPath,
      secondClip: getComputedStyle(board.querySelector(".chalk-script-two")).clipPath,
      answerOpacity: parseFloat(getComputedStyle(board.querySelector(".chalk-answer")).opacity),
      flowOpacity: parseFloat(getComputedStyle(board.querySelector(".chalk-flow")).opacity),
    };
  });
}

function assertFinalGeometry(result, profile) {
  for (const name of ["note", "first", "second", "flow", "answer"]) {
    const item = result[name];
    if (item.left < result.board.left - 1 || item.right > result.board.right + 1 || item.top < result.board.top - 1 || item.bottom > result.board.bottom + 1) {
      throw new Error(`${profile}: ${name} escapes chalkboard`);
    }
  }
  for (const name of ["note", "first", "second", "answer"]) {
    if (intersectionArea(result[name], result.stamp) > 1) throw new Error(`${profile}: ${name} is covered by teacher stamp`);
    for (const card of result.cards) {
      if (intersectionArea(result[name], card) > 1) throw new Error(`${profile}: ${name} is covered by a desk card`);
    }
  }
  if (!Number.isFinite(result.firstTravel) || !Number.isFinite(result.secondTravel) || !Number.isFinite(result.lineGap)) {
    throw new Error(`${profile}: responsive chalk path variables are missing`);
  }
  if (Math.abs(result.firstTravel - (result.first.width - 19)) > 2 || Math.abs(result.secondTravel - (result.second.width - 19)) > 2) {
    throw new Error(`${profile}: chalk travel does not match rendered writing width`);
  }
  if (result.answerOpacity < 0.99 || result.flowOpacity < 0.99 || result.firstClip.includes("100%") || result.secondClip.includes("100%")) {
    throw new Error(`${profile}: finished handwriting is not fully visible`);
  }
}

async function secondLineCharacterProbe(board) {
  return board.evaluate((element) => {
    const writing = element.querySelector(".chalk-script-two").getBoundingClientRect();
    const chalk = element.querySelector(".chalk-stick").getBoundingClientRect();
    const characters = [...element.querySelectorAll(".chalk-script-two .chalk-letter")].map((letter, index) => {
      const rect = letter.getBoundingClientRect();
      return {
        index,
        character: letter.textContent,
        opacity: parseFloat(getComputedStyle(letter).opacity),
        left: rect.left,
        right: rect.right,
      };
    });
    const visibleCharacters = characters.filter((character) => character.opacity >= 0.98).length;
    const startedCharacters = characters.filter((character) => character.opacity > 0.05).length;
    const activeCharacter = characters.find((character) => character.opacity > 0.05 && character.opacity < 0.98) || null;
    return {
      mode: "characters",
      characterCount: characters.length,
      visibleCharacters,
      startedCharacters,
      activeCharacter,
      writingLeft: writing.left,
      writingRight: writing.right,
      chalkLeft: chalk.left,
      chalkRight: chalk.right,
      chalkOpacity: parseFloat(getComputedStyle(element.querySelector(".chalk-stick")).opacity),
    };
  });
}

function assertSecondLineCharacterProbe(probe, profile) {
  if (probe.characterCount !== 9 || probe.visibleCharacters < 3 || probe.visibleCharacters > 6 || probe.startedCharacters >= 9) {
    throw new Error(`${profile}: second line is not appearing character by character`);
  }
  if (!probe.activeCharacter || probe.chalkOpacity < 0.8 || probe.activeCharacter.right < probe.chalkLeft - 28 || probe.activeCharacter.left > probe.chalkRight + 28) {
    throw new Error(`${profile}: active second-line letter is not following the chalk tip`);
  }
}

async function waitForChalkTimeline(board, targetMilliseconds) {
  await board.evaluate(async (element, target) => {
    const chalk = element.querySelector(".chalk-stick");
    const deadline = performance.now() + 6000;
    while (performance.now() < deadline) {
      const animation = chalk.getAnimations().find((item) => item.animationName === "chalk-hand" || item.animationName === "chalk-hand-desktop");
      if (animation && Number(animation.currentTime) >= target) return;
      await new Promise((resolve) => requestAnimationFrame(resolve));
    }
    throw new Error(`chalk timeline did not reach ${target}ms`);
  }, targetMilliseconds);
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const report = { base, suffix, checked_at: new Date().toISOString(), profiles: [] };
  try {
    for (const profile of [
      { name: "desktop-compact", width: 1366, height: 768, desktop: true, characterWriting: true },
      { name: "desktop", width: 1440, height: 1000, desktop: true, characterWriting: true },
      { name: "desktop-wide", width: 1920, height: 1080, desktop: true, characterWriting: true },
      { name: "tablet", width: 768, height: 1024, desktop: false, characterWriting: true },
      { name: "mobile", width: 390, height: 844, desktop: false, characterWriting: true },
    ]) {
      const context = await browser.newContext({ viewport: { width: profile.width, height: profile.height }, reducedMotion: "no-preference" });
      const page = await context.newPage();
      const errors = [];
      page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
      page.on("pageerror", (error) => errors.push(error.message));
      const response = await page.goto(base + "/", { waitUntil: "networkidle" });
      if (!response || response.status() !== 200) throw new Error(`${profile.name}: homepage unavailable`);

      const board = page.locator("[data-chalk-board]");
      const initial = await board.evaluate((element) => ({
        animated: element.classList.contains("chalk-animated"),
        rect: element.getBoundingClientRect().toJSON(),
        viewportHeight: window.innerHeight,
      }));
      if (profile.name === "mobile") {
        await page.waitForTimeout(900);
        const premature = await board.evaluate((element) => element.classList.contains("chalk-animated"));
        if (initial.rect.top > initial.viewportHeight * 0.72 && premature) throw new Error(`${profile.name}: chalk started before board entered viewport`);
        await page.screenshot({ path: path.join(outputDir, `${suffix}-${profile.name}-before-scroll.png`) });
        await board.scrollIntoViewIfNeeded();
      }

      await page.locator("[data-chalk-board].chalk-animated").waitFor({ timeout: 4000 });
      const durations = await board.evaluate((element) => {
        const writingWindow = (selector) => {
          const line = element.querySelector(selector);
          const letters = [...line.querySelectorAll(".chalk-letter")];
          if (letters.length && getComputedStyle(letters[0]).animationName !== "none") {
            const starts = letters.map((letter) => parseFloat(getComputedStyle(letter).animationDelay));
            const ends = letters.map((letter) => parseFloat(getComputedStyle(letter).animationDelay) + parseFloat(getComputedStyle(letter).animationDuration));
            return Math.max(...ends) - Math.min(...starts);
          }
          return parseFloat(getComputedStyle(line).animationDuration);
        };
        return { first: writingWindow(".chalk-script-one"), second: writingWindow(".chalk-script-two") };
      });
      if (durations.first < 1.4 || durations.second < 1.6) throw new Error(`${profile.name}: handwriting is still too fast`);
      await page.waitForTimeout(1350);
      await page.locator(".classroom-scene").screenshot({ path: path.join(outputDir, `${suffix}-${profile.name}-writing.png`) });
      let secondLineProbe = null;
      if (profile.characterWriting) {
        await waitForChalkTimeline(board, 3200);
        secondLineProbe = await secondLineCharacterProbe(board);
        assertSecondLineCharacterProbe(secondLineProbe, profile.name);
        await page.locator(".classroom-scene").screenshot({ path: path.join(outputDir, `${suffix}-${profile.name}-second-line-writing.png`) });
      }
      await page.locator("[data-chalk-board].chalk-written").waitFor({ timeout: 8500 });
      await page.locator(".classroom-scene").screenshot({ path: path.join(outputDir, `${suffix}-${profile.name}-finished.png`) });

      const geometry = await finalGeometry(page);
      assertFinalGeometry(geometry, profile.name);
      if (errors.length) throw new Error(`${profile.name}: browser errors: ${errors.join(" | ")}`);
      report.profiles.push({ ...profile, initial, durations, secondLineProbe, geometry });
      await context.close();
    }

    const reduced = await browser.newContext({ viewport: { width: 768, height: 1024 }, reducedMotion: "reduce" });
    const reducedPage = await reduced.newPage();
    await reducedPage.goto(base + "/", { waitUntil: "networkidle" });
    const reducedBoard = reducedPage.locator("[data-chalk-board]");
    if (!await reducedPage.evaluate(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches)) throw new Error("reduced-motion: browser context does not report reduce");
    await reducedPage.locator("[data-chalk-board].chalk-animated").waitFor({ timeout: 4000 });
    await waitForChalkTimeline(reducedBoard, 3200);
    const reducedSecondLineProbe = await secondLineCharacterProbe(reducedBoard);
    assertSecondLineCharacterProbe(reducedSecondLineProbe, "reduced-motion");
    await reducedPage.locator(".classroom-scene").screenshot({ path: path.join(outputDir, `${suffix}-reduced-motion-writing.png`) });
    await reducedPage.locator("[data-chalk-board].chalk-written").waitFor({ timeout: 8500 });
    await reducedPage.locator(".classroom-scene").screenshot({ path: path.join(outputDir, `${suffix}-reduced-motion-finished.png`) });
    const reducedGeometry = await finalGeometry(reducedPage);
    assertFinalGeometry(reducedGeometry, "reduced-motion");
    report.reducedMotion = { matches: true, automatic: true, buttonClicks: 0, width: 768, height: 1024, secondLineProbe: reducedSecondLineProbe, geometry: reducedGeometry };
    await reduced.close();

    fs.writeFileSync(path.join(outputDir, `${suffix}-report.json`), JSON.stringify(report, null, 2) + "\n", { mode: 0o644 });
    console.log(`CHALK_VISUAL_OK base=${base} profiles=desktop-compact,desktop,desktop-wide,tablet,mobile reduced_motion_tablet=automatic`);
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(`CHALK_VISUAL_FAILED ${error.message}`);
  process.exit(1);
});
