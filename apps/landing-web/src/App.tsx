import React, { useState, useEffect, useRef } from 'react';

// ============================================================================
// DATA & ASSET CONSTANTS (mi menú.onl - Sistema Operativo para Restaurantes)
// ============================================================================
const HERO_IMAGE = '/landing-assets/assets/mimenu-hero-burger.png';
const SECTION2_IMAGE = '/landing-assets/assets/mimenu-features-grid.png';
const SECTION3_IMG1 = '/landing-assets/assets/feature-card-menu.png';
const SECTION3_IMG2 = '/landing-assets/assets/feature-card-pedidos.png';
const SECTION3_BG = '/landing-assets/assets/feature-card-crecimiento.png';

const featureBars = [
  '🍔 Menú Digital Interactivo con Código QR',
  '⚡ Punto de Venta POS & Caja en la Nube',
  '📟 Pantalla de Cocina KDS y Pedidos WhatsApp',
];

const services = [
  { name: 'Menú\nDigital QR', num: '01', active: true, desc: 'Catálogo interactivo con fotos HD y modificadores.' },
  { name: 'Punto de\nVenta POS', num: '02', active: false, desc: 'Cobros rápidos, tickets y caja diaria sin fricción.' },
  { name: 'Cocina\nKDS', num: '03', active: false, desc: 'Comandas en tiempo real con tiempos por estación.' },
  { name: 'Delivery\nWhatsApp', num: '04', active: false, desc: 'Toma pedidos directos sin comisiones abusivas.' },
];

// ============================================================================
// CORE TECHNICAL HOOKS
// ============================================================================

interface CardPosition {
  x: number;
  y: number;
  sw: number;
  sh: number;
}

/**
 * useMaskPositions
 * Tracks container and card elements to compute windowing offsets for masked backgrounds.
 */
function useMaskPositions(
  sectionRef: React.RefObject<HTMLElement | null>,
  cardRefs: React.MutableRefObject<(HTMLElement | null)[]>
) {
  const [positions, setPositions] = useState<CardPosition[]>([]);

  useEffect(() => {
    const section = sectionRef.current;
    if (!section) return;

    const update = () => {
      const sRect = section.getBoundingClientRect();
      const nextPositions = cardRefs.current.map((card) => {
        if (!card) return { x: 0, y: 0, sw: sRect.width, sh: sRect.height };
        const cRect = card.getBoundingClientRect();
        return {
          x: cRect.left - sRect.left,
          y: cRect.top - sRect.top,
          sw: sRect.width,
          sh: sRect.height,
        };
      });
      setPositions(nextPositions);
    };

    update();
    const observer = new ResizeObserver(update);
    observer.observe(section);
    window.addEventListener('resize', update, { passive: true });

    return () => {
      observer.disconnect();
      window.removeEventListener('resize', update);
    };
  }, [sectionRef, cardRefs]);

  return positions;
}

/**
 * useImageWidth
 * Loads background image to calculate the scaled width relative to section height.
 */
function useImageWidth(bgImage: string, sectionRef: React.RefObject<HTMLElement | null>) {
  const [renderWidth, setRenderWidth] = useState(0);

  useEffect(() => {
    const img = new Image();
    img.src = bgImage;

    const calc = () => {
      const section = sectionRef.current;
      if (!section) return;
      const sh = section.clientHeight || 800;
      const nw = img.naturalWidth || 1920;
      const nh = img.naturalHeight || 1080;
      setRenderWidth(nw * (sh / nh));
    };

    if (img.complete) {
      calc();
    } else {
      img.onload = calc;
    }

    window.addEventListener('resize', calc, { passive: true });
    return () => window.removeEventListener('resize', calc);
  }, [bgImage, sectionRef]);

  return renderWidth;
}

/**
 * useIsMobile
 * Breakpoint listener for 768px.
 */
function useIsMobile() {
  const [isMobile, setIsMobile] = useState(() => {
    if (typeof window === 'undefined') return false;
    return window.matchMedia('(max-width: 767px)').matches;
  });

  useEffect(() => {
    const media = window.matchMedia('(max-width: 767px)');
    const onChange = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    media.addEventListener('change', onChange);
    return () => media.removeEventListener('change', onChange);
  }, []);

  return isMobile;
}

