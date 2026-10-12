import React, { useCallback, useEffect, useState } from 'react';
import { ApiError, fetchApi, formatOrderCode, formatOrderModifier } from '@restaurantos/api-client';
import { Badge, Button } from '@restaurantos/ui';
import {
  AlertTriangle,
  ChefHat,
  CheckCircle,
  Clock,
  Play,
  RefreshCcw,
  Bike,
  ShoppingBag,
  Share2,
  Utensils,
  User,
  AlertCircle,
  Tag,
} from 'lucide-react';

type TaskStatus = 'PENDING' | 'IN_PROGRESS' | 'COMPLETED';

interface KdsTask {
  id: string;
  order_id: string;
  folio: string;
  product_name: string;
  quantity: number;
  station: string;
  status: TaskStatus;
  created_at: string;
  channel?: string;
  service_type?: string;
  customer_snapshot?: { name?: string; phone?: string };
  selected_modifiers?: unknown[] | Record<string, unknown>;
  line_notes?: string;
}

interface KdsSession {
  permissions: string[];
  active_branch: { id: string; name: string } | null;
}

type ViewState = 'loading' | 'ready' | 'denied' | 'error';

const columns: Array<{
  status: TaskStatus;
  title: string;
  empty: string;
  icon: React.ReactNode;
  tone: 'pending' | 'progress' | 'ready';
  actionLabel?: string;
  actionIcon?: React.ReactNode;
}> = [
  {
    status: 'PENDING',
    title: 'Pendiente',
    empty: 'No hay pedidos esperando preparación.',
    icon: <Clock size={20} />,
    tone: 'pending',
    actionLabel: 'Iniciar Preparación',
    actionIcon: <Play size={16} />,
  },
  {
    status: 'IN_PROGRESS',
    title: 'En Preparación',
    empty: 'No hay pedidos preparándose en este momento.',
    icon: <ChefHat size={20} />,
    tone: 'progress',
    actionLabel: 'Marcar Listo',
    actionIcon: <CheckCircle size={16} />,
  },
  {
    status: 'COMPLETED',
    title: 'Listo para Servir / Entregar',
    empty: 'Todavía no hay comandas terminadas.',
    icon: <CheckCircle size={20} />,
    tone: 'ready',
  },
];

const getElapsedMinutes = (createdAt: string) => {
  const timestamp = Date.parse(createdAt);
  if (!Number.isFinite(timestamp)) return 0;
  return Math.max(0, Math.floor((Date.now() - timestamp) / 60_000));
};

const getElapsedBadge = (createdAt: string) => {
  const minutes = getElapsedMinutes(createdAt);
  if (minutes < 1) {
    return <span className="kds-time-pill kds-time-now">Ahora</span>;
  }
  if (minutes > 30) {
    return (
      <span className="kds-time-pill kds-time-danger">
        <Clock size={12} /> Hace {minutes} min
      </span>
    );
  }
  if (minutes > 15) {
    return (
      <span className="kds-time-pill kds-time-warning">
        <Clock size={12} /> Hace {minutes} min
      </span>
    );
  }
  return (
    <span className="kds-time-pill kds-time-normal">
      <Clock size={12} /> Hace {minutes} min
    </span>
  );
};

const getChannelBadge = (channel?: string) => {
  const ch = (channel || 'LOCAL').toUpperCase();
  if (ch.includes('UBER')) {
    return (
      <span className="kds-channel-badge kds-channel-uber">
        <Share2 size={12} /> Uber Eats
      </span>
    );
  }
  if (ch.includes('DIDI')) {
    return (
      <span className="kds-channel-badge kds-channel-didi">
        <Bike size={12} /> DiDi Food
      </span>
    );
  }
  if (ch.includes('RAPPI')) {
    return (
      <span className="kds-channel-badge kds-channel-rappi">
        <ShoppingBag size={12} /> Rappi
      </span>
    );
  }
  if (ch.includes('WEB') || ch.includes('INTENT')) {
    return (
      <span className="kds-channel-badge kds-channel-web">
        <Tag size={12} /> Pedido Web
      </span>
    );
  }
  return (
    <span className="kds-channel-badge kds-channel-local">
      <Utensils size={12} /> Local / Mesa
    </span>
  );
};

