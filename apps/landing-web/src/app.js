(() => {
  "use strict";

  const root = document.documentElement;
  const world = document.querySelector('[data-sc-mode="worldflight"]');
  const map = document.querySelector(".plate-map");
  const routeControls = Array.from(document.querySelectorAll("[data-route-progress]"));
  const mapButtons = Array.from(document.querySelectorAll("[data-route-index]"));
  const stories = Array.from(document.querySelectorAll("[data-story]"));
  const plates = new Map(
    Array.from(document.querySelectorAll("[data-plate]")).map((plate) => [plate.dataset.plate, plate])
  );
  const seeds = Array.from(document.querySelectorAll(".plate-map__seed"));
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const routeBreaks = [0, 0.255, 0.515, 0.775, 1.01];
  let activeIndex = -1;
  let raf = 0;

  function pageProgress() {
    const distance = Math.max(document.documentElement.scrollHeight - window.innerHeight, 1);
    return Math.min(1, Math.max(0, window.scrollY / distance));
  }

  function routeIndex(progress) {
    for (let index = routeBreaks.length - 2; index >= 0; index -= 1) {
      if (progress >= routeBreaks[index]) return index;
    }
    return 0;
  }

  function syncVisualState() {
    raf = 0;
    const progress = pageProgress();
    const index = routeIndex(progress);

    root.style.setProperty("--omnipos-progress", `${progress}turn`);
    root.style.setProperty("--omnipos-active", String(index));
    root.style.setProperty("--kiwi-progress", `${progress}turn`);
    root.style.setProperty("--kiwi-active", String(index));

    stories.forEach((story) => {
      const plate = plates.get(story.dataset.story);
      const opacity = Number.parseFloat(story.style.opacity || "0");
      const visible = Number.isFinite(opacity) && opacity > 0.5;
      story.toggleAttribute("inert", !visible);
      if (visible) story.removeAttribute("aria-hidden");
      else story.setAttribute("aria-hidden", "true");
      if (plate) plate.style.opacity = Number.isFinite(opacity) ? String(Math.min(1, opacity * 1.08)) : "0";
    });

    if (index !== activeIndex) {
      activeIndex = index;
      mapButtons.forEach((button, buttonIndex) => {
        button.setAttribute("aria-current", buttonIndex === index ? "true" : "false");
      });
    }

    seeds.forEach((seed, seedIndex) => {
      seed.classList.toggle("is-complete", seedIndex <= index);
    });

    const video = world?.querySelector("video");
    const time = video && Number.isFinite(video.currentTime) ? video.currentTime.toFixed(1) : "0.0";
    map.dataset.scVerifyState = `tramo:${index}|plato:${Math.round(progress * 20)}|video:${time}`;
  }

  function requestSync() {
    if (!raf) raf = window.requestAnimationFrame(syncVisualState);
  }

  function jumpTo(progress) {
    const distance = Math.max(document.documentElement.scrollHeight - window.innerHeight, 0);
    window.scrollTo({
      top: distance * progress,
      behavior: reducedMotion.matches ? "auto" : "smooth",
    });
  }

  routeControls.forEach((control) => {
    control.addEventListener("click", (event) => {
      const progress = Number.parseFloat(control.dataset.routeProgress || "0");
      if (!Number.isFinite(progress)) return;
      event.preventDefault();
      jumpTo(progress);
    });
  });

  window.addEventListener("scroll", requestSync, { passive: true });
  window.addEventListener("resize", requestSync);
  window.addEventListener("load", () => {
    window.dispatchEvent(new Event("resize"));
    requestSync();
  });

  if (document.fonts?.ready) {
    document.fonts.ready.then(() => {
      window.dispatchEvent(new Event("resize"));
      requestSync();
    });
  }

  if (window.ScrollCraft) {
    window.__sc = window.ScrollCraft.mount(document.body);
  }

  function followEngine() {
    syncVisualState();
    window.requestAnimationFrame(followEngine);
  }

  window.requestAnimationFrame(followEngine);
})();