/**
 * useStaggeredReveal
 * IntersectionObserver triggering staggered entrance transitions.
 */
function useStaggeredReveal(count: number, threshold = 0.15) {
  const containerRef = useRef<HTMLElement | null>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = containerRef.current;
    if (!el || typeof IntersectionObserver === 'undefined') {
      setVisible(true);
      return;
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { threshold }
    );

    observer.observe(el);
    return () => observer.disconnect();
  }, [threshold]);

  const getAnimStyle = (index: number): React.CSSProperties => ({
    opacity: visible ? 1 : 0,
    transform: visible ? 'translateY(0)' : 'translateY(24px)',
    transition: `opacity 0.6s cubic-bezier(0.16,1,0.3,1) ${index * 120}ms, transform 0.6s cubic-bezier(0.16,1,0.3,1) ${index * 120}ms`,
  });

  return { containerRef, getAnimStyle, visible };
}

// ============================================================================
// MASKED CARD COMPONENT
// ============================================================================
interface MaskedCardProps {
  bgImage: string;
  position?: CardPosition;
  imageWidth: number;
  focalX: number;
  className?: string;
  children: React.ReactNode;
  cardRef?: (el: HTMLElement | null) => void;
  style?: React.CSSProperties;
}

const MaskedCard: React.FC<MaskedCardProps> = ({
  bgImage,
  position,
  imageWidth,
  focalX,
  className = '',
  children,
  cardRef,
  style = {},
}) => {
  const sw = position?.sw || 0;
  const sh = position?.sh || 0;
  const x = position?.x || 0;
  const y = position?.y || 0;

  const overflow = imageWidth > sw ? imageWidth - sw : 0;
  const focalOffset = overflow * focalX;

  const maskStyle: React.CSSProperties = {
    backgroundImage: `url(${bgImage})`,
    backgroundSize: sh > 0 ? `auto ${sh}px` : 'cover',
    backgroundPosition: `-${Math.round(x + focalOffset)}px -${Math.round(y)}px`,
    backgroundRepeat: 'no-repeat',
    ...style,
  };

  return (
    <div ref={cardRef} className={`relative overflow-hidden ${className}`} style={maskStyle}>
      {children}
    </div>
  );
};

// ============================================================================
// SPLASH SCREEN
// ============================================================================
const SplashScreen: React.FC<{ onComplete: () => void }> = ({ onComplete }) => {
  const [count, setCount] = useState(0);
  const [exiting, setExiting] = useState(false);

  useEffect(() => {
    let current = 0;
    const interval = setInterval(() => {
      current += 1;
      setCount(current);
      if (current >= 100) {
        clearInterval(interval);
        setTimeout(() => {
          setExiting(true);
          setTimeout(() => {
            onComplete();
          }, 700);
        }, 200);
      }
    }, 20);

    return () => clearInterval(interval);
  }, [onComplete]);

  return (
    <div
      className={`fixed inset-0 z-[100] bg-[#070e14] text-white flex items-end justify-start p-6 md:p-10 transition-opacity duration-700 ease-[cubic-bezier(0.16,1,0.3,1)] ${
        exiting ? 'opacity-0 pointer-events-none' : 'opacity-100'
      }`}
    >
      <div className="flex flex-col gap-2">
        <span className="text-xs md:text-sm font-extrabold uppercase tracking-widest text-[#00d2ff]">
          INICIANDO MI MENÚ.ONL
        </span>
        <span className="text-7xl md:text-9xl font-bold tabular-nums leading-none tracking-tight">
          {count}
        </span>
      </div>
    </div>
  );
};

