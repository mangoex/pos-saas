import json
from pathlib import Path


def main():
    md_path = Path("docs/MANUAL_RESTAURANTOS_COMPLETO.md")
    raw_md = md_path.read_text(encoding="utf-8")
    encoded_md = json.dumps(raw_md)

    html_content = f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="theme-color" content="#07130e">
  <title>RestaurantOS (Kiwi) — Manual Maestro & Blueprint Operativo</title>
  <meta name="description" content="Manual maestro interactivo, arquitectura, costeo matemático, operaciones de inventario e Inteligencia Artificial en RestaurantOS (Kiwi).">
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Ccircle cx='16' cy='16' r='15' fill='%2307130e'/%3E%3Ccircle cx='16' cy='16' r='9' fill='%23b9df53'/%3E%3Ccircle cx='16' cy='16' r='2.5' fill='%2307130e'/%3E%3C/svg%3E">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:ital,wght@0,300;0,400;0,500;0,600;0,700;0,800;1,400&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg-base: #060e0a;
      --bg-surface: #0c1a14;
      --bg-card: #11241c;
      --bg-card-hover: #162f25;
      --bg-glass: rgba(12, 26, 20, 0.85);
      --border-subtle: rgba(185, 223, 83, 0.12);
      --border-strong: rgba(185, 223, 83, 0.28);
      --primary: #b9df53;
      --primary-hover: #c9eb6b;
      --primary-dim: rgba(185, 223, 83, 0.15);
      --emerald: #10b981;
      --amber: #f59e0b;
      --rose: #f43f5e;
      --cyan: #06b6d4;
      --indigo: #6366f1;
      --text-main: #f1f5f9;
      --text-muted: #94a3b8;
      --text-dim: #64748b;
      --font-sans: 'Plus Jakarta Sans', system-ui, -apple-system, sans-serif;
      --font-mono: 'JetBrains Mono', monospace;
      --shadow-glow: 0 0 25px rgba(185, 223, 83, 0.12);
      --shadow-card: 0 10px 30px -10px rgba(0, 0, 0, 0.5);
      --radius-sm: 8px;
      --radius-md: 14px;
      --radius-lg: 20px;
      --radius-full: 9999px;
    }}

    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    html {{ scroll-behavior: smooth; font-family: var(--font-sans); background: var(--bg-base); color: var(--text-main); }}
    body {{ min-height: 100vh; line-height: 1.6; overflow-x: hidden; }}

    /* Top Navigation */
    .top-nav {{
      position: sticky; top: 0; z-index: 100;
      backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);
      background: var(--bg-glass);
      border-bottom: 1px solid var(--border-subtle);
      display: flex; align-items: center; justify-content: space-between;
      padding: 0.75rem 2rem;
    }}
    .brand {{
      display: flex; align-items: center; gap: 0.75rem; text-decoration: none; color: var(--text-main);
    }}
    .brand-logo {{
      width: 38px; height: 38px; border-radius: 50%;
      background: #07130e; border: 2px solid var(--primary);
      display: flex; align-items: center; justify-content: center;
    }}
    .brand-title {{ font-weight: 800; font-size: 1.15rem; letter-spacing: -0.02em; }}
    .brand-badge {{
      font-size: 0.7rem; font-weight: 700; text-transform: uppercase;
      background: var(--primary-dim); color: var(--primary);
      padding: 0.2rem 0.6rem; border-radius: var(--radius-full); border: 1px solid var(--border-subtle);
    }}
    .nav-links {{ display: flex; align-items: center; gap: 1.25rem; }}
    .nav-link {{
      color: var(--text-muted); text-decoration: none; font-size: 0.9rem; font-weight: 500;
      transition: color 0.2s;
    }}
    .nav-link:hover {{ color: var(--primary); }}
    .nav-actions {{ display: flex; align-items: center; gap: 0.75rem; }}
    .btn-download {{
      background: var(--primary); color: #07130e;
      border: none; padding: 0.5rem 1.1rem; border-radius: var(--radius-full);
      font-weight: 700; font-size: 0.88rem; cursor: pointer;
      display: flex; align-items: center; gap: 0.5rem; transition: transform 0.2s, background 0.2s, box-shadow 0.2s;
      box-shadow: 0 2px 10px rgba(185, 223, 83, 0.25);
    }}
    .btn-download:hover {{
      background: var(--primary-hover); transform: translateY(-1px);
      box-shadow: 0 4px 16px rgba(185, 223, 83, 0.4);
    }}
    .btn-outline {{
      background: transparent; color: var(--text-main);
      border: 1px solid var(--border-strong); padding: 0.45rem 0.9rem; border-radius: var(--radius-full);
      font-weight: 600; font-size: 0.85rem; text-decoration: none; transition: background 0.2s, border-color 0.2s;
    }}
    .btn-outline:hover {{ background: var(--bg-card); border-color: var(--primary); color: var(--primary); }}

    /* Hero Section */
    .hero {{
      padding: 4.5rem 2rem 3rem; max-width: 1200px; margin: 0 auto; text-align: center;
      position: relative;
    }}
    .hero-glow {{
      position: absolute; top: -50px; left: 50%; transform: translateX(-50%);
      width: 500px; height: 300px; background: radial-gradient(circle, rgba(185,223,83,0.15) 0%, rgba(6,14,10,0) 70%);
      pointer-events: none; z-index: -1;
    }}
    .hero-kicker {{
      display: inline-flex; align-items: center; gap: 0.5rem;
      background: var(--bg-card); border: 1px solid var(--border-strong);
      padding: 0.35rem 0.9rem; border-radius: var(--radius-full);
      font-size: 0.82rem; font-weight: 600; color: var(--primary); margin-bottom: 1.25rem;
    }}
    .hero-title {{
      font-size: 3.2rem; font-weight: 800; line-height: 1.15; letter-spacing: -0.03em;
      margin-bottom: 1.25rem;
    }}
    .hero-title span {{
      background: linear-gradient(135deg, #ffffff 30%, var(--primary) 100%);
      -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    }}
    .hero-subtitle {{
      font-size: 1.15rem; color: var(--text-muted); max-width: 780px; margin: 0 auto 2rem;
      line-height: 1.6;
    }}
    .hero-badges {{
      display: flex; flex-wrap: wrap; justify-content: center; gap: 0.6rem; margin-bottom: 2rem;
    }}
    .hero-badge {{
      background: var(--bg-surface); border: 1px solid var(--border-subtle);
      padding: 0.4rem 0.85rem; border-radius: var(--radius-full);
      font-size: 0.8rem; font-weight: 600; color: var(--text-muted);
      display: flex; align-items: center; gap: 0.4rem;
    }}
    .hero-badge.active {{ color: var(--primary); border-color: var(--border-strong); }}

    /* Layout Containers */
    .container {{ max-width: 1240px; margin: 0 auto; padding: 0 1.5rem; }}
    .section-title-wrap {{
      margin-bottom: 2rem; text-align: left;
    }}
    .section-tag {{
      font-size: 0.8rem; font-weight: 700; text-transform: uppercase; color: var(--primary);
      letter-spacing: 0.08em; margin-bottom: 0.35rem; display: block;
    }}
    .section-title {{
      font-size: 2rem; font-weight: 800; letter-spacing: -0.02em; color: var(--text-main);
    }}
    .section-desc {{ font-size: 1rem; color: var(--text-muted); margin-top: 0.4rem; max-width: 800px; }}

    /* Interactive Stepper (Guide & Map) */
    .stepper-container {{
      background: var(--bg-surface); border: 1px solid var(--border-subtle);
      border-radius: var(--radius-lg); padding: 2rem; margin-bottom: 3.5rem;
      box-shadow: var(--shadow-card);
    }}
    .stepper-nav {{
      display: grid; grid-template-columns: repeat(7, 1fr); gap: 0.5rem;
      border-bottom: 1px solid var(--border-subtle); padding-bottom: 1.5rem; margin-bottom: 2rem;
      overflow-x: auto;
    }}
    .step-btn {{
      background: var(--bg-card); border: 1px solid var(--border-subtle);
      border-radius: var(--radius-md); padding: 1rem 0.75rem; text-align: center;
      cursor: pointer; transition: all 0.2s; color: var(--text-muted);
      display: flex; flex-direction: column; align-items: center; gap: 0.4rem;
    }}
    .step-btn:hover {{ background: var(--bg-card-hover); border-color: var(--primary); color: var(--text-main); }}
    .step-btn.active {{
      background: var(--bg-card-hover); border-color: var(--primary); color: var(--primary);
      box-shadow: var(--shadow-glow);
    }}
    .step-num {{
      width: 26px; height: 26px; border-radius: 50%;
      background: rgba(185, 223, 83, 0.1); border: 1px solid var(--border-strong);
      display: flex; align-items: center; justify-content: center;
      font-size: 0.8rem; font-weight: 800;
    }}
    .step-btn.active .step-num {{ background: var(--primary); color: #07130e; }}
    .step-label {{ font-size: 0.8rem; font-weight: 700; line-height: 1.2; }}
    .step-content-card {{
      background: var(--bg-card); border: 1px solid var(--border-subtle);
      border-radius: var(--radius-md); padding: 1.75rem;
      display: grid; grid-template-columns: 1.2fr 1fr; gap: 2rem;
    }}
    .step-info h3 {{ font-size: 1.35rem; font-weight: 800; color: var(--primary); margin-bottom: 0.75rem; }}
    .step-info p {{ color: var(--text-muted); font-size: 0.95rem; margin-bottom: 1rem; line-height: 1.6; }}
    .step-rules-list {{ list-style: none; display: flex; flex-direction: column; gap: 0.5rem; }}
    .step-rules-list li {{
      font-size: 0.88rem; color: var(--text-main); display: flex; align-items: flex-start; gap: 0.5rem;
    }}
    .step-rules-list li::before {{ content: '✓'; color: var(--primary); font-weight: 800; }}
    .step-code-preview {{
      background: #040906; border: 1px solid rgba(185, 223, 83, 0.15);
      border-radius: var(--radius-sm); padding: 1.2rem; font-family: var(--font-mono);
      font-size: 0.82rem; color: #a7f3d0; overflow-x: auto;
    }}

    /* Calculator & Simulation Cards */
    .lab-grid {{
      display: grid; grid-template-columns: repeat(2, 1fr); gap: 1.75rem; margin-bottom: 3.5rem;
    }}
    .lab-card {{
      background: var(--bg-surface); border: 1px solid var(--border-subtle);
      border-radius: var(--radius-lg); padding: 1.75rem;
      display: flex; flex-direction: column; justify-content: space-between;
      box-shadow: var(--shadow-card);
    }}
    .lab-card.full-width {{ grid-column: 1 / -1; }}
    .lab-header {{ margin-bottom: 1.25rem; }}
    .lab-header h3 {{ font-size: 1.25rem; font-weight: 700; color: var(--text-main); display: flex; align-items: center; gap: 0.5rem; }}
    .lab-header p {{ font-size: 0.88rem; color: var(--text-muted); margin-top: 0.25rem; }}
    
    .form-group {{ margin-bottom: 1rem; }}
    .form-label {{ display: flex; justify-content: space-between; font-size: 0.84rem; font-weight: 600; color: var(--text-muted); margin-bottom: 0.35rem; }}
    .form-control {{
      width: 100%; background: var(--bg-card); border: 1px solid var(--border-subtle);
      color: var(--text-main); padding: 0.65rem 0.85rem; border-radius: var(--radius-sm);
      font-size: 0.92rem; font-family: var(--font-mono); outline: none; transition: border-color 0.2s;
    }}
    .form-control:focus {{ border-color: var(--primary); }}
    .slider-control {{ width: 100%; accent-color: var(--primary); cursor: pointer; }}

    .calc-result-box {{
      background: var(--bg-card); border: 1px solid var(--border-strong);
      border-radius: var(--radius-md); padding: 1.25rem; margin-top: 1rem;
    }}
    .calc-row {{
      display: flex; justify-content: space-between; align-items: center;
      padding: 0.4rem 0; font-size: 0.9rem; border-bottom: 1px dashed rgba(185, 223, 83, 0.1);
    }}
    .calc-row:last-child {{ border-bottom: none; }}
    .calc-val {{ font-family: var(--font-mono); font-weight: 700; color: var(--primary); font-size: 1.05rem; }}

    /* Donut Chart Simulation */
    .chart-container {{
      display: flex; align-items: center; justify-content: center; gap: 2rem; margin-top: 1rem;
    }}
    .donut-chart-wrap {{ position: relative; width: 160px; height: 160px; }}
    .donut-center-text {{
      position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
      text-align: center;
    }}
    .donut-pct {{ font-size: 1.4rem; font-weight: 800; color: var(--primary); font-family: var(--font-mono); }}
    .donut-lbl {{ font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase; }}

    /* AI Playground Section */
    .ai-playground {{
      background: var(--bg-surface); border: 1px solid var(--border-strong);
      border-radius: var(--radius-lg); padding: 2rem; margin-bottom: 3.5rem;
      box-shadow: var(--shadow-glow);
    }}
    .tabs-nav {{
      display: flex; gap: 0.75rem; border-bottom: 1px solid var(--border-subtle);
      padding-bottom: 1rem; margin-bottom: 1.5rem;
    }}
    .tab-btn {{
      background: transparent; border: none; color: var(--text-muted);
      font-size: 0.95rem; font-weight: 700; padding: 0.5rem 1rem; border-radius: var(--radius-full);
      cursor: pointer; transition: all 0.2s;
    }}
    .tab-btn.active {{
      background: var(--primary-dim); color: var(--primary); border: 1px solid var(--border-strong);
    }}
    .ai-console {{
      display: grid; grid-template-columns: 1fr 1.2fr; gap: 1.5rem;
    }}
    .ai-input-box {{
      background: var(--bg-card); border: 1px solid var(--border-subtle);
      border-radius: var(--radius-md); padding: 1.25rem; display: flex; flex-direction: column; gap: 1rem;
    }}
    .prompt-presets {{ display: flex; flex-wrap: wrap; gap: 0.4rem; }}
    .preset-chip {{
      background: var(--bg-surface); border: 1px solid var(--border-subtle);
      color: var(--text-muted); font-size: 0.78rem; padding: 0.35rem 0.65rem; border-radius: var(--radius-full);
      cursor: pointer; transition: all 0.2s;
    }}
    .preset-chip:hover {{ border-color: var(--primary); color: var(--text-main); }}
    .ai-output-box {{
      background: #040906; border: 1px solid rgba(185, 223, 83, 0.2);
      border-radius: var(--radius-md); padding: 1.25rem; font-family: var(--font-mono);
      font-size: 0.85rem; color: var(--text-main); display: flex; flex-direction: column; justify-content: space-between;
    }}
    .ai-pill {{
      display: inline-flex; align-items: center; gap: 0.4rem;
      padding: 0.2rem 0.5rem; border-radius: var(--radius-full); font-size: 0.72rem; font-weight: 700;
    }}
    .pill-ready {{ background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }}
    .pill-draft {{ background: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); }}

    /* Tables & Reference Section */
    .ref-table-wrap {{
      background: var(--bg-surface); border: 1px solid var(--border-subtle);
      border-radius: var(--radius-lg); overflow: hidden; margin-bottom: 3.5rem;
      box-shadow: var(--shadow-card);
    }}
    .ref-table-header {{
      padding: 1.25rem 1.75rem; border-bottom: 1px solid var(--border-subtle);
      display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem;
    }}
    .ref-table {{
      width: 100%; border-collapse: collapse; text-align: left; font-size: 0.88rem;
    }}
    .ref-table th {{
      background: var(--bg-card); color: var(--primary); font-weight: 700;
      padding: 0.9rem 1.25rem; border-bottom: 1px solid var(--border-subtle); text-transform: uppercase; font-size: 0.75rem; letter-spacing: 0.05em;
    }}
    .ref-table td {{
      padding: 0.9rem 1.25rem; border-bottom: 1px solid rgba(185, 223, 83, 0.06);
      color: var(--text-main);
    }}
    .ref-table tr:hover td {{ background: rgba(185, 223, 83, 0.03); }}
    .badge-check {{ color: var(--emerald); font-weight: 800; }}
    .badge-cross {{ color: var(--text-dim); }}

    /* Footer */
    footer {{
      border-top: 1px solid var(--border-subtle); background: var(--bg-surface);
      padding: 3rem 2rem 2rem; margin-top: 4rem; text-align: center;
    }}
    .footer-links {{
      display: flex; justify-content: center; gap: 1.5rem; margin-bottom: 1.5rem; flex-wrap: wrap;
    }}
    .footer-links a {{ color: var(--text-muted); text-decoration: none; font-size: 0.9rem; transition: color 0.2s; }}
    .footer-links a:hover {{ color: var(--primary); }}
    .footer-copy {{ font-size: 0.82rem; color: var(--text-dim); }}

    @media (max-width: 900px) {{
      .hero-title {{ font-size: 2.2rem; }}
      .stepper-nav {{ grid-template-columns: repeat(4, 1fr); }}
      .step-content-card {{ grid-template-columns: 1fr; }}
      .lab-grid {{ grid-template-columns: 1fr; }}
      .ai-console {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>

  <!-- Top Navigation -->
  <header class="top-nav">
    <a href="/" class="brand">
      <div class="brand-logo">
        <svg width="22" height="22" viewBox="0 0 32 32"><circle cx="16" cy="16" r="15" fill="#07130e"/><circle cx="16" cy="16" r="9" fill="#b9df53"/><circle cx="16" cy="16" r="2.5" fill="#07130e"/></svg>
      </div>
      <div>
        <div class="brand-title">RestaurantOS <span style="color:var(--primary)">Kiwi</span></div>
      </div>
      <span class="brand-badge">Manual Maestro</span>
    </a>
    <nav class="nav-links">
      <a href="#roadmap" class="nav-link">Guía & Mapa</a>
      <a href="#costeo" class="nav-link">Costeo Matemático</a>
      <a href="#inventarios" class="nav-link">Inventarios</a>
      <a href="#ia" class="nav-link">Inteligencia Artificial</a>
      <a href="#permisos" class="nav-link">Permisos</a>
    </nav>
    <div class="nav-actions">
      <button class="btn-download" id="btnDownloadMd" title="Descargar archivo Markdown completo">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
        Descargar .MD
      </button>
      <a href="/admin/" class="btn-outline">Admin</a>
      <a href="/pos/" class="btn-outline">POS</a>
      <a href="/kds/" class="btn-outline">KDS</a>
    </div>
  </header>

  <!-- Hero -->
  <section class="hero">
    <div class="hero-glow"></div>
    <div class="hero-kicker">
      <span>⚡ Blueprint Operativo & Especificación Técnica 1.0</span>
    </div>
    <h1 class="hero-title">
      Control Total de tu Cadena:<br>
      <span>De la Harina al Cobro en Caja</span>
    </h1>
    <p class="hero-subtitle">
      Guía interactiva completa de RestaurantOS: secuencia canónica de configuración, relaciones entre insumos y recetas, modelo matemático de costos, operaciones de inventario por lotes y el rol de la IA en Back Office y POS.
    </p>
    <div class="hero-badges">
      <span class="hero-badge active">🌿 Offline-First (PostgreSQL + SQLite)</span>
      <span class="hero-badge active">📊 Ledger Inmutable de Inventarios</span>
      <span class="hero-badge active">💰 Cero Flotantes (Centavos Exactos)</span>
      <span class="hero-badge active">🤖 IA con Human-in-the-Loop</span>
      <span class="hero-badge">⚡ KDS Multi-estación</span>
    </div>
  </section>

  <main class="container">

    <!-- SECTION 1: INTERACTIVE STEPPER & MAP -->
    <section id="roadmap" style="margin-bottom: 4rem;">
      <div class="section-title-wrap">
        <span class="section-tag">Paso a Paso Canónico</span>
        <h2 class="section-title">1. Orden de Configuración Inicial (De Cero a la Primera Venta)</h2>
        <p class="section-desc">
          El sistema exige respetar el árbol estricto de dependencias. Sigue este mapa interactivo para configurar tu restaurante sin errores de catálogo.
        </p>
      </div>

      <div class="stepper-container">
        <div class="stepper-nav" id="stepperNav">
          <button class="step-btn active" data-step="1">
            <span class="step-num">1</span>
            <span class="step-label">Organización</span>
          </button>
          <button class="step-btn" data-step="2">
            <span class="step-num">2</span>
            <span class="step-label">Insumos Base</span>
          </button>
          <button class="step-btn" data-step="3">
            <span class="step-num">3</span>
            <span class="step-label">Proveedores</span>
          </button>
          <button class="step-btn" data-step="4">
            <span class="step-num">4</span>
            <span class="step-label">Compras / CPP</span>
          </button>
          <button class="step-btn" data-step="5">
            <span class="step-num">5</span>
            <span class="step-label">Subrecetas / Lotes</span>
          </button>
          <button class="step-btn" data-step="6">
            <span class="step-num">6</span>
            <span class="step-label">Productos / Recetas</span>
          </button>
          <button class="step-btn" data-step="7">
            <span class="step-num">7</span>
            <span class="step-label">Cajas / KDS</span>
          </button>
        </div>

        <div class="step-content-card" id="stepCard">
          <div class="step-info">
            <h3 id="stepTitle">1. Estructura Organizacional</h3>
            <p id="stepDesc">
              Configura el Grupo corporativo, las Razones Sociales fiscales, las Unidades de Negocio (restaurante, panadería, etc.) y las Sucursales físicas con su único Almacén operativo vinculado.
            </p>
            <ul class="step-rules-list" id="stepRules">
              <li>Cada sucursal pertenece a exactamente una sola razón social fiscal.</li>
              <li>Cada sucursal tiene un único almacén formal donde se costean sus inventarios.</li>
              <li>El alta de sucursal crea automáticamente su almacén principal en una sola transacción.</li>
            </ul>
          </div>
          <div>
            <div style="font-size:0.75rem; font-weight:700; color:var(--text-muted); text-transform:uppercase; margin-bottom:0.4rem;">Entidades del Dominio</div>
            <pre class="step-code-preview" id="stepCode">Organization
  └── LegalEntity (RFC)
        └── BusinessUnit (restaurant)
              └── Branch (Sucursal Centro)
                    └── Warehouse (Almacén Principal)</pre>
          </div>
        </div>
      </div>
    </section>

    <!-- SECTION 2: COSTING & RELATIONSHIPS LAB -->
    <section id="costeo" style="margin-bottom: 4rem;">
      <div class="section-title-wrap">
        <span class="section-tag">Laboratorio de Costos</span>
        <h2 class="section-title">2. Relaciones y Fórmulas Matemáticas de Costeo</h2>
        <p class="section-desc">
          Experimenta en tiempo real cómo viaja el dinero desde el costal del proveedor hasta el margen de contribución de cada platillo vendido en caja.
        </p>
      </div>

      <div class="lab-grid">
        
        <!-- Simulator 1: Purchase Presentation to Base Unit -->
        <div class="lab-card">
          <div>
            <div class="lab-header">
              <h3>📦 1. Presentación de Compra a Costo Base</h3>
              <p>Convierte el empaque comercial del proveedor a costo exacto por kilogramo y gramo.</p>
            </div>
            <div class="form-group">
              <label class="form-label"><span>Contenido del Empaque Comercial:</span> <strong id="lblContent">25 kg</strong></label>
              <input type="range" class="slider-control" id="inputContent" min="1" max="100" value="25" step="1">
            </div>
            <div class="form-group">
              <label class="form-label"><span>Precio Neto de Compra ($ MXN):</span> <strong id="lblPrice">$450.00</strong></label>
              <input type="range" class="slider-control" id="inputPrice" min="50" max="3000" value="450" step="10">
            </div>
            <div class="form-group">
              <label class="form-label"><span>Rendimiento Aprovechable:</span> <strong id="lblYield">100%</strong></label>
              <input type="range" class="slider-control" id="inputYield" min="50" max="100" value="100" step="5">
            </div>
          </div>
          <div class="calc-result-box">
            <div class="calc-row"><span>Contenido Neto Útil:</span><span class="calc-val" id="resNetContent">25.00 kg</span></div>
            <div class="calc-row"><span>Costo Unitario Base:</span><span class="calc-val" id="resBaseCost">$18.00 / kg</span></div>
            <div class="calc-row"><span>Costo por Gramo:</span><span class="calc-val" id="resGramCost">$0.0180 / g</span></div>
          </div>
        </div>

        <!-- Simulator 2: Sub-recipe Batch Yield -->
        <div class="lab-card">
          <div>
            <div class="lab-header">
              <h3>🍳 2. Subreceta / Producción por Lotes</h3>
              <p>Calcula el costo unitario de un insumo elaborado (ej. 50 Panes Brioche artesanal).</p>
            </div>
            <div class="form-group">
              <label class="form-label"><span>Costo Total de Materias Primas Consumidas:</span> <strong id="lblBatchCost">$195.00 MXN</strong></label>
              <input type="range" class="slider-control" id="inputBatchCost" min="50" max="1000" value="195" step="5">
            </div>
            <div class="form-group">
              <label class="form-label"><span>Rendimiento Real Obtenido (Piezas):</span> <strong id="lblBatchYield">50 bollos</strong></label>
              <input type="range" class="slider-control" id="inputBatchYield" min="10" max="200" value="50" step="5">
            </div>
            <div class="form-group">
              <label class="form-label"><span>Merma en Proceso de Horneado:</span> <strong id="lblBatchWaste">5%</strong></label>
              <input type="range" class="slider-control" id="inputBatchWaste" min="0" max="20" value="5" step="1">
            </div>
          </div>
          <div class="calc-result-box">
            <div class="calc-row"><span>Insumo Elaborado Resultante:</span><span style="color:#fff; font-weight:700;">Pan Brioche Artesanal</span></div>
            <div class="calc-row"><span>Costo por Pieza Terminada:</span><span class="calc-val" id="resPieceCost">$3.90 / pza</span></div>
            <div class="calc-row"><span>Impacto en Venta POS:</span><span style="color:var(--text-muted); font-size:0.8rem;">Descarga 1 bollo al vender</span></div>
          </div>
        </div>

        <!-- Simulator 3: Full Dish Recipe & Food Cost % -->
        <div class="lab-card full-width">
          <div class="lab-header">
            <h3>🍔 3. Receta de Venta y Margen de Utilidad (Hamburguesa Gourmet)</h3>
            <p>Monitorea el Food Cost % y el margen bruto ajustando el precio de venta y la porción de carne.</p>
          </div>
          <div style="display:grid; grid-template-columns: 1fr 1fr; gap:2rem;">
            <div>
              <div class="form-group">
                <label class="form-label"><span>Precio de Venta al Público en POS:</span> <strong id="lblDishPrice" style="color:var(--primary); font-size:1.1rem;">$149.00 MXN</strong></label>
                <input type="range" class="slider-control" id="inputDishPrice" min="80" max="300" value="149" step="1">
              </div>
              <div class="form-group">
                <label class="form-label"><span>Carne Sirloin (Gramos netos):</span> <strong id="lblMeatGrams">200 g ($31.11)</strong></label>
                <input type="range" class="slider-control" id="inputMeatGrams" min="100" max="350" value="200" step="10">
              </div>
              <div style="font-size:0.82rem; color:var(--text-muted); line-height:1.6;">
                <strong>Componentes fijos de la receta:</strong><br>
                • Pan Brioche: 1 pza ($3.90)<br>
                • Queso Cheddar 40g ($7.20) | Tocino 30g ($8.25)<br>
                • Salsa BBQ 30ml ($2.40) | Vegetales y Empaque ($6.30)
              </div>
            </div>

            <div>
              <div class="chart-container">
                <div class="donut-chart-wrap">
                  <svg viewBox="0 0 36 36" style="transform: rotate(-90deg); width:100%; height:100%;">
                    <path stroke="#1f3d2b" stroke-width="4.5" fill="none" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"/>
                    <path id="donutSegment" stroke="#b9df53" stroke-width="4.5" stroke-dasharray="39.7, 100" stroke-linecap="round" fill="none" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"/>
                  </svg>
                  <div class="donut-center-text">
                    <div class="donut-pct" id="donutPct">39.7%</div>
                    <div class="donut-lbl">Food Cost</div>
                  </div>
                </div>
                <div style="display:flex; flex-direction:column; gap:0.5rem; flex:1;">
                  <div class="calc-row"><span>Costo Total Insumos:</span><span class="calc-val" id="resTotalFoodCost">$59.16</span></div>
                  <div class="calc-row"><span>Margen Bruto:</span><span class="calc-val" id="resGrossMargin" style="color:#34d399;">$89.84 (60.3%)</span></div>
                  <div class="calc-row"><span>Estado Semáforo:</span><span id="resHealthBadge" class="ai-pill pill-ready">🟢 Margen Saludable</span></div>
                </div>
              </div>
            </div>
          </div>
        </div>

      </div>
    </section>

    <!-- SECTION 3: INVENTORY OPERATIONS -->
    <section id="inventarios" style="margin-bottom: 4rem;">
      <div class="section-title-wrap">
        <span class="section-tag">Operaciones Avanzadas</span>
        <h2 class="section-title">3. Traspasos, Mermas y Conteos Físicos Ciegos</h2>
        <p class="section-desc">
          Descubre cómo el libro de movimientos inmutable garantiza que ninguna venta ni traspaso en tránsito desvirtúe las existencias.
        </p>
      </div>

      <div class="lab-grid">
        <!-- Transfer Simulator -->
        <div class="lab-card">
          <div class="lab-header">
            <h3>🚚 Traspasos entre Sucursales</h3>
            <p>El inventario viaja con su costo promedio congelado sin tratarse como una compra.</p>
          </div>
          <div class="calc-result-box" style="background:#07130e;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem;">
              <div style="text-align:center;">
                <div style="font-size:0.75rem; color:var(--text-muted);">ORIGEN (Centro)</div>
                <div style="font-weight:800; color:var(--primary); font-size:1.1rem;">TRANSFER_OUT</div>
                <div style="font-size:0.8rem; font-family:var(--font-mono);">10.0 kg @ $140/kg</div>
              </div>
              <div style="color:var(--primary); font-weight:800; font-size:1.5rem;">➜</div>
              <div style="text-align:center;">
                <div style="font-size:0.75rem; color:var(--text-muted);">EN TRÁNSITO</div>
                <div style="font-weight:800; color:#fbbf24; font-size:0.9rem;">Saldo Inmutable</div>
                <div style="font-size:0.75rem; color:var(--text-dim);">$1,400.00 MXN</div>
              </div>
              <div style="color:var(--primary); font-weight:800; font-size:1.5rem;">➜</div>
              <div style="text-align:center;">
                <div style="font-size:0.75rem; color:var(--text-muted);">DESTINO (Norte)</div>
                <div style="font-weight:800; color:#34d399; font-size:1.1rem;">TRANSFER_IN</div>
                <div style="font-size:0.8rem; font-family:var(--font-mono);">9.5 kg recibidos</div>
              </div>
            </div>
            <div style="font-size:0.82rem; color:var(--text-muted); border-top:1px solid var(--border-subtle); padding-top:0.6rem;">
              <strong>Manejo de Diferencia:</strong> 0.5 kg se documentan con motivo de daño. El destino absorbe los 9.5 kg a $140/kg directamente en su Costo Promedio Ponderado.
            </div>
          </div>
        </div>

        <!-- Blind Count Simulator -->
        <div class="lab-card">
          <div class="lab-header">
            <h3>🔍 Conteo Físico Ciego vs. Ledger Dinámico</h3>
            <p>Ajusta diferencias reales sin pisar ventas legítimas ocurridas durante la auditoría.</p>
          </div>
          <div class="calc-result-box" style="background:#07130e;">
            <div class="calc-row"><span>1. Fotografía Teórica (08:00 AM):</span><span class="calc-val">20.0 kg</span></div>
            <div class="calc-row"><span>2. Captura Ciega (Supervisor cuenta):</span><span class="calc-val" style="color:#38bdf8;">18.0 kg físicos</span></div>
            <div class="calc-row"><span>3. Venta en POS (08:30 AM):</span><span class="calc-val" style="color:#f43f5e;">-1.0 kg (Ledger: 19.0 kg)</span></div>
            <div class="calc-row" style="border-top:1px solid var(--border-strong); padding-top:0.6rem;">
              <span><strong>Ajuste Inteligente Aplicado:</strong></span>
              <span class="calc-val" style="color:var(--primary);">-1.0 kg (COUNT_ADJUSTMENT)</span>
            </div>
            <div style="font-size:0.75rem; color:var(--text-dim); margin-top:0.4rem;">
              Fórmula: Conteo Físico (18 kg) - Ledger Vigente (19 kg) = -1 kg. ¡Cero ventas perdidas!
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- SECTION 4: ARTIFICIAL INTELLIGENCE PLAYGROUND -->
    <section id="ia" style="margin-bottom: 4rem;">
      <div class="section-title-wrap">
        <span class="section-tag">Inteligencia Artificial Segura</span>
        <h2 class="section-title">4. IA en Back Office y Punto de Venta (Playground)</h2>
        <p class="section-desc">
          Prueba el comportamiento del copiloto administrativo y la captura de pedidos por voz sin riesgo de alucinación ni exposición de datos personales.
        </p>
      </div>

      <div class="ai-playground">
        <div class="tabs-nav">
          <button class="tab-btn active" id="tabBtnBackoffice" onclick="switchAiTab('backoffice')">🏢 Back Office Copilot (AIA-001/002)</button>
          <button class="tab-btn" id="tabBtnPos" onclick="switchAiTab('pos')">🎙️ POS Captura Asistida por Voz</button>
        </div>

        <!-- Backoffice AI Tab -->
        <div id="aiTabBackoffice" class="ai-console">
          <div class="ai-input-box">
            <div style="font-size:0.85rem; font-weight:700; color:var(--text-main);">Selecciona una consulta de diagnóstico:</div>
            <div class="prompt-presets">
              <button class="preset-chip" onclick="setPrompt('¿Qué insumos no tienen precio?')">¿Qué insumos no tienen precio?</button>
              <button class="preset-chip" onclick="setPrompt('Crear insumo Salsa Tártara 1L')">Crear insumo Salsa Tártara</button>
              <button class="preset-chip" onclick="setPrompt('¿Cuál es la merma promedio de pechuga de pollo?')">Consultar regla de merma</button>
            </div>
            <textarea id="aiPromptInput" class="form-control" rows="3" style="resize:none;">¿Qué insumos no tienen precio?</textarea>
            <button class="btn-download" style="justify-content:center;" onclick="simulateAiResponse()">
              <span>Ejecutar Diagnóstico IA</span>
            </button>
          </div>

          <div class="ai-output-box">
            <div>
              <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.75rem;">
                <span style="font-size:0.75rem; color:var(--text-muted); text-transform:uppercase;">Respuesta del Motor Canónico</span>
                <span id="aiStateBadge" class="ai-pill pill-draft">DRAFT (Sin Cambios)</span>
              </div>
              <div id="aiOutputText" style="line-height:1.6; color:#e2e8f0; font-size:0.86rem;">
                Para responder con precisión contable, por favor especifica qué autoridad deseas diagnosticar:<br><br>
                1. <strong>Precio de Compra de Proveedor:</strong> Insumos sin presentación activa con precio.<br>
                2. <strong>Costo Promedio Ponderado:</strong> Insumos sin recepción confirmada en la sucursal actual.<br><br>
                <em>(El sistema no mezcla catálogos ni inventa costos cero).</em>
              </div>
            </div>
            <div style="border-top:1px solid rgba(185,223,83,0.15); padding-top:0.75rem; margin-top:1rem; font-size:0.75rem; color:var(--text-dim);">
              🔒 PII Protegido: Excluidos saldos de caja, ventas de empleados y clientes.
            </div>
          </div>
        </div>

        <!-- POS Voice AI Tab -->
        <div id="aiTabPos" class="ai-console" style="display:none;">
          <div class="ai-input-box">
            <div style="font-size:0.85rem; font-weight:700; color:var(--text-main);">Dicta o escribe el pedido del cliente:</div>
            <div class="prompt-presets">
              <button class="preset-chip" onclick="setVoicePrompt('Un baguette de BBQ sin cebolla y unas papas para recoger a nombre de Miguel González 6672013019')">Baguette BBQ sin cebolla</button>
              <button class="preset-chip" onclick="setVoicePrompt('2 hamburguesas con queso y un refresco a domicilio para Laura 6671234567')">Hamburguesas + Bebida</button>
            </div>
            <textarea id="voicePromptInput" class="form-control" rows="3" style="resize:none;">Un baguette de BBQ sin cebolla y unas papas para recoger a nombre de Miguel González 6672013019</textarea>
            <button class="btn-download" style="justify-content:center;" onclick="simulateVoiceParse()">
              <span>Interpretar y Llenar Carrito</span>
            </button>
          </div>

          <div class="ai-output-box">
            <div>
              <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.75rem;">
                <span style="font-size:0.75rem; color:var(--text-muted); text-transform:uppercase;">Sanitización PII & Carrito Borrador</span>
                <span class="ai-pill pill-ready">LISTO PARA COBRO</span>
              </div>
              <div id="voiceOutputText" style="line-height:1.6; color:#e2e8f0; font-size:0.86rem;">
                <span style="color:#38bdf8;">👤 Cliente Resuelto:</span> [REDACTED_NAME] (Tel: [REDACTED_PHONE])<br>
                <span style="color:#fbbf24;">📦 Modalidad:</span> Para Recoger (takeout)<br>
                <span style="color:#34d399;">🛒 Líneas en Carrito:</span><br>
                • 1x Baguette BBQ ($120.00) ➔ <em>Comentario: Sin cebolla</em><br>
                • 1x Papas Gajo ($45.00)<br>
                <strong>Total a Cobrar en Caja: $165.00 MXN</strong>
              </div>
            </div>
            <div style="border-top:1px solid rgba(185,223,83,0.15); padding-top:0.75rem; margin-top:1rem; font-size:0.75rem; color:var(--text-dim);">
              ✓ El cajero revisa visualmente y confirma el cobro en caja física.
            </div>
          </div>
        </div>

      </div>
    </section>

    <!-- SECTION 5: ROLES & PERMISSION MATRIX -->
    <section id="permisos" style="margin-bottom: 4rem;">
      <div class="section-title-wrap">
        <span class="section-tag">Seguridad y Accesos</span>
        <h2 class="section-title">5. Matriz Canónica de Permisos por Rol</h2>
        <p class="section-desc">
          La autoridad se gobierna exclusivamente mediante permisos granulares en backend, jamás por nombres cosméticos de roles.
        </p>
      </div>

      <div class="ref-table-wrap">
        <div class="ref-table-header">
          <div style="font-weight:700; color:var(--text-main);">Permisos de Dominio vs. Roles Operativos</div>
          <input type="text" id="searchPerms" placeholder="Filtrar permisos..." class="form-control" style="width:220px; font-size:0.82rem; padding:0.4rem 0.75rem;">
        </div>
        <table class="ref-table" id="permsTable">
          <thead>
            <tr>
              <th>Permiso Granular</th>
              <th>Admin Corporativo</th>
              <th>Supervisor Sucursal</th>
              <th>Cajero</th>
              <th>Encargado Inventarios</th>
              <th>Auditor</th>
            </tr>
          </thead>
          <tbody>
            <tr><td><code>admin.manage</code></td><td class="badge-check">✓</td><td class="badge-cross">—</td><td class="badge-cross">—</td><td class="badge-cross">—</td><td class="badge-cross">—</td></tr>
            <tr><td><code>branch.admin.access</code></td><td class="badge-check">✓</td><td class="badge-check">✓</td><td class="badge-cross">—</td><td class="badge-cross">—</td><td class="badge-cross">—</td></tr>
            <tr><td><code>catalog.branch.manage</code></td><td class="badge-check">✓</td><td class="badge-check">✓</td><td class="badge-cross">—</td><td class="badge-cross">—</td><td class="badge-cross">—</td></tr>
            <tr><td><code>pos.operate</code> / <code>orders.create</code></td><td class="badge-check">✓</td><td class="badge-check">✓</td><td class="badge-check">✓</td><td class="badge-cross">—</td><td class="badge-cross">—</td></tr>
            <tr><td><code>cash.shift.open/close</code></td><td class="badge-check">✓</td><td class="badge-check">✓</td><td class="badge-check">✓</td><td class="badge-cross">—</td><td class="badge-cross">—</td></tr>
            <tr><td><code>payments.confirm</code></td><td class="badge-check">✓</td><td class="badge-check">✓</td><td class="badge-check">✓</td><td class="badge-cross">—</td><td class="badge-cross">—</td></tr>
            <tr><td><code>purchases.manage</code></td><td class="badge-check">✓</td><td class="badge-check">✓</td><td class="badge-cross">—</td><td class="badge-check">✓</td><td class="badge-cross">—</td></tr>
            <tr><td><code>production.manage</code></td><td class="badge-check">✓</td><td class="badge-check">✓</td><td class="badge-cross">—</td><td class="badge-check">✓</td><td class="badge-cross">—</td></tr>
            <tr><td><code>inventory.transfer.send</code></td><td class="badge-check">✓</td><td class="badge-check">✓</td><td class="badge-cross">—</td><td class="badge-check">✓</td><td class="badge-cross">—</td></tr>
            <tr><td><code>inventory.transfer.receive</code></td><td class="badge-check">✓</td><td class="badge-check">✓</td><td class="badge-cross">—</td><td class="badge-check">✓</td><td class="badge-cross">—</td></tr>
            <tr><td><code>inventory.waste</code></td><td class="badge-check">✓</td><td class="badge-check">✓</td><td class="badge-cross">—</td><td class="badge-check">✓</td><td class="badge-cross">—</td></tr>
            <tr><td><code>inventory.count</code></td><td class="badge-check">✓</td><td class="badge-check">✓</td><td class="badge-cross">—</td><td class="badge-check">✓</td><td class="badge-cross">—</td></tr>
            <tr><td><code>audit.read</code></td><td class="badge-check">✓</td><td class="badge-check">✓</td><td class="badge-cross">—</td><td class="badge-cross">—</td><td class="badge-check">✓</td></tr>
          </tbody>
        </table>
      </div>
    </section>

  </main>

  <!-- Footer -->
  <footer>
    <div class="footer-links">
      <a href="/">Inicio Kiwi</a>
      <a href="/admin/">Admin Back Office</a>
      <a href="/pos/">Punto de Venta POS</a>
      <a href="/kds/">Cocina KDS</a>
      <a href="/menu/">Menú Móvil</a>
    </div>
    <p class="footer-copy">
      RestaurantOS (Kiwi) © 2026. Plataforma de Alto Rendimiento para Cadenas Gastronómicas.
    </p>
  </footer>

  <!-- EMBEDDED JAVASCRIPT LOGIC -->
  <script>
    // 1. Download Full Markdown
    const rawMarkdownContent = {encoded_md};
    document.getElementById('btnDownloadMd').addEventListener('click', () => {{
      const blob = new Blob([rawMarkdownContent], {{ type: 'text/markdown;charset=utf-8' }});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'MANUAL_RESTAURANTOS_COMPLETO.md';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }});

    // 2. Stepper Data & Logic
    const stepsData = {{
      1: {{
        title: '1. Estructura Organizacional',
        desc: 'Configura el Grupo corporativo, las Razones Sociales fiscales, las Unidades de Negocio (restaurante, panadería, etc.) y las Sucursales físicas con su único Almacén operativo vinculado.',
        rules: [
          'Cada sucursal pertenece a exactamente una sola razón social fiscal.',
          'Cada sucursal tiene un único almacén formal donde se costean sus inventarios.',
          'El alta de sucursal crea automáticamente su almacén principal en una sola transacción.'
        ],
        code: `Organization\\n  └── LegalEntity (RFC)\\n        └── BusinessUnit (restaurant)\\n              └── Branch (Sucursal Centro)\\n                    └── Warehouse (Almacén Principal)`
      }},
      2: {{
        title: '2. Insumos Base Corporativos',
        desc: 'Materias primas puras sin procesar en la unidad de medida base indivisible (kg, g, l, ml, pza). El catálogo de insumos es compartido y corporativo.',
        rules: [
          'Unidad base estandarizada internacional (kg, g, l, ml, pza).',
          'SKU normalizado compuesto exclusivamente por dígitos ASCII.',
          'No se asignan costos manuales editables; el costo proviene de compras confirmadas.'
        ],
        code: `InventoryItem(\\n  id=\"uuid-001\",\\n  sku=\"100234\",\\n  name=\"HARINA DE TRIGO\",\\n  base_unit=\"kg\",\\n  item_type=\"RAW_MATERIAL\"\\n)`
      }},
      3: {{
        title: '3. Proveedores y Presentaciones de Compra',
        desc: 'Empaques comerciales del proveedor (bulto 25kg, caja 12pz, cubeta 19L) con factor de conversión exacto hacia la unidad base y precio de lista.',
        rules: [
          'Contenido neto y aprovechable en unidad base.',
          'Editar precio de catálogo crea historial pero NO modifica costo contable en almacén.',
          'Maneja condiciones de crédito, días de entrega y contactos por sucursal.'
        ],
        code: `PurchasePresentation(\\n  supplier_id=\"uuid-prov-1\",\\n  item_id=\"uuid-harina\",\\n  commercial_unit=\"Bulto 25kg\",\\n  package_content=25.0000,\\n  yield_ratio=1.0000,\\n  last_price_cents=45000\\n)`
      }},
      4: {{
        title: '4. Compras Directas y Costo Promedio Ponderado',
        desc: 'Recepción física de mercancía en el almacén. Genera la entrada en el Ledger (PURCHASE_RECEIPT) y fija el nuevo Costo Promedio Ponderado móvil.',
        rules: [
          'El costo promedio contable se recalcula exclusivamente al confirmar la recepción física.',
          'Si se pagó de caja, crea retiro inmutable (WITHDRAWAL) vinculado uno a uno.',
          'Existencia negativa bloquea compras para evitar distorsión de costeo.'
        ],
        code: `CPP_Nuevo = [ (Exist_Ant * CPP_Ant) + (Cant_Rec * Costo_Rec) ]\\n            / (Exist_Ant + Cant_Rec)\\n\\nMovimiento: PURCHASE_RECEIPT (+25.0 kg @ $18.00/kg)`
      }},
      5: {{
        title: '5. Subrecetas / Producción por Lotes',
        desc: 'Fórmulas para elaborar insumos intermedios en cocina (masas, salsas, aderezos porcionados). Consume materias primas y da de alta el insumo elaborado.',
        rules: [
          'Explosión de materias primas con PRODUCTION_INPUT.',
          'Alta del insumo elaborado con PRODUCTION_OUTPUT valorizado al costo real del lote.',
          'La venta posterior descarga el elaborado; nunca vuelve a explotar materias primas.'
        ],
        code: `ProductionBatch(\\n  recipe=\"LOTE 50 PANES BRIOCHE\",\\n  inputs=[Harina 3.5kg, Mantequilla 0.5kg, Huevo 10pz],\\n  output=50 panes @ $3.90/pza\\n)`
      }},
      6: {{
        title: '6. Productos, Precios y Recetas de Venta',
        desc: 'Platillos terminados del menú POS. Cada producto tiene estación KDS, selector previo de tamaño, modificadores, ingredientes extras y receta de porción.',
        rules: [
          'Selector previo obligatorio (ej. Tamaño) antes de listar productos en POS.',
          'Fórmula de merma estándar: Cantidad Bruta = Cantidad Neta / (1 - Merma).',
          'Comentarios (ej. Sin cebolla) van a cocina sin alterar costo ni inventario.'
        ],
        code: `Product(\"HAMBURGUESA GOURMET\", price_cents=14900)\\nRecipeComponent(item=\"Pan Brioche\", qty=1 pza, cost=$3.90)\\nRecipeComponent(item=\"Carne Sirloin\", gross_qty=0.222kg, cost=$31.11)`
      }},
      7: {{
        title: '7. Cajas, KDS e Impresoras Térmicas',
        desc: 'Infraestructura física y operativa de la sucursal. Apertura de turno con fondo inicial, ruteo automático de comandas a pantallas KDS y cobro inmutable.',
        rules: [
          'Apertura de turno (cash.shift.open) obligatoria para crear pedidos.',
          'KDS divide componentes automáticamente entre cocina, bebidas y empaque.',
          'Cobro idempotente: pagos confirmados son inmutables y admiten cortes parciales.'
        ],
        code: `POST /api/v1/orders/{{id}}/payments\\nIdempotency-Key: \"chk-8837194\"\\nMethod: \"cash\" | \"debit_card\" | \"credit_card\" | \"transfer\"`
      }}
    }};

    document.querySelectorAll('.step-btn').forEach(btn => {{
      btn.addEventListener('click', () => {{
        document.querySelectorAll('.step-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const s = stepsData[btn.dataset.step];
        document.getElementById('stepTitle').innerText = s.title;
        document.getElementById('stepDesc').innerText = s.desc;
        document.getElementById('stepRules').innerHTML = s.rules.map(r => `<li>${{r}}</li>`).join('');
        document.getElementById('stepCode').innerText = s.code;
      }});
    }});

    // 3. Calculator 1: Presentation to Base Unit
    const inputContent = document.getElementById('inputContent');
    const inputPrice = document.getElementById('inputPrice');
    const inputYield = document.getElementById('inputYield');

    function updateCalc1() {{
      const content = parseFloat(inputContent.value);
      const price = parseFloat(inputPrice.value);
      const yieldPct = parseFloat(inputYield.value) / 100;

      document.getElementById('lblContent').innerText = content + ' kg';
      document.getElementById('lblPrice').innerText = '$' + price.toFixed(2);
      document.getElementById('lblYield').innerText = (yieldPct * 100).toFixed(0) + '%';

      const netUseful = content * yieldPct;
      const baseCost = price / netUseful;
      const gramCost = baseCost / 1000;

      document.getElementById('resNetContent').innerText = netUseful.toFixed(2) + ' kg';
      document.getElementById('resBaseCost').innerText = '$' + baseCost.toFixed(2) + ' / kg';
      document.getElementById('resGramCost').innerText = '$' + gramCost.toFixed(4) + ' / g';
    }}
    inputContent.addEventListener('input', updateCalc1);
    inputPrice.addEventListener('input', updateCalc1);
    inputYield.addEventListener('input', updateCalc1);
    updateCalc1();

    // 4. Calculator 2: Batch Production
    const inputBatchCost = document.getElementById('inputBatchCost');
    const inputBatchYield = document.getElementById('inputBatchYield');
    const inputBatchWaste = document.getElementById('inputBatchWaste');

    function updateCalc2() {{
      const cost = parseFloat(inputBatchCost.value);
      const yieldQty = parseFloat(inputBatchYield.value);
      const waste = parseFloat(inputBatchWaste.value);

      document.getElementById('lblBatchCost').innerText = '$' + cost.toFixed(2) + ' MXN';
      document.getElementById('lblBatchYield').innerText = yieldQty + ' bollos';
      document.getElementById('lblBatchWaste').innerText = waste + '%';

      const pieceCost = cost / yieldQty;
      document.getElementById('resPieceCost').innerText = '$' + pieceCost.toFixed(2) + ' / pza';
    }}
    inputBatchCost.addEventListener('input', updateCalc2);
    inputBatchYield.addEventListener('input', updateCalc2);
    inputBatchWaste.addEventListener('input', updateCalc2);
    updateCalc2();

    // 5. Calculator 3: Dish Recipe & Food Cost
    const inputDishPrice = document.getElementById('inputDishPrice');
    const inputMeatGrams = document.getElementById('inputMeatGrams');

    function updateCalc3() {{
      const price = parseFloat(inputDishPrice.value);
      const meatGrams = parseFloat(inputMeatGrams.value);

      const meatGrossGrams = meatGrams / (1 - 0.10); // 10% waste
      const meatCost = (meatGrossGrams / 1000) * 140.0; // $140/kg sirloin

      document.getElementById('lblDishPrice').innerText = '$' + price.toFixed(2) + ' MXN';
      document.getElementById('lblMeatGrams').innerText = meatGrams + ' g ($' + meatCost.toFixed(2) + ')';

      const fixedCosts = 3.90 + 7.20 + 8.25 + 2.40 + 6.30; // Bun, Cheese, Bacon, BBQ, Veggies & Pack
      const totalFoodCost = meatCost + fixedCosts;
      const grossMargin = price - totalFoodCost;
      const foodCostPct = (totalFoodCost / price) * 100;
      const marginPct = 100 - foodCostPct;

      document.getElementById('resTotalFoodCost').innerText = '$' + totalFoodCost.toFixed(2);
      document.getElementById('resGrossMargin').innerText = '$' + grossMargin.toFixed(2) + ' (' + marginPct.toFixed(1) + '%)';
      document.getElementById('donutPct').innerText = foodCostPct.toFixed(1) + '%';
      document.getElementById('donutSegment').setAttribute('stroke-dasharray', foodCostPct.toFixed(1) + ', 100');

      const badge = document.getElementById('resHealthBadge');
      if (foodCostPct < 35) {{
        badge.className = 'ai-pill pill-ready';
        badge.innerText = '🟢 Margen Excelente (<35%)';
        document.getElementById('donutSegment').setAttribute('stroke', '#10b981');
      }} else if (foodCostPct <= 45) {{
        badge.className = 'ai-pill pill-draft';
        badge.innerText = '🟡 Margen Saludable (35-45%)';
        document.getElementById('donutSegment').setAttribute('stroke', '#b9df53');
      }} else {{
        badge.className = 'ai-pill';
        badge.style.background = 'rgba(244,63,94,0.2)';
        badge.style.color = '#f43f5e';
        badge.innerText = '🔴 Alto Riesgo (>45%)';
        document.getElementById('donutSegment').setAttribute('stroke', '#f43f5e');
      }}
    }}
    inputDishPrice.addEventListener('input', updateCalc3);
    inputMeatGrams.addEventListener('input', updateCalc3);
    updateCalc3();

    // 6. AI Playground Tabs & Simulations
    function switchAiTab(tab) {{
      if (tab === 'backoffice') {{
        document.getElementById('aiTabBackoffice').style.display = 'grid';
        document.getElementById('aiTabPos').style.display = 'none';
        document.getElementById('tabBtnBackoffice').classList.add('active');
        document.getElementById('tabBtnPos').classList.remove('active');
      }} else {{
        document.getElementById('aiTabBackoffice').style.display = 'none';
        document.getElementById('aiTabPos').style.display = 'grid';
        document.getElementById('tabBtnBackoffice').classList.remove('active');
        document.getElementById('tabBtnPos').classList.add('active');
      }}
    }}

    function setPrompt(p) {{
      document.getElementById('aiPromptInput').value = p;
      simulateAiResponse();
    }}
    function setVoicePrompt(p) {{
      document.getElementById('voicePromptInput').value = p;
      simulateVoiceParse();
    }}

    function simulateAiResponse() {{
      const q = document.getElementById('aiPromptInput').value.toLowerCase();
      const out = document.getElementById('aiOutputText');
      const badge = document.getElementById('aiStateBadge');

      if (q.includes('precio') || q.includes('insumos')) {{
        badge.className = 'ai-pill pill-draft';
        badge.innerText = 'DRAFT (Aclaración)';
        out.innerHTML = `Para responder con precisión contable, por favor especifica qué autoridad deseas diagnosticar:<br><br>
        1. <strong>Precio de Compra de Proveedor:</strong> Insumos sin presentación activa con precio.<br>
        2. <strong>Costo Promedio Ponderado:</strong> Insumos sin recepción confirmada en la sucursal actual.<br><br>
        <em>(El sistema no mezcla catálogos ni inventa costos cero).</em>`;
      }} else if (q.includes('crear') || q.includes('salsa')) {{
        badge.className = 'ai-pill pill-ready';
        badge.innerText = 'READY_FOR_REVIEW';
        out.innerHTML = `<strong>Propuesta de Catálogo Generada:</strong><br>
        • Acción: <code>create_inventory_item</code><br>
        • Nombre: <strong>SALSA TÁRTARA</strong> | Unidad Base: <strong>l</strong><br>
        • Tipo: Insumo Elaborado (PREPARED)<br>
        • Fingerprint: <code>sha256-8a91b...</code><br><br>
        <button class="btn-outline" style="padding:0.25rem 0.6rem; font-size:0.75rem; background:rgba(185,223,83,0.1);" onclick="alert('¡Propuesta aplicada mediante servicio canónico en backend con Idempotency-Key!')">Aceptar y Aplicar</button>
        <button class="btn-outline" style="padding:0.25rem 0.6rem; font-size:0.75rem;" onclick="alert('Propuesta descartada. Cero escrituras en base de datos.')">Rechazar</button>`;
      }} else {{
        badge.className = 'ai-pill pill-ready';
        badge.innerText = 'CANONICAL_RULE';
        out.innerHTML = `<strong>Regla PRD-FR-084 / SDD 5.8:</strong><br>
        La merma de pechuga de pollo se presupuesta al 10% en corte y limpieza. La cantidad bruta se calcula como <code>bruta = neta / (1 - 0.10)</code>. No genera salida duplicada de inventario.`;
      }}
    }}

    function simulateVoiceParse() {{
      const q = document.getElementById('voicePromptInput').value;
      const out = document.getElementById('voiceOutputText');

      out.innerHTML = `
        <span style="color:#38bdf8;">👤 Cliente Resuelto:</span> [REDACTED_NAME] (Tel: [REDACTED_PHONE])<br>
        <span style="color:#fbbf24;">📦 Modalidad:</span> Para Recoger (takeout)<br>
        <span style="color:#34d399;">🛒 Líneas en Carrito:</span><br>
        • 1x Baguette BBQ ($120.00) ➔ <em>Comentario: Sin cebolla</em><br>
        • 1x Papas Gajo ($45.00)<br>
        <strong>Total a Cobrar en Caja: $165.00 MXN</strong>
      `;
    }}

    // 7. Search Filter in Permission Table
    document.getElementById('searchPerms').addEventListener('input', (e) => {{
      const term = e.target.value.toLowerCase();
      document.querySelectorAll('#permsTable tbody tr').forEach(row => {{
        const txt = row.innerText.toLowerCase();
        row.style.display = txt.includes(term) ? '' : 'none';
      }});
    }});
  </script>
</body>
</html>
"""

    output_dir = Path("apps/landing-web/src/manual")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "index.html").write_text(html_content, encoding="utf-8")
    Path("apps/landing-web/src/manual.html").write_text(html_content, encoding="utf-8")
    print("Manual pages generated successfully in apps/landing-web/src/manual/index.html and apps/landing-web/src/manual.html")

if __name__ == "__main__":
    main()