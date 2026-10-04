(() => {
  const chalkBoard = document.querySelector("[data-chalk-board]");
  if (chalkBoard) {
    const motionButton = document.querySelector("[data-chalk-motion]");
    const writing = chalkBoard.querySelector(".chalk-writing");
    const firstLine = chalkBoard.querySelector(".chalk-script-one");
    const secondLine = chalkBoard.querySelector(".chalk-script-two");
    const finalMark = chalkBoard.querySelector(".chalk-answer");
    let completionTimer;
    let startDelayTimer;
    let started = false;

    const setMotionButton = (state) => {
      if (!motionButton) return;
      motionButton.hidden = false;
      motionButton.disabled = state === "writing";
      motionButton.textContent = state === "writing"
        ? "Writing…"
        : "Replay chalk writing ↻";
    };

    const syncChalkPath = () => {
      if (!writing || !firstLine || !secondLine) return;
      const firstTravel = Math.max(0, firstLine.getBoundingClientRect().width - 19);
      const secondTravel = Math.max(0, secondLine.getBoundingClientRect().width - 19);
      const lineGap = secondLine.offsetTop - firstLine.offsetTop;
      chalkBoard.style.setProperty("--chalk-line-one-x", `${firstTravel}px`);
      chalkBoard.style.setProperty("--chalk-line-two-x", `${secondTravel}px`);
      chalkBoard.style.setProperty("--chalk-line-gap", `${lineGap}px`);
    };

    const markWritten = () => {
      window.clearTimeout(completionTimer);
      window.clearTimeout(startDelayTimer);
      chalkBoard.classList.remove("chalk-animated");
      chalkBoard.classList.add("chalk-written");
      setMotionButton("finished");
    };

    const startWriting = () => {
      if (started) return;
      started = true;
      syncChalkPath();
      const begin = () => {
        syncChalkPath();
        setMotionButton("writing");
        chalkBoard.classList.add("chalk-animated");
        if (finalMark) finalMark.addEventListener("animationend", markWritten, { once: true });
        completionTimer = window.setTimeout(markWritten, 6800);
      };
      const desktopDelay = window.matchMedia("(min-width: 981px)").matches ? 650 : 0;
      startDelayTimer = window.setTimeout(begin, desktopDelay);
    };

    syncChalkPath();
    if (window.ResizeObserver) new ResizeObserver(syncChalkPath).observe(writing || chalkBoard);
    window.addEventListener("resize", syncChalkPath, { passive: true });

    if (window.IntersectionObserver) {
      const observer = new IntersectionObserver((entries) => {
        if (entries.some((entry) => entry.isIntersecting && entry.intersectionRatio >= 0.58)) {
          observer.disconnect();
          startWriting();
        }
      }, { threshold: [0.58] });
      observer.observe(chalkBoard);
    } else {
      startWriting();
    }

    if (motionButton) {
      motionButton.addEventListener("click", () => {
        window.clearTimeout(completionTimer);
        window.clearTimeout(startDelayTimer);
        chalkBoard.classList.remove("chalk-written", "chalk-animated");
        started = false;
        void chalkBoard.offsetWidth;
        startWriting();
      });
    }
  }

  const workbook = document.querySelector("[data-counter='workbook-count']");
  const counter = document.getElementById("workbook-count");
  if (workbook && counter) {
    const update = () => { counter.textContent = `${workbook.value.length} / 3000`; };
    workbook.addEventListener("input", update);
    update();
  }

  document.querySelectorAll("[data-share-url]").forEach((button) => {
    button.addEventListener("click", async () => {
      const share = { title: button.dataset.shareTitle, url: button.dataset.shareUrl };
      try {
        if (navigator.share) {
          await navigator.share(share);
        } else {
          await navigator.clipboard.writeText(share.url);
          const original = button.innerHTML;
          button.textContent = "Agent link copied ✓";
          window.setTimeout(() => { button.innerHTML = original; }, 1800);
        }
      } catch (error) {
        if (error.name !== "AbortError") {
          window.location.href = `mailto:?subject=${encodeURIComponent(share.title)}&body=${encodeURIComponent(share.url)}`;
        }
      }
    });
  });

  document.querySelectorAll(".upload-button input[type='file']").forEach((input) => {
    input.addEventListener("change", () => {
      const name = input.closest(".upload-field")?.querySelector("[data-upload-name]");
      if (name && input.files.length) name.textContent = input.files[0].name;
    });
  });

  document.querySelectorAll("[data-agent-process]").forEach((form) => {
    form.addEventListener("submit", () => {
      const button = form.querySelector("button[type='submit']");
      const label = form.querySelector("[data-process-label]");
      const wait = form.querySelector("[data-process-wait]");
      form.setAttribute("aria-busy", "true");
      if (button) button.disabled = true;
      if (label) label.textContent = "Agent is reading…";
      if (wait) wait.hidden = false;
    });
  });

  document.querySelectorAll("[data-copy-target]").forEach((button) => {
    button.addEventListener("click", async () => {
      const target = document.getElementById(button.dataset.copyTarget);
      if (!target) return;
      const status = button.getAttribute("aria-describedby")
        ? document.getElementById(button.getAttribute("aria-describedby"))
        : null;
      try {
        await navigator.clipboard.writeText(target.textContent);
        const original = button.textContent;
        button.textContent = "Copied ✓";
        if (status) status.textContent = "Prompt copied to the clipboard.";
        window.setTimeout(() => {
          button.textContent = original;
          if (status) status.textContent = "";
        }, 1800);
      } catch (_) {
        const selection = window.getSelection();
        const range = document.createRange();
        range.selectNodeContents(target);
        selection.removeAllRanges();
        selection.addRange(range);
        if (status) status.textContent = "Clipboard access was unavailable. The prompt is selected for manual copy.";
      }
    });
  });
})();