// ============================================================================
// NAVBAR COMPONENT
// ============================================================================
const Navbar: React.FC = () => {
  const [isMenuOpen, setIsMenuOpen] = useState(false);

  useEffect(() => {
    if (isMenuOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [isMenuOpen]);

  return (
    <header className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-4 md:px-6 py-2.5 md:py-3.5 bg-black/60 backdrop-blur-md border-b border-white/10 text-white">
      {/* Logo */}
      <div className="flex flex-col">
        <span className="text-xl md:text-2xl font-extrabold uppercase tracking-tight leading-none">
          mi menú<span className="text-[#fbbf24]">.onl</span>
        </span>
        <span className="text-[8px] md:text-[9px] font-semibold tracking-wider text-slate-400 uppercase mt-1 md:mt-1.5 leading-none">
          Sistema Operativo para Restaurantes
        </span>
      </div>

      {/* Desktop nav */}
      <div className="hidden md:flex items-center gap-4">
        <nav className="flex items-center gap-6 text-sm font-semibold text-slate-300">
          <a href="#section-1" className="hover:text-white transition-colors">Inicio</a>
          <a href="#section-2" className="hover:text-white transition-colors">Operación</a>
          <a href="#section-3" className="hover:text-white transition-colors">Crecimiento</a>
          <a href="/manual/" className="hover:text-white transition-colors">Manual</a>
        </nav>
        <a
          href="/admin/login"
          className="px-5 py-2 rounded-full border border-white/20 text-xs font-bold uppercase tracking-wider hover:bg-white hover:text-black transition-colors"
        >
          Iniciar Sesión
        </a>
        <a
          href="/admin/register?plan=trial"
          className="px-6 py-2 rounded-full bg-gradient-to-r from-[#ff3366] to-[#ec4899] text-xs font-extrabold uppercase tracking-wider text-white shadow-lg shadow-[#ff3366]/30 hover:scale-105 transition-transform"
        >
          14 Días Gratis
        </a>
      </div>

      {/* Mobile hamburger */}
      <button
        type="button"
        onClick={() => setIsMenuOpen(!isMenuOpen)}
        className="w-10 h-10 flex items-center justify-center relative md:hidden text-white focus:outline-none"
        aria-label="Abrir menú"
      >
        <span
          className={`absolute h-0.5 w-6 bg-white rounded-full transition-all duration-300 ease-[cubic-bezier(0.76,0,0.24,1)] ${
            isMenuOpen ? 'rotate-45 translate-y-0' : '-translate-y-2'
          }`}
        />
        <span
          className={`absolute h-0.5 w-6 bg-white rounded-full transition-all duration-300 ease-[cubic-bezier(0.76,0,0.24,1)] ${
            isMenuOpen ? 'opacity-0 scale-x-0' : 'opacity-100 scale-x-100'
          }`}
        />
        <span
          className={`absolute h-0.5 w-6 bg-white rounded-full transition-all duration-300 ease-[cubic-bezier(0.76,0,0.24,1)] ${
            isMenuOpen ? '-rotate-45 translate-y-0' : 'translate-y-2'
          }`}
        />
      </button>

      {/* Mobile menu overlay */}
      <div
        className={`fixed inset-0 z-40 md:hidden transition-opacity duration-300 ${
          isMenuOpen ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'
        }`}
      >
        <div
          className="absolute inset-0 bg-black/60 backdrop-blur-sm"
          onClick={() => setIsMenuOpen(false)}
        />
        <div
          className={`absolute top-0 right-0 h-full w-[85%] max-w-sm bg-[#0e1722] p-8 shadow-2xl flex flex-col justify-center gap-4 transition-transform duration-500 ease-[cubic-bezier(0.76,0,0.24,1)] ${
            isMenuOpen ? 'translate-x-0' : 'translate-x-full'
          }`}
        >
          {['Inicio', 'Operación', 'Crecimiento', 'Manual'].map((label, idx) => (
            <a
              key={label}
              href={label === 'Manual' ? '/manual/' : `#section-${idx + 1}`}
              onClick={() => setIsMenuOpen(false)}
              className="text-3xl font-extrabold text-white hover:text-[#00d2ff] transition-colors"
              style={{
                transitionDelay: `${100 + idx * 60}ms`,
                transform: isMenuOpen ? 'translateX(0)' : 'translateX(32px)',
                opacity: isMenuOpen ? 1 : 0,
                transition: 'all 0.5s cubic-bezier(0.76,0,0.24,1)',
              }}
            >
              {label}
            </a>
          ))}
          <div className="mt-8 pt-8 border-t border-slate-700 flex flex-col gap-3">
            <a
              href="/admin/login"
              className="w-full text-center py-3.5 rounded-full border border-white/20 text-white font-bold text-sm"
            >
              Iniciar Sesión
            </a>
            <a
              href="/admin/register?plan=trial"
              className="w-full text-center py-3.5 rounded-full bg-[#ff3366] text-white font-bold text-sm"
            >
              Probar 14 Días Gratis
            </a>
          </div>
        </div>
      </div>
    </header>
  );
};

// ============================================================================
// MAIN LANDING COMPONENT (App.tsx)
// ============================================================================
export const App: React.FC = () => {
  const [showSplash, setShowSplash] = useState(true);
  const isMobile = useIsMobile();

  // Section 1
  const section1Ref = useRef<HTMLElement | null>(null);
  const s1CardsRef = useRef<(HTMLElement | null)[]>([]);
  const s1Positions = useMaskPositions(section1Ref, s1CardsRef);
  const s1ImageWidth = useImageWidth(HERO_IMAGE, section1Ref);
  const s1Reveal = useStaggeredReveal(4);

  // Section 2
  const section2Ref = useRef<HTMLElement | null>(null);
  const s2CardsRef = useRef<(HTMLElement | null)[]>([]);
  const s2Positions = useMaskPositions(section2Ref, s2CardsRef);
  const s2ImageWidth = useImageWidth(SECTION2_IMAGE, section2Ref);
  const s2Reveal = useStaggeredReveal(4);

  // Section 3
  const s3Reveal = useStaggeredReveal(4);

  return (
    <div className="bg-[#070e14] text-white min-h-screen">
      {/* Splash Screen */}
      {showSplash && <SplashScreen onComplete={() => setShowSplash(false)} />}

      {/* Fixed Navbar */}
      <Navbar />

      {/* ==================================================================
          SECTION 1 - HERO
          ================================================================== */}
      <section
        ref={(el) => {
          section1Ref.current = el;
          s1Reveal.containerRef.current = el;
        }}
        id="section-1"
        className="h-screen w-full overflow-hidden flex flex-col pt-20 md:pt-24 px-3 md:px-5 pb-1.5 md:pb-2 gap-1.5 md:gap-2 box-border"
      >
        {/* 3 Feature Bars */}
        <div className="flex flex-col gap-1.5 md:gap-2 shrink-0">
          {featureBars.map((text, i) => (
            <MaskedCard
              key={text}
              cardRef={(el) => { s1CardsRef.current[i] = el; }}
              bgImage={HERO_IMAGE}
              position={s1Positions[i]}
              imageWidth={s1ImageWidth}
              focalX={isMobile ? 0.7 : 0.8}
              className="w-full h-12 md:h-16 shrink-0 rounded-xl md:rounded-2xl border border-white/10"
              style={s1Reveal.getAnimStyle(i)}
            >
              <div className="absolute inset-0 z-10 flex items-center justify-center bg-black/40 backdrop-blur-sm px-4">
                <span className="text-white text-sm md:text-xl font-bold tracking-tight text-center">
                  {text}
                </span>
              </div>
            </MaskedCard>
          ))}
        </div>

        {/* Main Hero Card (4th card) */}
        <MaskedCard
          cardRef={(el) => { s1CardsRef.current[3] = el; }}
          bgImage={HERO_IMAGE}
          position={s1Positions[3]}
          imageWidth={s1ImageWidth}
          focalX={isMobile ? 0.7 : 0.8}
          className="w-full flex-1 min-h-0 rounded-xl md:rounded-2xl border border-white/15"
          style={s1Reveal.getAnimStyle(3)}
        >
          {/* Top-left text */}
          <div className="absolute top-4 left-4 md:top-7 md:left-7 text-white text-xs md:text-sm font-semibold leading-relaxed max-w-[220px] md:max-w-[340px] z-10 drop-shadow-md">
            Plan básico para arrancar: menú digital, pedidos y caja en un solo lugar.
          </div>

          {/* Bottom-left block */}
          <div className="absolute bottom-5 left-4 md:bottom-8 md:left-7 z-10 flex flex-col gap-2">
            <span className="text-xs md:text-sm font-extrabold uppercase tracking-widest text-[#00d2ff]">
              EMPIEZA · PARA RESTAURANTES
            </span>
            <h1 className="text-white text-[clamp(2.8rem,9vw,8rem)] font-bold leading-[0.82] tracking-tight">
              Comienza<br />
              <span className="text-[#00d2ff]">hoy</span><span className="text-[#ff3366]">.</span>
            </h1>
            <a
              href="/admin/register?plan=starter"
              className="text-white text-sm md:text-lg font-bold underline decoration-[#00d2ff] decoration-2 underline-offset-4 hover:text-[#00d2ff] transition-colors"
            >
              Planes desde $349 MXN/mes
            </a>
            <div className="flex items-center gap-3 mt-1">
              <a
                href="/admin/register?plan=trial"
                className="px-6 py-3 md:px-8 md:py-4 rounded-full bg-gradient-to-r from-[#ff3366] to-[#ec4899] text-white font-extrabold text-xs md:text-base uppercase tracking-wider shadow-lg shadow-[#ff3366]/40 hover:scale-105 transition-transform"
              >
                PRUEBA 14 DÍAS GRATIS →
              </a>
              <span className="text-xs md:text-sm text-slate-300 hidden sm:inline">
                Sin complicarte. Crece a tu ritmo.
              </span>
            </div>
          </div>

          {/* Bottom-right block */}
          <div className="absolute bottom-6 right-4 md:bottom-8 md:right-7 z-10 flex flex-col items-end gap-2">
            <div className="flex items-center gap-3 text-xs md:text-sm font-bold tracking-wider text-slate-200 bg-black/60 backdrop-blur-md px-4 py-2 rounded-full border border-white/10">
              <a href="/admin/">ADMIN</a> · <a href="/pos/">POS</a> · <a href="/kds/">KDS</a> · <a href="/manual/">MANUAL</a>
            </div>
            <div className="flex items-center gap-2 text-[10px] md:text-xs font-semibold uppercase tracking-wider text-slate-300">
              <span className="w-2 h-2 rounded-full bg-[#10b981] animate-pulse" />
              MENÚ DIGITAL · PEDIDOS · CAJA
            </div>
          </div>
        </MaskedCard>
      </section>

      {/* ==================================================================
          SECTION 2 - OPERACIÓN EN VIVO (Grid)
          ================================================================== */}
      <section
        ref={(el) => {
          section2Ref.current = el;
          s2Reveal.containerRef.current = el;
        }}
        id="section-2"
        className="min-h-screen md:h-screen w-full overflow-hidden flex flex-col pt-1.5 md:pt-2 px-3 md:px-5 pb-1.5 md:pb-2 gap-1.5 md:gap-2 box-border"
      >
        <div className="flex-1 min-h-0 grid grid-cols-1 md:grid-cols-2 grid-rows-[auto_auto_auto_auto] md:grid-rows-[1fr_1fr_0.85fr] gap-1.5 md:gap-2">
          {/* Card 0 - Top Left */}
          <MaskedCard
            cardRef={(el) => { s2CardsRef.current[0] = el; }}
            bgImage={SECTION2_IMAGE}
            position={s2Positions[0]}
            imageWidth={s2ImageWidth}
            focalX={isMobile ? 0.65 : 0.8}
            className="rounded-xl md:rounded-2xl border border-white/10 min-h-[180px] md:min-h-0"
            style={s2Reveal.getAnimStyle(0)}
          >
            <div className="absolute inset-0 z-10 p-5 md:p-7 flex flex-col justify-between bg-black/50 backdrop-blur-sm">
              <div>
                <span className="text-xs font-bold uppercase tracking-widest text-[#ff6b00]">
                  PARA RESTAURANTES
                </span>
                <h2 className="text-2xl md:text-4xl font-bold leading-tight mt-1">
                  Tu restaurante.<br />
                  <span className="text-[#ff6b00]">Desde tu celular.</span>
                </h2>
                <p className="text-xs md:text-sm text-slate-300 mt-2 max-w-sm">
                  Recibe pedidos, actualiza tu menú y controla tus ventas en un solo lugar.
                </p>
              </div>
              <div className="flex flex-wrap gap-2 mt-2">
                <span className="px-3 py-1 rounded-full bg-white/10 border border-white/15 text-xs font-semibold">
                  📱 Todo desde tu celular
                </span>
                <span className="px-3 py-1 rounded-full bg-white/10 border border-white/15 text-xs font-semibold">
                  ⚡ Sin equipos costosos
                </span>
              </div>
            </div>
          </MaskedCard>

          {/* Card 1 - Top Right (spans 2 rows on desktop) */}
          <MaskedCard
            cardRef={(el) => { s2CardsRef.current[1] = el; }}
            bgImage={SECTION2_IMAGE}
            position={s2Positions[1]}
            imageWidth={s2ImageWidth}
            focalX={isMobile ? 0.65 : 0.8}
            className="md:row-span-2 rounded-xl md:rounded-2xl border border-white/10 min-h-[240px] md:min-h-0"
            style={s2Reveal.getAnimStyle(1)}
          >
            <div className="absolute inset-0 z-10 p-6 md:p-8 flex flex-col justify-between bg-black/60 backdrop-blur-sm">
              <div>
                <span className="text-xs font-bold uppercase tracking-widest text-[#ff6b00]">
                  PEDIDOS EN VIVO
                </span>
                <h2 className="text-2xl md:text-3xl font-bold mt-1">Recibe y organiza.</h2>
                <p className="text-xs md:text-sm text-slate-300 mt-1 max-w-sm">
                  Todos tus pedidos en un solo lugar. Fácil, rápido y sin perder ventas.
                </p>

                {/* Mockup orders */}
                <div className="mt-4 flex flex-col gap-2.5">
                  <div className="p-3.5 rounded-xl bg-slate-900/80 border border-white/15 flex items-center justify-between">
                    <div>
                      <div className="flex items-center gap-2">
                        <strong className="text-sm">#1286</strong>
                        <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                          Nuevo
                        </span>
                      </div>
                      <p className="text-xs text-slate-300 mt-0.5">María G. · 2x Hamb. Clásica</p>
                    </div>
                    <span className="text-sm font-bold text-white">$220</span>
                  </div>

                  <div className="p-3.5 rounded-xl bg-slate-900/60 border border-white/10 flex items-center justify-between opacity-80">
                    <div>
                      <div className="flex items-center gap-2">
                        <strong className="text-sm">#1285</strong>
                        <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-400 border border-amber-500/30">
                          En cocina
                        </span>
                      </div>
                      <p className="text-xs text-slate-300 mt-0.5">Carlos R. · 1x Pizza, 1x Refresco</p>
                    </div>
                    <span className="text-sm font-bold text-white">$180</span>
                  </div>
                </div>
              </div>

              <a
                href="/admin/register?plan=trial"
                className="self-end px-7 py-3.5 rounded-full bg-[#ff6b00] text-white font-bold text-sm hover:scale-105 transition-transform shadow-lg shadow-[#ff6b00]/30"
              >
                Comenzar gratis →
              </a>
            </div>
          </MaskedCard>

          {/* Card 2 - Bottom Left */}
          <MaskedCard
            cardRef={(el) => { s2CardsRef.current[2] = el; }}
            bgImage={SECTION2_IMAGE}
            position={s2Positions[2]}
            imageWidth={s2ImageWidth}
            focalX={isMobile ? 0.65 : 0.8}
            className="rounded-xl md:rounded-2xl border border-white/10 min-h-[160px] md:min-h-0"
            style={s2Reveal.getAnimStyle(2)}
          >
            <div className="absolute inset-0 z-10 p-5 md:p-7 flex flex-col justify-between bg-black/50 backdrop-blur-sm">
              <div>
                <span className="text-xs font-bold uppercase tracking-widest text-[#00d2ff]">
                  GESTIÓN DE MENÚ
                </span>
                <h2 className="text-[clamp(1.8rem,4vw,3.5rem)] font-bold leading-none mt-1">
                  Actualiza<br />al momento.
                </h2>
                <p className="text-xs md:text-sm text-slate-300 mt-2 max-w-sm">
                  Cambia precios, disponibilidad de platillos y fotos en segundos.
                </p>
              </div>
            </div>
          </MaskedCard>

          {/* Card 3 - Bottom Full Width (Services) */}
          <MaskedCard
            cardRef={(el) => { s2CardsRef.current[3] = el; }}
            bgImage={SECTION2_IMAGE}
            position={s2Positions[3]}
            imageWidth={s2ImageWidth}
            focalX={isMobile ? 0.65 : 0.8}
            className="col-span-1 md:col-span-2 rounded-xl md:rounded-2xl border border-white/10 min-h-[180px] md:min-h-0"
            style={s2Reveal.getAnimStyle(3)}
          >
            <div className="absolute inset-0 z-10 flex flex-wrap md:flex-nowrap gap-1.5 md:gap-2 p-2 md:p-3">
              {services.map((svc) => (
                <div
                  key={svc.num}
                  className={`flex-1 min-w-[calc(50%-4px)] md:min-w-0 rounded-xl md:rounded-2xl p-3 md:p-5 flex flex-col justify-between border transition-all ${
                    svc.active
                      ? 'bg-white/95 text-black border-white shadow-xl'
                      : 'bg-white/15 backdrop-blur-xl text-white border-white/15 hover:bg-white/25'
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <h3 className="text-lg md:text-2xl font-bold leading-tight whitespace-pre-line">
                      {svc.name}
                    </h3>
                    <span
                      className={`w-7 h-7 md:w-9 md:h-9 rounded-full border flex items-center justify-center text-xs font-bold ${
                        svc.active ? 'border-black text-black' : 'border-white text-white'
                      }`}
                    >
                      {svc.num}
                    </span>
                  </div>
                  <p className={`text-xs mt-2 ${svc.active ? 'text-slate-600' : 'text-slate-300'}`}>
                    {svc.desc}
                  </p>
                </div>
              ))}
            </div>
          </MaskedCard>
        </div>
      </section>

      {/* ==================================================================
          SECTION 3 - CRECIMIENTO Y ESCALA
          ================================================================== */}
      <section
        ref={s3Reveal.containerRef}
        id="section-3"
        className="min-h-screen md:h-screen w-full overflow-hidden flex flex-col pt-1.5 md:pt-2 px-3 md:px-5 pb-1.5 md:pb-2 gap-1.5 md:gap-2 box-border"
      >
        <div className="flex-1 min-h-0 grid grid-cols-1 md:grid-cols-2 gap-1.5 md:gap-2">
          {/* Left Column */}
          <div className="flex flex-col gap-1.5 md:gap-2">
            {/* Card 0: Heading */}
            <div
              className="rounded-xl md:rounded-2xl bg-[#111a24] border border-white/10 p-5 md:p-8 flex flex-col justify-between flex-[1.2] min-h-[160px] md:min-h-0"
              style={s3Reveal.getAnimStyle(0)}
            >
              <div>
                <span className="text-xs font-bold uppercase tracking-widest text-[#00d2ff]">
                  CONTROL TOTAL
                </span>
                <h2 className="text-[clamp(2.5rem,5.5vw,5rem)] font-bold leading-[0.95] text-white mt-1">
                  Haz crecer<br />tu negocio.
                </h2>
              </div>
              <p className="text-xs md:text-sm font-semibold text-slate-300">
                Más pedidos. Más control. Más tiempo para lo importante.
              </p>
            </div>

            {/* Card 1: Two Images */}
            <div
              className="flex gap-1.5 md:gap-2 flex-1 min-h-[120px] md:min-h-0"
              style={s3Reveal.getAnimStyle(1)}
            >
              <div className="flex-1 rounded-xl md:rounded-2xl overflow-hidden border border-white/10 relative">
                <img src={SECTION3_IMG1} alt="Menú digital" className="w-full h-full object-cover" />
                <span className="absolute bottom-2 left-2 px-2.5 py-1 rounded-full bg-black/70 backdrop-blur-md text-[10px] font-bold text-white">
                  Menú Inteligente
                </span>
              </div>
              <div className="flex-1 rounded-xl md:rounded-2xl overflow-hidden border border-white/10 relative">
                <img src={SECTION3_IMG2} alt="Comandas" className="w-full h-full object-cover" />
                <span className="absolute bottom-2 left-2 px-2.5 py-1 rounded-full bg-black/70 backdrop-blur-md text-[10px] font-bold text-white">
                  Comandas Directas
                </span>
              </div>
            </div>

            {/* Card 2: Pricing / Starter CTA */}
            <div
              className="rounded-xl md:rounded-2xl bg-[#1a2634] border border-white/10 p-5 md:p-7 flex items-end justify-between flex-[0.8] min-h-[140px] md:min-h-0"
              style={s3Reveal.getAnimStyle(2)}
            >
              <div>
                <p className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-1">
                  SIN ATADURAS
                </p>
                <h3 className="text-lg md:text-2xl font-bold text-white leading-tight">
                  Planes accesibles<br />desde $349 MXN/mes
                </h3>
              </div>
              <a
                href="/admin/register?plan=starter"
                className="px-6 py-3.5 md:px-8 md:py-4 bg-white rounded-full text-black text-sm md:text-base font-bold hover:scale-105 transition-transform"
              >
                Plan Inicial ↗
              </a>
            </div>
          </div>

          {/* Right Column: Tall Card with 2 overlays */}
          <div
            className="rounded-xl md:rounded-2xl overflow-hidden relative min-h-[350px] md:min-h-0 border border-white/10"
            style={s3Reveal.getAnimStyle(3)}
          >
            <img
              src={SECTION3_BG}
              alt="Crecimiento gastronómico"
              className="w-full h-full object-cover"
            />

            <div className="absolute bottom-3 left-3 right-3 md:bottom-5 md:left-5 md:right-5 flex gap-1.5 md:gap-2 z-10">
              {/* Overlay 1 (White) */}
              <div className="flex-1 bg-white rounded-xl md:rounded-2xl p-4 md:p-6 flex flex-col justify-between h-36 md:h-48 text-black shadow-2xl">
                <div>
                  <span className="text-[10px] font-bold uppercase tracking-wider text-[#ff6b00]">
                    VENTAS DIRECTAS
                  </span>
                  <h4 className="text-base md:text-xl font-bold leading-tight mt-1">
                    Comparte tu<br />enlace o QR
                  </h4>
                  <p className="text-[11px] text-slate-600 mt-1">
                    Ventas directas sin intermediarios.
                  </p>
                </div>
                <div className="self-end w-8 h-8 md:w-10 md:h-10 rounded-full border border-black flex items-center justify-center rotate-[-45deg]">
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                    <path d="M1 7h12m0 0L8 2m5 5L8 12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </div>
              </div>

              {/* Overlay 2 (Glass) */}
              <div className="flex-1 bg-black/60 backdrop-blur-xl border border-white/20 rounded-xl md:rounded-2xl p-4 md:p-6 flex flex-col justify-between h-36 md:h-48 text-white shadow-2xl">
                <div>
                  <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                    OPERACIÓN ÁGIL
                  </span>
                  <h4 className="text-base md:text-xl font-bold leading-tight mt-1">
                    La forma más<br />fácil de vender
                  </h4>
                  <p className="text-[11px] text-slate-300 mt-1">
                    Comandas y tickets automatizados.
                  </p>
                </div>
                <div className="self-end w-8 h-8 md:w-10 md:h-10 rounded-full border border-white flex items-center justify-center rotate-[-45deg] text-white">
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                    <path d="M1 7h12m0 0L8 2m5 5L8 12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
};

export default App;
