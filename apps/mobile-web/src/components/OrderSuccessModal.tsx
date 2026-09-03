import React, { useState } from 'react';
import { CheckCircle2, X, ShoppingBag, ArrowLeft, Clock, ChefHat, Star, Send, ExternalLink } from 'lucide-react';
import { CreatedOrderResult, BranchInfo } from '../types';
import { formatMoney, submitCustomerFeedback } from '../api';

interface OrderSuccessModalProps {
  orderResult: CreatedOrderResult;
  branch?: BranchInfo | null;
  onClose: () => void;
  onNewOrder: () => void;
}

export const OrderSuccessModal: React.FC<OrderSuccessModalProps> = ({
  orderResult,
  branch,
  onClose,
  onNewOrder,
}) => {
  const pendingReview = orderResult.kind === 'public_order_intent';
  const orderFolio = pendingReview ? orderResult.public_reference : orderResult.folio;

  // Smart Rating State
  const [rating, setRating] = useState<number | null>(null);
  const [hoveredRating, setHoveredRating] = useState<number | null>(null);
  const [privateComment, setPrivateComment] = useState('');
  const [isSubmittingFeedback, setIsSubmittingFeedback] = useState(false);
  const [feedbackSubmitted, setFeedbackSubmitted] = useState(false);

  const handleSelectRating = (selected: number) => {
    setRating(selected);
    if (selected >= 4 && branch?.id) {
      // Record positive feedback automatically
      submitCustomerFeedback({
        branch_id: branch.id,
        rating: selected,
        order_folio: orderFolio,
        customer_name: orderResult.customer_info.name,
        comment: 'Calificación 4-5 estrellas (Redirigido a Google Reviews)',
      });
    }
  };

  const handleSendPrivateFeedback = async () => {
    if (!branch?.id || !rating) return;
    setIsSubmittingFeedback(true);
    try {
      await submitCustomerFeedback({
        branch_id: branch.id,
        rating: rating,
        order_folio: orderFolio,
        customer_name: orderResult.customer_info.name,
        comment: privateComment.trim() || undefined,
      });
      setFeedbackSubmitted(true);
    } finally {
      setIsSubmittingFeedback(false);
    }
  };

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        background: 'rgba(15, 23, 42, 0.7)',
        backdropFilter: 'blur(8px)',
        WebkitBackdropFilter: 'blur(8px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '20px',
        animation: 'fadeIn 0.25s ease-out',
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: '#ffffff',
          borderRadius: '28px',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.35)',
          maxWidth: '440px',
          width: '100%',
          maxHeight: '90vh',
          overflowY: 'auto',
          position: 'relative',
          padding: '32px 24px 28px',
          boxSizing: 'border-box',
          animation: 'popIn 0.3s cubic-bezier(0.16, 1, 0.3, 1)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Top-Right Close Button */}
        <button
          type="button"
          onClick={onClose}
          aria-label="Cerrar"
          style={{
            position: 'absolute',
            top: '18px',
            right: '18px',
            width: '38px',
            height: '38px',
            borderRadius: '50%',
            background: '#f1f5f9',
            border: 'none',
            color: '#475569',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
            transition: 'all 0.2s ease',
            zIndex: 10,
          }}
        >
          <X size={20} />
        </button>

        <div className="success-modal" style={{ padding: 0 }}>
          <div className="success-icon-wrapper" style={{ marginTop: '8px' }}>
            <CheckCircle2 size={46} />
          </div>

          <h2 style={{ fontSize: '22px', fontWeight: 800, color: '#0f172a', margin: '8px 0 4px' }}>
            {pendingReview ? '¡Solicitud recibida!' : '¡Pedido Registrado y Enviado!'}
          </h2>

          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px', margin: '4px 0 8px' }}>
            <span style={{ fontSize: '13px', color: '#64748b', fontWeight: 600 }}>{pendingReview ? 'Referencia' : 'Folio de Orden'}</span>
            <span className="folio-chip">#{orderFolio}</span>
          </div>

          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              background: '#ecfdf5',
              border: '1px solid #a7f3d0',
              color: '#047857',
              padding: '6px 14px',
              borderRadius: '9999px',
              fontSize: '13px',
              fontWeight: 700,
              marginBottom: '10px',
            }}
          >
            {pendingReview ? <Clock size={16} /> : <ChefHat size={16} />}
            <span>{pendingReview ? 'Pendiente de revisión' : 'Enviado al Punto de Venta y Cocina'}</span>
          </div>

          <p style={{ fontSize: '14px', color: '#64748b', lineHeight: 1.5, maxWidth: '340px', margin: '0 auto 16px' }}>
            {pendingReview ? 'Tu solicitud ha quedado registrada (Aún no es un pedido operativo) y será revisada de inmediato en el mostrador del restaurante.' : 'Tu pedido ha quedado registrado en el sistema y enviado a la sucursal. ¡Estamos preparando tu orden!'}
          </p>

          {/* Order Details Card */}
          <div style={{ width: '100%', background: '#f8fafc', padding: '16px', borderRadius: '16px', border: '1px solid #e2e8f0', textAlign: 'left', display: 'flex', flexDirection: 'column', gap: '10px', marginBottom: '16px', boxSizing: 'border-box' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid #e2e8f0', paddingBottom: '8px' }}>
              <strong style={{ fontSize: '13px', color: '#64748b' }}>Cliente:</strong>
              <span style={{ fontSize: '13px', fontWeight: 700, color: '#0f172a' }}>{orderResult.customer_info.name}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid #e2e8f0', paddingBottom: '8px' }}>
              <strong style={{ fontSize: '13px', color: '#64748b' }}>Modalidad:</strong>
              <span style={{ fontSize: '13px', fontWeight: 700, color: '#0f172a' }}>
                {orderResult.customer_info.order_type === 'takeaway' ? '🏃 Recoger en Sucursal' : '🛵 Envío a Domicilio'}
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid #e2e8f0', paddingBottom: '8px' }}>
              <strong style={{ fontSize: '13px', color: '#64748b' }}>Total a Pagar:</strong>
              <span style={{ fontSize: '14px', fontWeight: 800, color: '#10b981' }}>{formatMoney(orderResult.total_cents)}</span>
            </div>
          </div>

          {/* Smart Rating & Google Reviews Section */}
          <div style={{ width: '100%', marginBottom: '18px', boxSizing: 'border-box' }}>
            {rating === null ? (
              <div style={{ background: '#f8fafc', padding: '16px', borderRadius: '16px', border: '1px solid #e2e8f0', textAlign: 'center' }}>
                <p style={{ fontSize: '13px', fontWeight: 700, color: '#334155', margin: '0 0 10px' }}>
                  ¿Cómo calificarías tu experiencia de compra?
                </p>
                <div style={{ display: 'flex', justifyContent: 'center', gap: '8px' }}>
                  {[1, 2, 3, 4, 5].map((star) => {
                    const isHighlighted = (hoveredRating !== null ? hoveredRating : 0) >= star;
                    return (
                      <button
                        key={star}
                        type="button"
                        onClick={() => handleSelectRating(star)}
                        onMouseEnter={() => setHoveredRating(star)}
                        onMouseLeave={() => setHoveredRating(null)}
                        style={{
                          background: 'none',
                          border: 'none',
                          cursor: 'pointer',
                          padding: '4px',
                          transition: 'transform 0.15s ease',
                          transform: isHighlighted ? 'scale(1.25)' : 'scale(1)',
                        }}
                        aria-label={`Calificar con ${star} estrellas`}
                      >
                        <Star
                          size={28}
                          fill={isHighlighted ? '#eab308' : '#f1f5f9'}
                          color={isHighlighted ? '#ca8a04' : '#94a3b8'}
                        />
                      </button>
                    );
                  })}
                </div>
              </div>
            ) : rating >= 4 ? (
              <div style={{ background: '#fefce8', border: '1px solid #fef08a', borderRadius: '16px', padding: '16px', textAlign: 'center' }}>
                <div style={{ display: 'flex', justifyContent: 'center', gap: '4px', marginBottom: '6px' }}>
                  {[1, 2, 3, 4, 5].map((s) => (
                    <Star
                      key={s}
                      size={18}
                      fill={s <= rating ? '#eab308' : '#fef9c3'}
                      color={s <= rating ? '#ca8a04' : '#cbd5e1'}
                    />
                  ))}
                </div>
                <strong style={{ fontSize: '14px', color: '#854d0e', display: 'block', marginBottom: '4px' }}>
                  ¡Muchas gracias por tu calificación de {rating} estrellas! 🎉
                </strong>
                {branch?.google_review_url ? (
                  <>
                    <p style={{ fontSize: '12px', color: '#a16207', margin: '0 0 12px', lineHeight: 1.4 }}>
                      ¿Nos apoyarías con 1 minuto compartiendo tu opinión en Google Maps para que más personas nos conozcan?
                    </p>
                    <a
                      href={branch.google_review_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: '8px',
                        background: '#0f172a',
                        color: '#ffffff',
                        padding: '10px 20px',
                        borderRadius: '9999px',
                        fontWeight: 700,
                        fontSize: '13px',
                        textDecoration: 'none',
                        boxShadow: '0 4px 12px rgba(15, 23, 42, 0.2)',
                        transition: 'opacity 0.2s',
                      }}
                    >
                      <Star size={16} fill="#eab308" color="#eab308" />
                      <span>Dejar Reseña en Google</span>
                      <ExternalLink size={14} />
                    </a>
                  </>
                ) : (
                  <p style={{ fontSize: '12px', color: '#a16207', margin: 0, lineHeight: 1.4 }}>
                    Nos alegra mucho poder atenderte. ¡Disfruta tu comida!
                  </p>
                )}
              </div>
            ) : (
              <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '16px', padding: '16px', textAlign: 'center' }}>
                <div style={{ display: 'flex', justifyContent: 'center', gap: '4px', marginBottom: '6px' }}>
                  {[1, 2, 3, 4, 5].map((s) => (
                    <Star
                      key={s}
                      size={18}
                      fill={s <= rating ? '#eab308' : '#f1f5f9'}
                      color={s <= rating ? '#ca8a04' : '#94a3b8'}
                    />
                  ))}
                </div>
                <strong style={{ fontSize: '14px', color: '#334155', display: 'block', marginBottom: '4px' }}>
                  Lamentamos que tu experiencia no haya sido perfecta 😔
                </strong>
                {feedbackSubmitted ? (
                  <p style={{ fontSize: '12px', color: '#059669', fontWeight: 600, margin: '8px 0 0' }}>
                    ¡Muchas gracias por tus comentarios! Los hemos recibido y los revisaremos con gerencia para mejorar.
                  </p>
                ) : (
                  <>
                    <p style={{ fontSize: '12px', color: '#64748b', margin: '0 0 10px', lineHeight: 1.4 }}>
                      Cuéntanos qué podemos mejorar para atenderte mejor:
                    </p>
                    <textarea
                      rows={2}
                      value={privateComment}
                      onChange={(e) => setPrivateComment(e.target.value)}
                      placeholder="Escribe tus sugerencias o qué sucedió..."
                      style={{
                        width: '100%',
                        padding: '10px',
                        borderRadius: '10px',
                        border: '1px solid #cbd5e1',
                        fontSize: '13px',
                        boxSizing: 'border-box',
                        fontFamily: 'inherit',
                        resize: 'none',
                        marginBottom: '10px',
                      }}
                    />
                    <button
                      type="button"
                      disabled={isSubmittingFeedback}
                      onClick={handleSendPrivateFeedback}
                      style={{
                        background: '#334155',
                        color: '#fff',
                        border: 'none',
                        padding: '8px 18px',
                        borderRadius: '9999px',
                        fontSize: '12px',
                        fontWeight: 700,
                        cursor: 'pointer',
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '6px',
                      }}
                    >
                      <Send size={14} />
                      <span>{isSubmittingFeedback ? 'Enviando...' : 'Enviar Retroalimentación a Gerencia'}</span>
                    </button>
                  </>
                )}
              </div>
            )}
          </div>

          {orderResult.whatsapp_url && (
            <a
              href={orderResult.whatsapp_url}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                width: '100%',
                padding: '14px',
                borderRadius: '9999px',
                border: 'none',
                background: '#25D366',
                color: '#ffffff',
                fontWeight: 800,
                fontSize: '15px',
                fontFamily: 'inherit',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '8px',
                boxShadow: '0 4px 14px rgba(37, 211, 102, 0.35)',
                textDecoration: 'none',
                marginBottom: '12px',
                boxSizing: 'border-box',
              }}
            >
              <span>📲 Enviar Pedido por WhatsApp</span>
            </a>
          )}

          <button
            type="button"
            onClick={onNewOrder}
            style={{
              width: '100%',
              padding: '14px',
              borderRadius: '9999px',
              border: 'none',
              background: '#0f172a',
              color: '#ffffff',
              fontWeight: 800,
              fontSize: '15px',
              fontFamily: 'inherit',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '8px',
              boxShadow: '0 4px 12px rgba(15, 23, 42, 0.15)',
              marginBottom: '10px',
            }}
          >
            <ShoppingBag size={18} />
            <span>Hacer Otro Pedido</span>
          </button>

          <button
            type="button"
            onClick={onClose}
            style={{
              width: '100%',
              padding: '12px',
              borderRadius: '9999px',
              border: '1px solid #e2e8f0',
              background: '#ffffff',
              color: '#64748b',
              fontWeight: 700,
              fontSize: '14px',
              fontFamily: 'inherit',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '6px',
            }}
          >
            <ArrowLeft size={16} />
            <span>Volver al Menú</span>
          </button>
        </div>
      </div>
    </div>
  );
};
