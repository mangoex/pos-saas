(() => {
  "use strict";

  const mobileViewport = window.matchMedia("(max-width: 860px)");
  let desktopStarted = false;

  function startDesktop() {
    if (mobileViewport.matches || desktopStarted) return;
    desktopStarted = true;

    // 1. Preserve compatibility with existing contract tests
    if (window.ScrollCraft && typeof window.ScrollCraft.mount === "function") {
      window.__sc = window.ScrollCraft.mount(document.body);
    }

    // 2. Splash Screen Controller (Counts 0 to 100 over exactly 2000ms)
    initSplashScreen();

    // 3. Masked Cards Engine (Windowing effect sharing background image across cards)
    initMaskedCards();

    // 4. Hero Parallax Continuous Video Scroll Engine (5 Aura Cards)
    initHeroParallaxScroll();

    // 5. Staggered Reveal Animations via IntersectionObserver
    initStaggeredReveal();

    // 6. Active Navbar Link Tracker
    initNavbarTracker();
  }

  /* --------------------------------------------------------------------------
     Splash Screen Controller
     -------------------------------------------------------------------------- */
  function initSplashScreen() {
    if (typeof document === "undefined" || typeof document.querySelector !== "function") return;
    const splash = document.querySelector("#splash-screen");
    const counterEl = document.querySelector("#splash-counter");
    if (!splash || !counterEl || !splash.classList) return;

    let current = 0;
    const duration = 2000;
    const totalSteps = 100;
    const intervalMs = duration / totalSteps;

    const timer = setInterval(() => {
      current += 1;
      counterEl.textContent = String(current);

      if (current >= 100) {
        clearInterval(timer);
        setTimeout(() => {
          if (splash.classList) splash.classList.add("is-exiting");
          setTimeout(() => {
            splash.style.display = "none";
          }, 700);
        }, 200);
      }
    }, intervalMs);
  }

  /* --------------------------------------------------------------------------
     Masked Cards Engine
     -------------------------------------------------------------------------- */
  function initMaskedCards() {
    if (typeof document === "undefined" || typeof document.querySelectorAll !== "function") return;
    if (typeof Image === "undefined") return;

    const sections = Array.from(document.querySelectorAll(".desktop-section[data-bg]"));
    if (sections.length === 0) return;

    sections.forEach((section) => {
      const bgUrl = section.dataset?.bg;
      const focalX = Number.parseFloat(section.dataset?.focal || "0.7");
      const cards = section.querySelectorAll ? Array.from(section.querySelectorAll(".masked-card")) : [];
      if (!bgUrl || cards.length === 0) return;

      const img = new Image();
      img.src = bgUrl;

      function updatePositions() {
        if (mobileViewport.matches) return;
        if (!section.getBoundingClientRect) return;
        const sRect = section.getBoundingClientRect();
        const sw = sRect.width;
        const sh = sRect.height;
        if (sw <= 0 || sh <= 0) return;

        const naturalWidth = img.naturalWidth || 1920;
        const naturalHeight = img.naturalHeight || 1080;
        const renderWidth = naturalWidth * (sh / naturalHeight);
        const overflow = renderWidth > sw ? renderWidth - sw : 0;
        const focalOffset = overflow * focalX;

        cards.forEach((card) => {
          if (!card.getBoundingClientRect) return;
          const cRect = card.getBoundingClientRect();
          const x = cRect.left - sRect.left;
          const y = cRect.top - sRect.top;

          const slides = card.querySelectorAll ? Array.from(card.querySelectorAll(".masked-card__slide")) : [];
          if (slides.length > 0) {
            slides.forEach((slide) => {
              if (!slide.style) return;
              slide.style.backgroundSize = `auto ${Math.round(sh)}px`;
              slide.style.backgroundPosition = `-${Math.round(x + focalOffset)}px -${Math.round(y)}px`;
            });
          } else if (card.style) {
            card.style.backgroundImage = `url("${bgUrl}")`;
            card.style.backgroundSize = `auto ${Math.round(sh)}px`;
            card.style.backgroundPosition = `-${Math.round(x + focalOffset)}px -${Math.round(y)}px`;
            card.style.backgroundRepeat = "no-repeat";
          }
        });
      }

      if (img.complete) {
        updatePositions();
      } else if (img.addEventListener) {
        img.addEventListener("load", updatePositions);
      }

      if (window.addEventListener) {
        window.addEventListener("resize", updatePositions, { passive: true });
      }
    });
  }

  /* --------------------------------------------------------------------------
     Hero Parallax Continuous Video Scroll Engine (5 Aura Cards)
     -------------------------------------------------------------------------- */
  function initHeroParallaxScroll() {
    if (typeof document === "undefined" || typeof document.querySelector !== "function") return;
    const track = document.querySelector("#section-1.hero-parallax-track");
    const viewport = document.querySelector("#heroSlidesViewport") || document.querySelector("#heroCardStage");
    if (!track || !viewport) return;

    const slides = Array.from(viewport.querySelectorAll ? viewport.querySelectorAll(".hero-full-slide, .aura-slide") : []);
    if (slides.length === 0) return;

    const scrubberSteps = Array.from(document.querySelectorAll ? document.querySelectorAll(".hero-timeline-scrubber .scrubber-step") : []);
    const progressFill = document.querySelector("#scrubberProgressFill");
    const scrollHint = document.querySelector("#heroScrollHint");

    let rafId = null;
    let targetProgress = 0;
    let currentProgress = 0;
    const totalTransitions = Math.max(1, slides.length - 1);

    function getScrollProgress() {
      if (typeof window === "undefined" || !track.getBoundingClientRect) return 0;
      const rect = track.getBoundingClientRect();
      const scrollHeight = track.offsetHeight - window.innerHeight;
      if (scrollHeight <= 0) return 0;
      const scrolled = -rect.top;
      return Math.max(0, Math.min(1, scrolled / scrollHeight));
    }

    function renderProgress(p) {
      const virtualIndex = p * totalTransitions; // 0.0 to 4.0

      // Update Scrubber Progress Fill
      if (progressFill && progressFill.style) {
        progressFill.style.height = `${(p * 100).toFixed(1)}%`;
      }

      // Hide scroll hint once user starts scrolling
      if (scrollHint && scrollHint.style) {
        scrollHint.style.opacity = p > 0.04 ? "0" : "1";
        scrollHint.style.pointerEvents = p > 0.04 ? "none" : "auto";
      }

      // Update Full-Screen Slides with smooth Parallax + Video Scrubber Crossfade
      slides.forEach((slide, idx) => {
        if (!slide.style) return;
        const diff = virtualIndex - idx; // diff < 0: upcoming slide; diff > 0: past slide
        const absDiff = Math.abs(diff);

        if (absDiff < 1.15) {
          const clampedAbs = Math.min(1, absDiff);
          const opacity = Math.max(0, 1 - clampedAbs * 1.3);
          const translateY = -diff * 60; // Parallax vertical drift
          const scale = 1 - clampedAbs * 0.035; // Subtle cinematic scale

          slide.style.opacity = opacity.toFixed(3);
          slide.style.transform = `translate3d(0, ${translateY.toFixed(1)}px, 0) scale(${scale.toFixed(3)})`;
          slide.style.pointerEvents = absDiff < 0.4 ? "auto" : "none";
          slide.style.visibility = "visible";
          slide.style.zIndex = String(Math.round((1 - clampedAbs) * 10) + 1);

          if (slide.classList) {
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
          if (slide.classList) slide.classList.remove("is-active");
        }
      });

      // Update Step Indicators
      const activeStepIndex = Math.round(virtualIndex);
      scrubberSteps.forEach((btn, sIdx) => {
        if (!btn.classList) return;
        if (sIdx === activeStepIndex) {
          btn.classList.add("is-active");
        } else {
          btn.classList.remove("is-active");
        }
      });
    }

    function onScroll() {
      targetProgress = getScrollProgress();
      if (!rafId && typeof window !== "undefined" && window.requestAnimationFrame) {
        rafId = window.requestAnimationFrame(updateLoop);
      }
    }

    function updateLoop() {
      // Lerp for buttery video scrub feel
      currentProgress += (targetProgress - currentProgress) * 0.2;
      if (Math.abs(targetProgress - currentProgress) < 0.001) {
        currentProgress = targetProgress;
        renderProgress(currentProgress);
        rafId = null;
      } else {
        renderProgress(currentProgress);
        rafId = window.requestAnimationFrame(updateLoop);
      }
    }

    // Click handler for scrubber steps
    scrubberSteps.forEach((btn) => {
      if (btn.addEventListener) {
        btn.addEventListener("click", () => {
          const step = Number.parseInt(btn.dataset?.step || "0", 10);
          if (typeof window === "undefined" || !track.getBoundingClientRect) return;
          const rect = track.getBoundingClientRect();
          const trackTop = (window.scrollY || 0) + rect.top;
          const scrollHeight = track.offsetHeight - window.innerHeight;
          const targetY = trackTop + (step / totalTransitions) * scrollHeight;
          if (window.scrollTo) {
            window.scrollTo({ top: targetY, behavior: "smooth" });
          }
        });
      }
    });

    if (typeof window !== "undefined" && window.addEventListener) {
      window.addEventListener("scroll", onScroll, { passive: true });
      window.addEventListener("resize", onScroll, { passive: true });
    }

    // Initial render
    currentProgress = getScrollProgress();
    targetProgress = currentProgress;
    renderProgress(currentProgress);
  }

  /* --------------------------------------------------------------------------
     Staggered Reveal Animations
     -------------------------------------------------------------------------- */
  function initStaggeredReveal() {
    if (typeof document === "undefined" || typeof document.querySelectorAll !== "function") return;
    const sections = Array.from(document.querySelectorAll(".desktop-section"));
    if (sections.length === 0) return;

    if (typeof window === "undefined" || !("IntersectionObserver" in window)) {
      sections.forEach((s) => s.classList?.add("is-revealed"));
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting && entry.target.classList) {
            entry.target.classList.add("is-revealed");
          }
        });
      },
      { threshold: 0.15 }
    );

    sections.forEach((section) => observer.observe(section));
  }

  /* --------------------------------------------------------------------------
     Active Navbar Link Tracker
     -------------------------------------------------------------------------- */
  function initNavbarTracker() {
    if (typeof document === "undefined" || typeof document.querySelectorAll !== "function") return;
    const links = Array.from(document.querySelectorAll(".desktop-navbar__link[href^='#']"));
    if (links.length === 0) return;

    const sections = links.map((l) => (l.getAttribute ? document.querySelector(l.getAttribute("href") || "") : null)).filter(Boolean);
    if (sections.length === 0) return;

    if (window.addEventListener) {
      window.addEventListener(
        "scroll",
        () => {
          const scrollY = window.scrollY || 0;
          const innerH = window.innerHeight || 800;

          sections.forEach((section, idx) => {
            const top = section.offsetTop || 0;
            const height = section.offsetHeight || 0;
            if (scrollY >= top - innerH / 3 && scrollY < top + height - innerH / 3) {
              links.forEach((l) => l.classList?.remove("active"));
              if (links[idx] && links[idx].classList) links[idx].classList.add("active");
            }
          });
        },
        { passive: true }
      );
    }
  }

  if (mobileViewport && mobileViewport.addEventListener) {
    mobileViewport.addEventListener("change", startDesktop);
  }
  startDesktop();
})();
