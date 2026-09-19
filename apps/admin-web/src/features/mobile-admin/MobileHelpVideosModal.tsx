import React, { useState } from 'react';
import {
  X,
  Play,
  PlaySquare,
  Sparkles,
  ChevronLeft,
  ChevronRight,
  HelpCircle,
  ExternalLink,
} from 'lucide-react';

export interface TutorialVideo {
  id: string;
  title: string;
  category: string;
  categoryColor: string;
  youtubeId: string;
  durationApprox: string;
  description: string;
}

export const TUTORIAL_VIDEOS: TutorialVideo[] = [
  {
    id: 'config-nombre',
    title: 'Configurando el Nombre',
    category: 'Sucursal',
    categoryColor: '#8b5cf6',
    youtubeId: 'PpdcuCMAfPg',
    durationApprox: '30s',
    description: 'Aprende a personalizar el nombre, logo y enlace público de tu restaurante.',
  },
  {
    id: 'edit-productos',
    title: 'Editando Productos',
    category: 'Catálogo',
    categoryColor: '#3b82f6',
    youtubeId: 'alaNrdtrP3k',
    durationApprox: '45s',
    description: 'Cambia precios, nombres, descripciones y fotos de tus platillos al instante.',
  },
  {
    id: 'crear-menu',
    title: 'Creando el Menú',
    category: 'Menú',
    categoryColor: '#10b981',
    youtubeId: 'odb00yMa6Nk',
    durationApprox: '40s',
    description: 'Estructura tu menú digital para que tus comensales ordenen con rapidez.',
  },
  {
    id: 'envio-domicilio',
    title: 'Envío a Domicilio',
    category: 'Entregas',
    categoryColor: '#f97316',
    youtubeId: 'qCWxvZHO_og',
    durationApprox: '35s',
    description: 'Configura tarifas de entrega por distancia y monto mínimo para envío gratis.',
  },
  {
    id: 'cupones-descuento',
    title: 'Cupones de Descuento',
    category: 'Marketing',
    categoryColor: '#ec4899',
    youtubeId: 'htqLte7J7pU',
    durationApprox: '30s',
    description: 'Crea códigos de descuento atractivos para fidelizar y conseguir recompras.',
  },
  {
    id: 'edit-categorias',
    title: 'Editando Categorías',
    category: 'Catálogo',
    categoryColor: '#6366f1',
    youtubeId: '5J94AFGaC9U',
    durationApprox: '30s',
    description: 'Organiza tus secciones: entradas, platos fuertes, bebidas y postres.',
  },
  {
    id: 'aceptar-pedidos',
    title: 'Aceptando Pedidos',
    category: 'Pedidos',
    categoryColor: '#0284c7',
    youtubeId: 't0255cZ6n_Y',
    durationApprox: '40s',
    description: 'Cómo recibir, confirmar y pasar a cocina las comandas entrantes en tiempo real.',
  },
  {
    id: 'portada-voz',
    title: 'Portada y Pedidos por Voz',
    category: 'Storefront',
    categoryColor: '#eab308',
    youtubeId: 'PQQQFGwhA9k',
    durationApprox: '45s',
    description: 'Configura la foto de portada y la experiencia de dictado por voz para clientes.',
  },
];

interface MobileHelpVideosModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialVideoId?: string;
}

