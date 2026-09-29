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

    // 4. Staggered Reveal Animations via IntersectionObserver
    initStaggeredReveal();

    // 5. Active Navbar Link Tracker
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
          if (!card.getBoundingClientRect || !card.style) return;
          const cRect = card.getBoundingClientRect();
          const x = cRect.left - sRect.left;
          const y = cRect.top - sRect.top;

          card.style.backgroundImage = `url("${bgUrl}")`;
          card.style.backgroundSize = `auto ${Math.round(sh)}px`;
          card.style.backgroundPosition = `-${Math.round(x + focalOffset)}px -${Math.round(y)}px`;
          card.style.backgroundRepeat = "no-repeat";
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