const getServiceTypeLabel = (serviceType?: string) => {
  switch (serviceType?.toUpperCase()) {
    case 'DINE_IN':
    case 'LOCAL':
      return 'En Sucursal';
    case 'TAKEAWAY':
    case 'TAKE_OUT':
      return 'Para Llevar';
    case 'DELIVERY':
      return 'A Domicilio';
    default:
      return serviceType || '';
  }
};

const KitchenBoard = () => {
  const [tasks, setTasks] = useState<KdsTask[]>([]);
  const [branch, setBranch] = useState<KdsSession['active_branch']>(null);
  const [viewState, setViewState] = useState<ViewState>('loading');
  const [error, setError] = useState('');
  const [transitioning, setTransitioning] = useState<string | null>(null);

  const loadTasks = useCallback(async (branchId: string) => {
    try {
      const result = await fetchApi<KdsTask[]>(
        `/kds/tasks?branch_id=${encodeURIComponent(branchId)}`,
      );
      setTasks(Array.isArray(result) ? result : []);
      setViewState('ready');
      setError('');
    } catch (reason) {
      setViewState(reason instanceof ApiError && reason.status === 403 ? 'denied' : 'error');
      setError(reason instanceof ApiError ? reason.message : 'No fue posible consultar cocina.');
    }
  }, []);

  useEffect(() => {
    let active = true;
    const bootstrap = async () => {
      try {
        const session = await fetchApi<KdsSession>('/auth/session');
        if (!active) return;
        if (!session.permissions.includes('kds.tasks.operate')) {
          setViewState('denied');
          setError('Tu usuario no tiene permiso para operar KDS.');
          return;
        }
        if (!session.active_branch) {
          setViewState('error');
          setError('Selecciona una sucursal autorizada antes de abrir KDS.');
          return;
        }
        setBranch(session.active_branch);
        await loadTasks(session.active_branch.id);
      } catch (reason) {
        if (!active) return;
        setViewState(reason instanceof ApiError && reason.status === 403 ? 'denied' : 'error');
        setError(
          reason instanceof ApiError && reason.status === 401
            ? 'Inicia sesión para abrir KDS.'
            : reason instanceof ApiError
              ? reason.message
              : 'No fue posible validar la sesión.',
        );
      }
    };
    void bootstrap();
    return () => {
      active = false;
    };
  }, [loadTasks]);

  useEffect(() => {
    if (!branch) return undefined;
    const interval = window.setInterval(() => {
      void loadTasks(branch.id);
    }, 5_000);
    return () => window.clearInterval(interval);
  }, [branch, loadTasks]);

  const transitionTask = async (task: KdsTask) => {
    const nextStatus = task.status === 'PENDING' ? 'IN_PROGRESS' : 'COMPLETED';
    setTransitioning(task.id);
    setError('');
    try {
      await fetchApi(`/kds/tasks/${encodeURIComponent(task.id)}/transition`, {
        method: 'POST',
        body: JSON.stringify({ status: nextStatus, branch_id: branch?.id }),
      });
      if (branch) await loadTasks(branch.id);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : 'No fue posible actualizar la tarea.');
    } finally {
      setTransitioning(null);
    }
  };

  return (
    <main className="kds-layout" aria-busy={viewState === 'loading'}>
      {/* KDS Header */}
      <header className="kds-header">
        <div className="kds-brand">
          <ChefHat size={30} className="kds-brand-icon" />
          <div>
            <strong>Sistema KDS de Cocina</strong>
            <span className="kds-brand-sub">Control en tiempo real</span>
          </div>
        </div>
        <div className="kds-header-context">
          <Badge variant="info">{branch?.name || 'Sin sucursal'}</Badge>
          {branch && (
            <Button size="sm" variant="secondary" onClick={() => void loadTasks(branch.id)}>
              <RefreshCcw size={15} /> Actualizar
            </Button>
          )}
        </div>
      </header>

      {viewState !== 'ready' ? (
        <section className="kds-state" role={viewState === 'error' ? 'alert' : 'status'}>
          {viewState === 'loading' ? <RefreshCcw className="kds-spin" size={38} /> : <AlertTriangle size={38} />}
          <strong>{viewState === 'loading' ? 'Cargando comanda de cocina…' : error}</strong>
        </section>
      ) : (
        <>
          {error && <p className="kds-inline-error" role="alert">{error}</p>}
          <section className="kds-board" aria-label="Tareas de producción">
            {columns.map((column) => {
              const columnTasks = tasks.filter((task) => task.status === column.status);
              return (
                <div key={column.status} className={`kds-column ${column.tone}`}>
                  {/* Column Header */}
                  <div className="kds-column-header">
                    <div className="kds-column-title">
                      {column.icon}
                      {column.title}
                    </div>
                    <div className="kds-column-count">{columnTasks.length}</div>
                  </div>

                  {/* Scrollable Column Cards Container */}
                  <div className="kds-column-cards">
                    {columnTasks.length === 0 ? (
                      <div className="kds-empty">
                        <Utensils size={36} style={{ opacity: 0.35, margin: '0 auto 10px' }} />
                        <p>{column.empty}</p>
                      </div>
                    ) : (
                      columnTasks.map((task) => {
                        const clientName = task.customer_snapshot?.name || '';
                        const serviceType = getServiceTypeLabel(task.service_type);
                        const modifiers = Array.isArray(task.selected_modifiers)
                          ? task.selected_modifiers
                          : typeof task.selected_modifiers === 'object' && task.selected_modifiers !== null
                          ? Object.values(task.selected_modifiers)
                          : [];

                        return (
                          <div key={task.id} className="kds-order-card">
                            <div className="kds-card-header">
                              <div className="kds-card-folio-group">
                                <span className="kds-folio-badge">{formatOrderCode(task.folio)}</span>
                                {getChannelBadge(task.channel)}
                              </div>
                              {getElapsedBadge(task.created_at)}
                            </div>

                            {/* Client & Service Info */}
                            {(clientName || serviceType) && (
                              <div className="kds-card-meta">
                                {clientName && (
                                  <div className="kds-meta-item">
                                    <User size={13} />
                                    <span>{clientName}</span>
                                  </div>
                                )}
                                {serviceType && (
                                  <span className="kds-service-tag">{serviceType}</span>
                                )}
                              </div>
                            )}

                            {/* Product & Quantity */}
                            <div className="kds-product-section">
                              <div className="kds-product-main">
                                <span className="kds-qty-badge">{task.quantity}×</span>
                                <span className="kds-product-name">{task.product_name}</span>
                              </div>
                              {task.station && (
                                <span className="kds-station-tag">{task.station}</span>
                              )}
                            </div>

                            {/* Modifiers / Extras */}
                            {modifiers.length > 0 && (
                              <div className="kds-modifiers-list">
                                {modifiers.map((mod, mIdx) => {
                                  const presentation = formatOrderModifier(mod);
                                  return (
                                    <span key={mIdx} className="kds-modifier-tag">
                                      {presentation.label}
                                    </span>
                                  );
                                })}
                              </div>
                            )}

                            {/* Line Notes (Kitchen Attention) */}
                            {task.line_notes && (
                              <div className="kds-notes-box">
                                <AlertCircle size={14} />
                                <span>Nota: {task.line_notes}</span>
                              </div>
                            )}

                            {/* Card Footer Actions */}
                            {task.status !== 'COMPLETED' && (
                              <div className="kds-card-footer">
                                <button
                                  type="button"
                                  className={`kds-action-btn ${task.status === 'PENDING' ? 'kds-btn-start' : 'kds-btn-done'}`}
                                  disabled={transitioning === task.id}
                                  onClick={() => void transitionTask(task)}
                                >
                                  {transitioning === task.id ? (
                                    <RefreshCcw size={16} className="kds-spin" />
                                  ) : (
                                    column.actionIcon
                                  )}
                                  <span>
                                    {transitioning === task.id
                                      ? 'Guardando…'
                                      : column.actionLabel}
                                  </span>
                                </button>
                              </div>
                            )}
                          </div>
                        );
                      })
                    )}
                  </div>
                </div>
              );
            })}
          </section>
        </>
      )}
    </main>
  );
};

export default KitchenBoard;
