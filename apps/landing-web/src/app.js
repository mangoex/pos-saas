(function () {
  "use strict";

  const mobileViewport =
    typeof window !== "undefined" && typeof window.matchMedia === "function"
      ? window.matchMedia("(max-width: 860px)")
      : null;

  function isMobile() {
    return Boolean(mobileViewport && mobileViewport.matches);
  }

  let desktopMounted = false;

  function startDesktop() {
    if (isMobile()) return;

    if (!desktopMounted && typeof window.ScrollCraft !== "undefined" && typeof window.ScrollCraft.mount === "function") {
      desktopMounted = true;
      window.ScrollCraft.mount();
    }

    initHeroParallaxScroll();
    initNavbarTracker();
  }

  /* --------------------------------------------------------------------------
     Hero Parallax Continuous Video Scroll Engine (5 Aura Slides)
     -------------------------------------------------------------------------- */
  let heroParallaxInitialized = false;

  function initHeroParallaxScroll() {
    if (heroParallaxInitialized) return;
    if (typeof document === "undefined" || typeof document.querySelector !== "function") return;
    const track = document.querySelector("#section-1.hero-parallax-track");
    const viewport = document.querySelector("#heroSlidesViewport");
    if (!track || !viewport || typeof viewport.querySelectorAll !== "function") return;

    const slides = Array.from(viewport.querySelectorAll(".hero-full-slide"));
    if (slides.length === 0) return;

    heroParallaxInitialized = true;

    const scrubberSteps = typeof document.querySelectorAll === "function"
      ? Array.from(document.querySelectorAll(".hero-timeline-scrubber .scrubber-step"))
      : [];
    const progressFill = document.querySelector("#scrubberProgressFill");
    const scrollHint = document.querySelector("#heroScrollHint");
    const navbar = document.querySelector(".desktop-navbar");

    let rafId = null;
    let targetProgress = 0;
    let currentProgress = 0;
    const totalTransitions = Math.max(1, slides.length - 1);

    function getScrollProgress() {
      if (typeof window === "undefined" || !track.getBoundingClientRect) return 0;
      const rect = track.getBoundingClientRect();
      const scrollHeight = (track.offsetHeight || 0) - (window.innerHeight || 800);
      if (scrollHeight <= 0) return 0;
      const scrolled = -rect.top;
      return Math.max(0, Math.min(1, scrolled / scrollHeight));
    }

    function renderProgress(p) {
      const virtualIndex = p * totalTransitions; // 0.0 to 4.0

      if (progressFill && progressFill.style) {
        progressFill.style.height = `${(p * 100).toFixed(1)}%`;
      }

      if (scrollHint && scrollHint.style) {
        scrollHint.style.opacity = p > 0.04 ? "0" : "1";
        scrollHint.style.pointerEvents = p > 0.04 ? "none" : "auto";
      }

      // Parallax update on full-screen slides
      slides.forEach((slide, idx) => {
        if (!slide.style) return;
        const diff = virtualIndex - idx;
        const absDiff = Math.abs(diff);

        if (absDiff < 1.15) {
          const clampedAbs = Math.min(1, absDiff);
          const opacity = Math.max(0, 1 - clampedAbs * 1.3);
          const translateY = -diff * 60;
          const scale = 1 - clampedAbs * 0.035;

          slide.style.opacity = opacity.toFixed(3);
          slide.style.transform = `translate3d(0, ${translateY.toFixed(1)}px, 0) scale(${scale.toFixed(3)})`;
          slide.style.pointerEvents = absDiff < 0.4 ? "auto" : "none";
          slide.style.visibility = "visible";
          slide.style.zIndex = String(Math.round((1 - clampedAbs) * 10) + 1);

          if (slide.classList && typeof slide.classList.add === "function") {
            if (absDiff < 0.5) {
              slide.classList.add("is-active");
            } else {
              slide.classList.remove("is-active");
            }
          }
        } else {
          slide.style.opacity = "0";
          slide.style.pointerEvents = "none";
          slide.style.visibility = "hidden";
          if (slide.classList && typeof slide.classList.remove === "function") {
            slide.classList.remove("is-active");
          }
        }
      });

      // Update Step Indicators
      const activeStepIndex = Math.round(virtualIndex);
      scrubberSteps.forEach((btn, sIdx) => {
        if (!btn.classList || typeof btn.classList.add !== "function") return;
        if (sIdx === activeStepIndex) {
          btn.classList.add("is-active");
        } else {
          btn.classList.remove("is-active");
        }
      });

      // Update Navbar Theme based on active slide
      if (navbar && typeof navbar.setAttribute === "function") {
        const activeSlide = slides[activeStepIndex];
        const theme = activeSlide && activeSlide.dataset ? activeSlide.dataset.theme : "light";
        navbar.setAttribute("data-theme", theme || "light");
      }
    }

    function onScroll() {
      targetProgress = getScrollProgress();
      if (!rafId && typeof window !== "undefined" && typeof window.requestAnimationFrame === "function") {
        rafId = window.requestAnimationFrame(updateLoop);
      }
    }

    function updateLoop() {
      currentProgress += (targetProgress - currentProgress) * 0.22;
      if (Math.abs(targetProgress - currentProgress) < 0.001) {
        currentProgress = targetProgress;
        renderProgress(currentProgress);
        rafId = null;
      } else {
        renderProgress(currentProgress);
        if (typeof window !== "undefined" && typeof window.requestAnimationFrame === "function") {
          rafId = window.requestAnimationFrame(updateLoop);
        }
      }
    }

    // Click handler for timeline scrubber buttons
    scrubberSteps.forEach((btn) => {
      if (typeof btn.addEventListener === "function") {
        btn.addEventListener("click", () => {
          const step = Number.parseInt((btn.dataset && btn.dataset.step) || "0", 10);
          if (typeof window === "undefined" || !track.getBoundingClientRect) return;
          const rect = track.getBoundingClientRect();
          const trackTop = (window.scrollY || 0) + rect.top;
          const scrollHeight = (track.offsetHeight || 0) - (window.innerHeight || 800);
          const targetY = trackTop + (step / totalTransitions) * scrollHeight;
          if (typeof window.scrollTo === "function") {
            window.scrollTo({ top: targetY, behavior: "smooth" });
          }
        });
      }
    });

    if (typeof window !== "undefined" && typeof window.addEventListener === "function") {
      window.addEventListener("scroll", onScroll, { passive: true });
      window.addEventListener("resize", onScroll, { passive: true });
    }

    currentProgress = getScrollProgress();
    targetProgress = currentProgress;
    renderProgress(currentProgress);
  }

  /* --------------------------------------------------------------------------
     Active Navbar Link Tracker
     -------------------------------------------------------------------------- */
  function initNavbarTracker() {
    if (typeof document === "undefined" || typeof document.querySelectorAll !== "function") return;
    const links = Array.from(document.querySelectorAll(".desktop-navbar__link[href^='#']"));
    if (links.length === 0) return;

    const sections = links.map((l) => (typeof l.getAttribute === "function" ? document.querySelector(l.getAttribute("href") || "") : null)).filter(Boolean);
    if (sections.length === 0) return;

    const navbar = document.querySelector(".desktop-navbar");

    if (typeof window !== "undefined" && typeof window.addEventListener === "function") {
      window.addEventListener(
        "scroll",
        () => {
          const scrollY = window.scrollY || 0;
          const innerH = window.innerHeight || 800;

          sections.forEach((section, idx) => {
            const top = section.offsetTop || 0;
            const height = section.offsetHeight || 0;
            if (scrollY >= top - innerH / 3 && scrollY < top + height - innerH / 3) {
              links.forEach((l) => {
                if (l.classList && typeof l.classList.remove === "function") l.classList.remove("active");
              });
              if (links[idx] && links[idx].classList && typeof links[idx].classList.add === "function") {
                links[idx].classList.add("active");
              }

              if (navbar && typeof navbar.setAttribute === "function") {
                if (section.id === "section-pedidos") {
                  navbar.setAttribute("data-theme", "dark");
                } else if (section.id === "section-pricing") {
                  navbar.setAttribute("data-theme", "light");
                }
              }
            }
          });
        },
        { passive: true }
      );
    }
  }

  if (mobileViewport && typeof mobileViewport.addEventListener === "function") {
    mobileViewport.addEventListener("change", startDesktop);
  }
  startDesktop();
})();