export const MobileHelpVideosModal: React.FC<MobileHelpVideosModalProps> = ({
  isOpen,
  onClose,
  initialVideoId,
}) => {
  const [selectedVideoId, setSelectedVideoId] = useState<string | null>(
    initialVideoId || null
  );

  if (!isOpen) return null;

  const currentVideo =
    TUTORIAL_VIDEOS.find((v) => v.id === selectedVideoId) || null;
  const currentIndex = currentVideo
    ? TUTORIAL_VIDEOS.findIndex((v) => v.id === currentVideo.id)
    : -1;

  const handlePrev = () => {
    if (currentIndex > 0) {
      setSelectedVideoId(TUTORIAL_VIDEOS[currentIndex - 1].id);
    }
  };

  const handleNext = () => {
    if (currentIndex < TUTORIAL_VIDEOS.length - 1) {
      setSelectedVideoId(TUTORIAL_VIDEOS[currentIndex + 1].id);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Tutoriales y guías en video de RestaurantOS"
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 200,
        backgroundColor: 'rgba(2, 6, 23, 0.82)',
        backdropFilter: 'blur(8px)',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'flex-end',
        animation: 'fadeIn 0.2s ease-out',
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          onClose();
        }
      }}
    >
      <div
        style={{
          backgroundColor: '#0f172a',
          borderTopLeftRadius: 24,
          borderTopRightRadius: 24,
          borderTop: '1px solid #1e293b',
          maxHeight: '92vh',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          boxShadow: '0 -8px 30px rgba(0, 0, 0, 0.6)',
        }}
      >
        {/* Grab Handle */}
        <div
          style={{
            width: 42,
            height: 4,
            borderRadius: 9999,
            backgroundColor: '#334155',
            margin: '10px auto 4px',
          }}
        />

        {/* Modal Header */}
        <div
          style={{
            padding: '12px 18px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            borderBottom: '1px solid #1e293b',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div
              style={{
                width: 36,
                height: 36,
                borderRadius: 10,
                background: 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: '0 2px 8px rgba(245, 158, 11, 0.3)',
              }}
            >
              <PlaySquare size={20} color="#ffffff" />
            </div>
            <div>
              <div
                style={{
                  fontSize: '1rem',
                  fontWeight: 800,
                  color: '#ffffff',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                }}
              >
                Guías Rápidas en Video
                <span
                  style={{
                    backgroundColor: '#1e293b',
                    color: '#f59e0b',
                    fontSize: '0.65rem',
                    fontWeight: 800,
                    padding: '2px 6px',
                    borderRadius: 6,
                    border: '1px solid rgba(245, 158, 11, 0.3)',
                  }}
                >
                  8 videos
                </span>
              </div>
              <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
                Aprende en segundos cada función de tu restaurante
              </div>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            aria-label="Cerrar tutoriales"
            style={{
              width: 34,
              height: 34,
              borderRadius: 10,
              backgroundColor: '#1e293b',
              border: '1px solid #334155',
              color: '#94a3b8',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: 'pointer',
            }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Scrollable Content Area */}
        <div
          style={{
            overflowY: 'auto',
            padding: '16px 14px 24px',
            display: 'flex',
            flexDirection: 'column',
            gap: 16,
          }}
        >
          {/* Active Video Player View (if a video is chosen) */}
          {currentVideo && (
            <div
              style={{
                backgroundColor: '#020617',
                borderRadius: 18,
                overflow: 'hidden',
                border: '1px solid #1e293b',
                boxShadow: '0 8px 24px rgba(0, 0, 0, 0.4)',
              }}
            >
              {/* Responsive Video Container for Shorts / Reels (9:16 or 16:9 responsive) */}
              <div
                style={{
                  position: 'relative',
                  width: '100%',
                  aspectRatio: '9 / 16',
                  maxHeight: '440px',
                  backgroundColor: '#000000',
                  margin: '0 auto',
                  display: 'flex',
                  justifyContent: 'center',
                }}
              >
                <iframe
                  src={`https://www.youtube.com/embed/${currentVideo.youtubeId}?autoplay=1&rel=0&modestbranding=1&playsinline=1`}
                  title={currentVideo.title}
                  allow="accelerometer; autoplay; clipboard-write strict-origin-when-cross-origin; encrypted-media; gyroscope; picture-in-picture; web-share"
                  allowFullScreen
                  style={{
                    width: '100%',
                    height: '100%',
                    border: 'none',
                  }}
                />
              </div>

              {/* Video Info and Controls */}
              <div style={{ padding: '14px 16px' }}>
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    marginBottom: 6,
                  }}
                >
                  <span
                    style={{
                      backgroundColor: currentVideo.categoryColor,
                      color: '#ffffff',
                      fontSize: '0.7rem',
                      fontWeight: 800,
                      padding: '2px 8px',
                      borderRadius: 9999,
                      textTransform: 'uppercase',
                    }}
                  >
                    {currentVideo.category}
                  </span>
                  <span style={{ fontSize: '0.75rem', color: '#64748b' }}>
                    Video {currentIndex + 1} de {TUTORIAL_VIDEOS.length}
                  </span>
                </div>

                <div
                  style={{
                    fontSize: '1.05rem',
                    fontWeight: 800,
                    color: '#ffffff',
                    lineHeight: 1.2,
                    marginBottom: 4,
                  }}
                >
                  {currentVideo.title}
                </div>
                <div style={{ fontSize: '0.8rem', color: '#94a3b8', marginBottom: 12 }}>
                  {currentVideo.description}
                </div>

                {/* Prev / Next navigation */}
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: 10,
                    paddingTop: 10,
                    borderTop: '1px solid #1e293b',
                  }}
                >
                  <button
                    type="button"
                    onClick={handlePrev}
                    disabled={currentIndex === 0}
                    style={{
                      flex: 1,
                      padding: '8px 12px',
                      backgroundColor: currentIndex === 0 ? '#0f172a' : '#1e293b',
                      color: currentIndex === 0 ? '#475569' : '#e2e8f0',
                      border: '1px solid #334155',
                      borderRadius: 10,
                      fontSize: '0.8rem',
                      fontWeight: 700,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: 4,
                      cursor: currentIndex === 0 ? 'not-allowed' : 'pointer',
                    }}
                  >
                    <ChevronLeft size={16} /> Anterior
                  </button>

                  <a
                    href={`https://youtube.com/shorts/${currentVideo.youtubeId}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    title="Abrir en app de YouTube"
                    style={{
                      padding: '8px 10px',
                      backgroundColor: '#1e293b',
                      color: '#94a3b8',
                      border: '1px solid #334155',
                      borderRadius: 10,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      textDecoration: 'none',
                    }}
                  >
                    <ExternalLink size={16} />
                  </a>

                  <button
                    type="button"
                    onClick={handleNext}
                    disabled={currentIndex === TUTORIAL_VIDEOS.length - 1}
                    style={{
                      flex: 1,
                      padding: '8px 12px',
                      backgroundColor:
                        currentIndex === TUTORIAL_VIDEOS.length - 1 ? '#0f172a' : '#1e293b',
                      color:
                        currentIndex === TUTORIAL_VIDEOS.length - 1 ? '#475569' : '#e2e8f0',
                      border: '1px solid #334155',
                      borderRadius: 10,
                      fontSize: '0.8rem',
                      fontWeight: 700,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: 4,
                      cursor:
                        currentIndex === TUTORIAL_VIDEOS.length - 1
                          ? 'not-allowed'
                          : 'pointer',
                    }}
                  >
                    Siguiente <ChevronRight size={16} />
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Section Header */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginTop: currentVideo ? 4 : 0,
            }}
          >
            <div
              style={{
                fontSize: '0.85rem',
                fontWeight: 800,
                color: '#cbd5e1',
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
                display: 'flex',
                alignItems: 'center',
                gap: 6,
              }}
            >
              <Sparkles size={14} color="#f59e0b" />
              {currentVideo ? 'Más Guías Disponibles' : 'Explora los Tutoriales'}
            </div>
            <span style={{ fontSize: '0.72rem', color: '#64748b' }}>
              Desliza a los lados ↔
            </span>
          </div>

          {/* Horizontal Scroll-Snap Reels Carousel */}
          <div
            role="region"
            aria-label="Carrusel horizontal de guías rápidas"
            style={{
              display: 'flex',
              gap: 12,
              overflowX: 'auto',
              scrollSnapType: 'x mandatory',
              WebkitOverflowScrolling: 'touch',
              paddingBottom: 8,
              scrollbarWidth: 'none',
              msOverflowStyle: 'none',
            }}
          >
            {TUTORIAL_VIDEOS.map((video, idx) => {
              const isSelected = video.id === selectedVideoId;
              const thumbnailUrl = `https://img.youtube.com/vi/${video.youtubeId}/hqdefault.jpg`;

              return (
                <div
                  key={video.id}
                  onClick={() => setSelectedVideoId(video.id)}
                  style={{
                    scrollSnapAlign: 'start',
                    flex: '0 0 138px',
                    height: 216,
                    borderRadius: 16,
                    overflow: 'hidden',
                    position: 'relative',
                    cursor: 'pointer',
                    backgroundColor: '#1e293b',
                    border: isSelected
                      ? '2px solid #f59e0b'
                      : '1px solid rgba(255, 255, 255, 0.1)',
                    boxShadow: isSelected
                      ? '0 0 14px rgba(245, 158, 11, 0.4)'
                      : '0 4px 10px rgba(0, 0, 0, 0.3)',
                    transition: 'transform 0.15s ease, border-color 0.15s ease',
                  }}
                >
                  {/* YouTube Thumbnail Cover */}
                  <img
                    src={thumbnailUrl}
                    alt={video.title}
                    loading="lazy"
                    style={{
                      width: '100%',
                      height: '100%',
                      objectFit: 'cover',
                      display: 'block',
                    }}
                  />

                  {/* Dark Gradient Overlay for legibility */}
                  <div
                    style={{
                      position: 'absolute',
                      inset: 0,
                      background:
                        'linear-gradient(180deg, rgba(0, 0, 0, 0.35) 0%, rgba(0, 0, 0, 0.15) 35%, rgba(0, 0, 0, 0.92) 100%)',
                      display: 'flex',
                      flexDirection: 'column',
                      justifyContent: 'space-between',
                      padding: 10,
                    }}
                  >
                    {/* Top Row: Category badge & duration */}
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        gap: 4,
                      }}
                    >
                      <span
                        style={{
                          backgroundColor: video.categoryColor,
                          color: '#ffffff',
                          fontSize: '0.62rem',
                          fontWeight: 800,
                          padding: '2px 6px',
                          borderRadius: 6,
                          textTransform: 'uppercase',
                        }}
                      >
                        {video.category}
                      </span>
                      <span
                        style={{
                          backgroundColor: 'rgba(0,0,0,0.6)',
                          color: '#ffffff',
                          fontSize: '0.6rem',
                          fontWeight: 700,
                          padding: '2px 5px',
                          borderRadius: 4,
                        }}
                      >
                        {video.durationApprox}
                      </span>
                    </div>

                    {/* Center: Play Circle icon */}
                    <div
                      style={{
                        alignSelf: 'center',
                        width: 38,
                        height: 38,
                        borderRadius: 9999,
                        backgroundColor: isSelected
                          ? '#f59e0b'
                          : 'rgba(255, 255, 255, 0.85)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        boxShadow: '0 4px 10px rgba(0, 0, 0, 0.4)',
                      }}
                    >
                      <Play
                        size={18}
                        color={isSelected ? '#ffffff' : '#0f172a'}
                        fill={isSelected ? '#ffffff' : '#0f172a'}
                        style={{ marginLeft: 2 }}
                      />
                    </div>

                    {/* Bottom: Title & Index */}
                    <div>
                      <div
                        style={{
                          fontSize: '0.78rem',
                          fontWeight: 800,
                          color: '#ffffff',
                          lineHeight: 1.25,
                          textShadow: '0 1px 3px rgba(0,0,0,0.8)',
                          display: '-webkit-box',
                          WebkitLineClamp: 2,
                          WebkitBoxOrient: 'vertical',
                          overflow: 'hidden',
                        }}
                      >
                        {video.title}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Quick Help Footer Tip */}
          <div
            style={{
              backgroundColor: '#1e293b',
              borderRadius: 12,
              padding: '10px 14px',
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              border: '1px solid #334155',
            }}
          >
            <HelpCircle size={16} color="#38bdf8" />
            <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
              ¿Tienes dudas adicionales? Toca cualquier guía para ver el paso a paso en pantalla.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
