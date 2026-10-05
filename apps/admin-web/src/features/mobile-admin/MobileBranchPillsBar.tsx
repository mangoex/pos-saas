import React, { useRef, useEffect } from 'react';
import { Store, MapPin, CheckCircle2, Circle, Plus } from 'lucide-react';

export interface MobileBranchItem {
  id: string;
  name: string;
  code?: string;
  status?: string;
}

export type ShiftState = 'open' | 'closed' | 'unknown';

interface MobileBranchPillsBarProps {
  branches: MobileBranchItem[];
  selectedBranchId: string;
  onSelectBranch: (branchId: string) => void;
  branchShiftStatus?: Record<string, ShiftState>;
  onAddBranch?: () => void;
}

export const MobileBranchPillsBar: React.FC<MobileBranchPillsBarProps> = ({
  branches,
  selectedBranchId,
  onSelectBranch,
  branchShiftStatus = {},
  onAddBranch,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);

  // Auto-scroll active pill into view smoothly
  useEffect(() => {
    if (!containerRef.current) return;
    const activeEl = containerRef.current.querySelector<HTMLElement>('.branch-pill-item.active');
    if (activeEl) {
      activeEl.scrollIntoView({
        behavior: 'smooth',
        inline: 'center',
        block: 'nearest',
      });
    }
  }, [selectedBranchId]);

  // If there are no branches or only 1, still render clean context but without clutter
  const isAllSelected = selectedBranchId === 'all';

  return (
    <nav
      aria-label="Selector de sucursales móvil"
      style={{
        width: '100%',
        backgroundColor: '#ffffff',
        borderBottom: '1px solid #e2e8f0',
        padding: '10px 16px',
        boxSizing: 'border-box',
        overflow: 'hidden',
        position: 'sticky',
        top: 0,
        zIndex: 35,
        boxShadow: '0 2px 8px rgba(0, 0, 0, 0.03)',
      }}
    >
      <div
        ref={containerRef}
        className="mobile-branch-pills-scroll"
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          overflowX: 'auto',
          WebkitOverflowScrolling: 'touch',
          scrollbarWidth: 'none',
          msOverflowStyle: 'none',
          paddingBottom: 2,
        }}
      >
        {/* Pill 1: Todas las sucursales */}
        <button
          type="button"
          onClick={() => onSelectBranch('all')}
          className={`branch-pill-item ${isAllSelected ? 'active' : ''}`}
          aria-pressed={isAllSelected}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            padding: '7px 14px',
            borderRadius: 9999,
            fontSize: '0.8125rem',
            fontWeight: isAllSelected ? 800 : 600,
            color: isAllSelected ? '#ffffff' : '#334155',
            backgroundColor: isAllSelected ? '#0f172a' : '#f1f5f9',
            border: isAllSelected ? '1px solid #0f172a' : '1px solid #e2e8f0',
            cursor: 'pointer',
            whiteSpace: 'nowrap',
            flexShrink: 0,
            transition: 'all 0.15s ease',
            boxShadow: isAllSelected ? '0 2px 6px rgba(15, 23, 42, 0.25)' : 'none',
          }}
        >
          <Store size={14} color={isAllSelected ? '#ffffff' : '#64748b'} />
          <span>Todas las sucursales</span>
          {branches.length > 0 && (
            <span
              style={{
                fontSize: '0.7rem',
                padding: '1px 6px',
                borderRadius: 9999,
                backgroundColor: isAllSelected ? 'rgba(255, 255, 255, 0.25)' : '#e2e8f0',
                color: isAllSelected ? '#ffffff' : '#475569',
                fontWeight: 700,
              }}
            >
              {branches.length}
            </span>
          )}
        </button>

        {/* Individual Branch Pills */}
        {branches.map((branch) => {
          const isSelected = selectedBranchId === branch.id;
          const shiftState = branchShiftStatus[branch.id] || 'unknown';
          const isOpen = shiftState === 'open';

          return (
            <button
              key={branch.id}
              type="button"
              onClick={() => onSelectBranch(branch.id)}
              className={`branch-pill-item ${isSelected ? 'active' : ''}`}
              aria-pressed={isSelected}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                padding: '7px 14px',
                borderRadius: 9999,
                fontSize: '0.8125rem',
                fontWeight: isSelected ? 800 : 600,
                color: isSelected ? '#ffffff' : '#334155',
                backgroundColor: isSelected ? '#ff5722' : '#f8fafc',
                border: isSelected ? '1px solid #ff5722' : '1px solid #cbd5e1',
                cursor: 'pointer',
                whiteSpace: 'nowrap',
                flexShrink: 0,
                transition: 'all 0.15s ease',
                boxShadow: isSelected ? '0 2px 6px rgba(255, 87, 34, 0.3)' : 'none',
              }}
            >
              <MapPin size={13} color={isSelected ? '#ffffff' : '#94a3b8'} />
              <span>{branch.name}</span>

              {/* Status indicator: 🟢 Open / ⚪ Closed */}
              {shiftState !== 'unknown' && (
                <span
                  title={isOpen ? 'Caja abierta con turno activo' : 'Caja cerrada'}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 3,
                    fontSize: '0.65rem',
                    fontWeight: 700,
                    padding: '1px 5px',
                    borderRadius: 9999,
                    backgroundColor: isSelected
                      ? 'rgba(255, 255, 255, 0.25)'
                      : (isOpen ? '#dcfce7' : '#f1f5f9'),
                    color: isSelected
                      ? '#ffffff'
                      : (isOpen ? '#166534' : '#64748b'),
                  }}
                >
                  <span
                    style={{
                      width: 6,
                      height: 6,
                      borderRadius: '50%',
                      backgroundColor: isSelected
                        ? (isOpen ? '#86efac' : '#e2e8f0')
                        : (isOpen ? '#22c55e' : '#94a3b8'),
                    }}
                  />
                  <span>{isOpen ? 'Caja' : 'Cerrada'}</span>
                </span>
              )}
            </button>
          );
        })}

        {/* Action Pill: + Nueva Sucursal */}
        {onAddBranch && (
          <button
            type="button"
            onClick={onAddBranch}
            className="branch-pill-item add-branch-pill"
            aria-label="Agregar nueva sucursal"
            title="Agregar nueva sucursal"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 4,
              padding: '7px 12px',
              borderRadius: 9999,
              fontSize: '0.8125rem',
              fontWeight: 700,
              color: '#0284c7',
              backgroundColor: '#f0f9ff',
              border: '1.5px dashed #38bdf8',
              cursor: 'pointer',
              whiteSpace: 'nowrap',
              flexShrink: 0,
              transition: 'all 0.15s ease',
            }}
          >
            <Plus size={14} color="#0284c7" strokeWidth={2.5} />
            <span>+ Nueva</span>
          </button>
        )}
      </div>
    </nav>
  );
};
