import React, { useState, useMemo, useEffect } from 'react';
import {
  PANTONE_SWATCHES,
  PANTONE_CATEGORIES,
  findPantoneSwatch,
  resolvePantoneSwatch,
  PantoneSwatch,
} from './pantonePaletteData';
import { Check, ShoppingBag, Sparkles } from 'lucide-react';

interface PantonePalettePickerProps {
  value: string;
  onChange: (paletteId: string) => void;
  branchName?: string;
}

export const PantonePalettePicker: React.FC<PantonePalettePickerProps> = ({
  value,
  onChange,
  branchName = 'Mi Restaurante',
}) => {
  const [selectedCategory, setSelectedCategory] = useState<string>('todos');

  // Identify currently selected swatch or fallback to 'orange' or custom hex
  const activeSwatch: PantoneSwatch = useMemo(() => {
    return resolvePantoneSwatch(value);
  }, [value]);

  const [hexInput, setHexInput] = useState<string>(activeSwatch.hex.toUpperCase());

  useEffect(() => {
    setHexInput(activeSwatch.hex.toUpperCase());
  }, [activeSwatch.hex]);

  const handleHexInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const rawVal = e.target.value.toUpperCase();
    setHexInput(rawVal);

    const clean = rawVal.trim();
    if (/^#?([0-9A-F]{3}|[0-9A-F]{6})$/i.test(clean)) {
      let normalized = clean.startsWith('#') ? clean : '#' + clean;
      if (normalized.length === 4) {
        normalized = '#' + normalized.slice(1).split('').map((c) => c + c).join('');
      }
      normalized = normalized.toLowerCase();
      const matched = findPantoneSwatch(normalized);
      onChange(matched ? matched.id : normalized);
    }
  };

  const handleHexInputBlur = () => {
    const clean = hexInput.trim();
    if (/^#?([0-9A-F]{3}|[0-9A-F]{6})$/i.test(clean)) {
      let normalized = clean.startsWith('#') ? clean : '#' + clean;
      if (normalized.length === 4) {
        normalized = '#' + normalized.slice(1).split('').map((c) => c + c).join('');
      }
      normalized = normalized.toLowerCase();
      const matched = findPantoneSwatch(normalized);
      onChange(matched ? matched.id : normalized);
      setHexInput(normalized.toUpperCase());
    } else {
      setHexInput(activeSwatch.hex.toUpperCase());
    }
  };

  const handleNativeColorChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newHex = e.target.value.toLowerCase();
    const matched = findPantoneSwatch(newHex);
    onChange(matched ? matched.id : newHex);
    setHexInput(newHex.toUpperCase());
  };

  // Filter swatches if category is not 'todos'
  const displayedSwatches = useMemo(() => {
    if (selectedCategory === 'todos') {
      return PANTONE_SWATCHES;
    }
    return PANTONE_SWATCHES.filter((s) => s.category === selectedCategory);
  }, [selectedCategory]);

  return (
    <div
      style={{
        backgroundColor: '#ffffff',
        borderRadius: 18,
        padding: 18,
        boxShadow: '0 2px 8px rgba(15, 23, 42, 0.06)',
        marginBottom: 16,
        border: '1px solid #f1f5f9',
      }}
    >
      {/* Title & Subtitle */}
      <div style={{ marginBottom: 14 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
          <h3
            style={{
              fontSize: '0.98rem',
              fontWeight: 800,
              margin: 0,
              color: '#0f172a',
              display: 'flex',
              alignItems: 'center',
              gap: 8,
            }}
          >
            <span>Carta Pantone® del Menú Digital</span>
            <span
              style={{
                fontSize: '0.7rem',
                fontWeight: 700,
                padding: '2px 8px',
                borderRadius: 9999,
                backgroundColor: '#f1f5f9',
                color: '#475569',
              }}
            >
              64 Colores
            </span>
          </h3>
        </div>
        <p style={{ fontSize: '0.8rem', color: '#64748b', margin: '4px 0 0', lineHeight: 1.4 }}>
          Selecciona el tono de marca para la aplicación web y menú digital de tus clientes.
        </p>
      </div>

      {/* Horizontal Category Pill Bar */}
      <div
        style={{
          display: 'flex',
          gap: 6,
          overflowX: 'auto',
          paddingBottom: 10,
          marginBottom: 14,
          scrollbarWidth: 'none',
          msOverflowStyle: 'none',
          WebkitOverflowScrolling: 'touch',
        }}
      >
        {PANTONE_CATEGORIES.map((cat) => {
          const isSelected = selectedCategory === cat.id;
          return (
            <button
              key={cat.id}
              type="button"
              onClick={() => setSelectedCategory(cat.id)}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 5,
                padding: '6px 12px',
                borderRadius: 9999,
                fontSize: '0.76rem',
                fontWeight: isSelected ? 700 : 500,
                border: isSelected ? '1.5px solid #0f172a' : '1px solid #e2e8f0',
                backgroundColor: isSelected ? '#0f172a' : '#f8fafc',
                color: isSelected ? '#ffffff' : '#334155',
                cursor: 'pointer',
                whiteSpace: 'nowrap',
                transition: 'all 0.15s ease',
                flexShrink: 0,
              }}
            >
              <span>{cat.icon}</span>
              <span>{cat.label}</span>
            </button>
          );
        })}
      </div>

      {/* Pantone Matrix Grid */}
      <div style={{ marginBottom: 18 }}>
        {selectedCategory === 'todos' ? (
          <div>
            {/* Column Category Indicators */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(8, 1fr)',
                gap: 4,
                marginBottom: 6,
                textAlign: 'center',
              }}
            >
              {['✨', '🔥', '🍷', '🌊', '💎', '🌿', '🍋', '☕'].map((icon, idx) => (
                <div
                  key={idx}
                  style={{
                    fontSize: '0.75rem',
                    color: '#64748b',
                    padding: '2px 0',
                    userSelect: 'none',
                  }}
                  title={PANTONE_CATEGORIES[idx + 1]?.label}
                >
                  {icon}
                </div>
              ))}
            </div>

            {/* 8x8 Grid matching the user's reference image */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(8, 1fr)',
                gap: 5,
                background: '#f8fafc',
                padding: 8,
                borderRadius: 14,
                border: '1px solid #e2e8f0',
              }}
            >
              {PANTONE_SWATCHES.map((swatch) => {
                const isSelected = activeSwatch.id === swatch.id || activeSwatch.hex.toLowerCase() === swatch.hex.toLowerCase();
                return (
                  <button
                    key={swatch.id}
                    type="button"
                    onClick={() => onChange(swatch.id)}
                    title={`${swatch.name} (${swatch.hex.toUpperCase()})`}
                    aria-label={`Seleccionar color ${swatch.name} ${swatch.hex}`}
                    style={{
                      aspectRatio: '1 / 1',
                      width: '100%',
                      backgroundColor: swatch.hex,
                      border: isSelected
                        ? '2px solid #ffffff'
                        : '1px solid rgba(0, 0, 0, 0.08)',
                      borderRadius: 8,
                      cursor: 'pointer',
                      position: 'relative',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      padding: 0,
                      outline: isSelected ? '2px solid #0f172a' : 'none',
                      outlineOffset: 1,
                      boxShadow: isSelected ? '0 2px 8px rgba(15, 23, 42, 0.3)' : 'none',
                      transform: isSelected ? 'scale(1.08)' : 'scale(1)',
                      zIndex: isSelected ? 2 : 1,
                      transition: 'transform 0.15s ease, box-shadow 0.15s ease',
                    }}
                  >
                    {isSelected && (
                      <Check
                        size={14}
                        strokeWidth={3.5}
                        color={swatch.contrast}
                        style={{ filter: 'drop-shadow(0 1px 2px rgba(0,0,0,0.4))' }}
                      />
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        ) : (
          /* Filtered Category Grid */
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(2, 1fr)',
              gap: 8,
              background: '#f8fafc',
              padding: 8,
              borderRadius: 14,
              border: '1px solid #e2e8f0',
            }}
          >
            {displayedSwatches.map((swatch) => {
              const isSelected = activeSwatch.id === swatch.id || activeSwatch.hex.toLowerCase() === swatch.hex.toLowerCase();
              return (
                <button
                  key={swatch.id}
                  type="button"
                  onClick={() => onChange(swatch.id)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 10,
                    padding: 8,
                    borderRadius: 10,
                    backgroundColor: isSelected ? '#ffffff' : '#f8fafc',
                    border: isSelected ? '2px solid #0f172a' : '1px solid #e2e8f0',
                    cursor: 'pointer',
                    textAlign: 'left',
                    transition: 'all 0.15s ease',
                  }}
                >
                  <div
                    style={{
                      width: 32,
                      height: 32,
                      borderRadius: 8,
                      backgroundColor: swatch.hex,
                      flexShrink: 0,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      border: '1px solid rgba(0,0,0,0.1)',
                    }}
                  >
                    {isSelected && <Check size={14} strokeWidth={3} color={swatch.contrast} />}
                  </div>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ fontSize: '0.82rem', fontWeight: isSelected ? 800 : 600, color: '#0f172a', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {swatch.name}
                    </div>
                    <div style={{ fontSize: '0.72rem', color: '#64748b', fontFamily: 'monospace' }}>
                      {swatch.hex.toUpperCase()}
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* Featured Pantone Chip Card */}
      <div
        style={{
          border: '1px solid #e2e8f0',
          borderRadius: 14,
          overflow: 'hidden',
          backgroundColor: '#ffffff',
          boxShadow: '0 4px 14px rgba(15, 23, 42, 0.05)',
          marginBottom: 16,
        }}
      >
        {/* Upper Color Block */}
        <div
          style={{
            height: 64,
            backgroundColor: activeSwatch.hex,
            display: 'flex',
            alignItems: 'flex-start',
            justifyContent: 'flex-end',
            padding: 8,
            transition: 'background-color 0.25s ease',
          }}
        >
          <span
            style={{
              fontSize: '0.68rem',
              fontWeight: 800,
              backgroundColor: activeSwatch.contrast === '#ffffff' ? 'rgba(0,0,0,0.25)' : 'rgba(255,255,255,0.7)',
              color: activeSwatch.contrast,
              padding: '2px 8px',
              borderRadius: 6,
              backdropFilter: 'blur(4px)',
            }}
          >
            {activeSwatch.categoryLabel}
          </span>
        </div>

        {/* Lower Info Zone */}
        <div style={{ padding: '12px 14px' }}>
          <div
            style={{
              fontSize: '0.68rem',
              fontWeight: 800,
              letterSpacing: '0.08em',
              color: '#94a3b8',
              textTransform: 'uppercase',
              marginBottom: 2,
            }}
          >
            PANTONE® RESTAURANTOS
          </div>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 8,
              marginBottom: 6,
            }}
          >
            <div style={{ fontSize: '1.05rem', fontWeight: 800, color: '#0f172a' }}>
              {activeSwatch.name}
            </div>

            {/* Editable Hex Code & Visual Picker */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                backgroundColor: '#f1f5f9',
                padding: '3px 8px',
                borderRadius: 8,
                border: '1px solid #cbd5e1',
                boxShadow: 'inset 0 1px 2px rgba(0, 0, 0, 0.04)',
              }}
            >
              <label
                style={{
                  position: 'relative',
                  width: 20,
                  height: 20,
                  borderRadius: 6,
                  backgroundColor: activeSwatch.hex,
                  border: '1px solid rgba(0, 0, 0, 0.15)',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                  overflow: 'hidden',
                }}
                title="Toca para seleccionar un color visualmente"
              >
                <input
                  type="color"
                  value={activeSwatch.hex.length === 7 ? activeSwatch.hex : '#ea580c'}
                  onChange={handleNativeColorChange}
                  aria-label="Selector visual de color"
                  style={{
                    position: 'absolute',
                    top: -10,
                    left: -10,
                    width: 40,
                    height: 40,
                    opacity: 0,
                    cursor: 'pointer',
                  }}
                />
              </label>

              <input
                type="text"
                value={hexInput}
                onChange={handleHexInputChange}
                onBlur={handleHexInputBlur}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    (e.target as HTMLInputElement).blur();
                  }
                }}
                maxLength={7}
                placeholder="#HEX"
                aria-label="Código de color hexadecimal"
                title="Escribe o edita el código hexadecimal preciso"
                style={{
                  fontFamily: 'monospace',
                  fontSize: '0.82rem',
                  fontWeight: 800,
                  color: '#0f172a',
                  backgroundColor: 'transparent',
                  border: 'none',
                  outline: 'none',
                  width: 74,
                  padding: 0,
                  textTransform: 'uppercase',
                }}
              />
            </div>
          </div>
          <div style={{ fontSize: '0.75rem', color: '#64748b', lineHeight: 1.35 }}>
            <span style={{ fontWeight: 600, color: '#475569' }}>Ideal para: </span>
            {activeSwatch.recommendedFor}
          </div>
        </div>
      </div>

      {/* Live Digital Menu Simulator Mini-Card */}
      <div
        style={{
          border: '1px solid #e2e8f0',
          borderRadius: 14,
          backgroundColor: '#fafaf9',
          padding: 12,
        }}
      >
        <div
          style={{
            fontSize: '0.72rem',
            fontWeight: 700,
            color: '#64748b',
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
            marginBottom: 8,
            display: 'flex',
            alignItems: 'center',
            gap: 5,
          }}
        >
          <Sparkles size={13} color="#0f172a" />
          <span>Vista Previa del Menú Móvil</span>
        </div>

        {/* Mini App Mockup */}
        <div
          style={{
            backgroundColor: '#ffffff',
            borderRadius: 12,
            border: '1px solid #e2e8f0',
            padding: 10,
            boxShadow: '0 2px 6px rgba(0,0,0,0.04)',
          }}
        >
          {/* Mini Header */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              paddingBottom: 8,
              borderBottom: '1px solid #f1f5f9',
              marginBottom: 8,
            }}
          >
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: '0.65rem', color: '#94a3b8', fontWeight: 500 }}>Bienvenido a</div>
              <div
                style={{
                  fontSize: '0.82rem',
                  fontWeight: 800,
                  color: '#0f172a',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  maxWidth: 160,
                }}
              >
                {branchName}
              </div>
            </div>

            {/* Mini Cart with active brand badge */}
            <div
              style={{
                width: 32,
                height: 32,
                borderRadius: 10,
                border: '1px solid #e2e8f0',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                position: 'relative',
                backgroundColor: '#ffffff',
              }}
            >
              <ShoppingBag size={14} color="#334155" />
              <span
                style={{
                  position: 'absolute',
                  top: -4,
                  right: -4,
                  backgroundColor: activeSwatch.hex,
                  color: activeSwatch.contrast,
                  fontSize: '0.6rem',
                  fontWeight: 800,
                  width: 15,
                  height: 15,
                  borderRadius: 9999,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                2
              </span>
            </div>
          </div>

          {/* Mini Category Chips */}
          <div style={{ display: 'flex', gap: 6, marginBottom: 8 }}>
            <div
              style={{
                padding: '3px 8px',
                borderRadius: 9999,
                backgroundColor: activeSwatch.hex,
                color: activeSwatch.contrast,
                fontSize: '0.68rem',
                fontWeight: 700,
              }}
            >
              🔥 Especialidades
            </div>
            <div
              style={{
                padding: '3px 8px',
                borderRadius: 9999,
                backgroundColor: '#f1f5f9',
                color: '#64748b',
                fontSize: '0.68rem',
                fontWeight: 500,
              }}
            >
              Bebidas
            </div>
            <div
              style={{
                padding: '3px 8px',
                borderRadius: 9999,
                backgroundColor: '#f1f5f9',
                color: '#64748b',
                fontSize: '0.68rem',
                fontWeight: 500,
              }}
            >
              Postres
            </div>
          </div>

          {/* Mini Product Card */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              backgroundColor: '#f8fafc',
              padding: 8,
              borderRadius: 8,
              border: '1px solid #f1f5f9',
            }}
          >
            <div>
              <div style={{ fontSize: '0.76rem', fontWeight: 700, color: '#0f172a' }}>Orden Especial</div>
              <div style={{ fontSize: '0.7rem', fontWeight: 800, color: '#475569' }}>$120.00 MXN</div>
            </div>
            <div
              style={{
                backgroundColor: activeSwatch.hex,
                color: activeSwatch.contrast,
                fontSize: '0.68rem',
                fontWeight: 700,
                padding: '4px 10px',
                borderRadius: 6,
                boxShadow: `0 2px 6px ${activeSwatch.hex}33`,
              }}
            >
              + Agregar
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
