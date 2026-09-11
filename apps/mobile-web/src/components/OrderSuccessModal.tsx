import React, { useState } from 'react';
import { CheckCircle2, X, ShoppingBag, ArrowLeft, Clock, ChefHat, Star, Send, ExternalLink, Sparkles, Camera, Upload, Copy, Check } from 'lucide-react';
import { CreatedOrderResult, BranchInfo } from '../types';
import { formatMoney, submitCustomerFeedback, submitCommunityPhoto } from '../api';

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

  // UGC Photo & Loyalty Campaign State
  const [showPhotoUpload, setShowPhotoUpload] = useState(false);
  const [selectedDishId, setSelectedDishId] = useState<string>(
    orderResult.items?.[0]?.product?.id || ''
  );
  const [photoPreview, setPhotoPreview] = useState<string | null>(null);
  const [photoCaption, setPhotoCaption] = useState('');
  const [isUploadingPhoto, setIsUploadingPhoto] = useState(false);
  const [ugcRewardResult, setUgcRewardResult] = useState<{ discount_code: string; message: string } | null>(null);
  const [copiedCode, setCopiedCode] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const isWhatsAppEnabled = Boolean(branch?.whatsapp_ordering_enabled) && Boolean(orderResult.whatsapp_url);

  // Auto-redirect to WhatsApp on mobile devices ONLY when enabled by branch and URL is present
  React.useEffect(() => {
    if (isWhatsAppEnabled && orderResult.whatsapp_url && typeof window !== 'undefined') {
      const isMobile = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent) || window.innerWidth <= 768;
      if (isMobile) {
        const timer = setTimeout(() => {
          window.location.href = orderResult.whatsapp_url!;
        }, 900);
        return () => clearTimeout(timer);
      }
    }
  }, [isWhatsAppEnabled, orderResult.whatsapp_url]);

  const handleSelectRating = (selected: number) => {
    setRating(selected);
    if (branch?.id) {
      // Record feedback immediately for all ratings (1-5) linked to customer phone
      submitCustomerFeedback({
        branch_id: branch.id,
        rating: selected,
        customer_phone: orderResult.customer_info.phone,
        order_folio: orderFolio,
        comment: selected >= 4 ? 'Calificación positiva (App Móvil)' : undefined,
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
        customer_phone: orderResult.customer_info.phone,
        order_folio: orderFolio,
        comment: privateComment.trim() || undefined,
      });
      setFeedbackSubmitted(true);
    } finally {
      setIsSubmittingFeedback(false);
    }
  };

  const handlePhotoFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const img = new Image();
      img.onload = () => {
        const canvas = document.createElement('canvas');
        const maxDim = 800;
        let w = img.width;
        let h = img.height;
        if (w > h && w > maxDim) {
          h = Math.round((h * maxDim) / w);
          w = maxDim;
        } else if (h > maxDim) {
          w = Math.round((w * maxDim) / h);
          h = maxDim;
        }
        canvas.width = w;
        canvas.height = h;
        const ctx = canvas.getContext('2d');
        if (!ctx) {
          setPhotoPreview(reader.result as string);
          return;
        }
        ctx.drawImage(img, 0, 0, w, h);
        setPhotoPreview(canvas.toDataURL('image/jpeg', 0.8));
      };
      img.src = reader.result as string;
    };
    reader.readAsDataURL(file);
  };

  const handleSendCommunityPhoto = async () => {
    if (!branch?.public_key || !photoPreview || !selectedDishId) return;
    setIsUploadingPhoto(true);
    setUploadError(null);
    try {
      const res = await submitCommunityPhoto(branch.public_key, {
        product_id: selectedDishId,
        order_folio: orderFolio,
        customer_name: orderResult.customer_info.name,
        customer_phone: orderResult.customer_info.phone,
        image_url: photoPreview,
        caption: photoCaption.trim() || undefined,
      });
      setUgcRewardResult({ discount_code: res.discount_code, message: res.message });
    } catch (err: any) {
      setUploadError(err.message || 'No se pudo enviar la foto.');
    } finally {
      setIsUploadingPhoto(false);
    }
  };

  const handleCopyCode = async (code: string) => {
    try {
      await navigator.clipboard.writeText(code);
      setCopiedCode(true);
      setTimeout(() => setCopiedCode(false), 2500);
    } catch {
      // ignore
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
            {orderResult.customer_info.order_type === 'delivery' && (
              <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid #e2e8f0', paddingBottom: '8px' }}>
                <strong style={{ fontSize: '13px', color: '#64748b' }}>Envío a Domicilio:</strong>
                <span style={{ fontSize: '13px', fontWeight: 700, color: (orderResult.delivery_fee_cents || orderResult.customer_info.delivery_fee_cents) ? '#0f172a' : '#16a34a' }}>
                  {(orderResult.delivery_fee_cents || orderResult.customer_info.delivery_fee_cents)
                    ? formatMoney(orderResult.delivery_fee_cents || orderResult.customer_info.delivery_fee_cents!)
                    : '¡Gratis!'}
                </span>
              </div>
            )}
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

          {/* Verified UGC Incentive Campaign */}
          <div
            style={{
              background: 'linear-gradient(135deg, #fefce8 0%, #fef08a 100%)',
              border: '1px solid #fde047',
              borderRadius: '16px',
              padding: '16px',
              textAlign: 'left',
              marginBottom: '16px',
              boxSizing: 'border-box',
              width: '100%',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
              <Camera size={20} color="#854d0e" />
              <strong style={{ fontSize: '13px', color: '#854d0e' }}>
                📸 ¡Gana 10% de descuento en tu próxima visita!
              </strong>
            </div>

            {ugcRewardResult ? (
              <div style={{ background: '#ffffff', borderRadius: '12px', padding: '12px', border: '1px solid #e2e8f0', textAlign: 'center' }}>
                <span style={{ fontSize: '12px', color: '#15803d', fontWeight: 700, display: 'block', marginBottom: '6px' }}>
                  🎉 ¡Foto enviada a moderación con éxito!
                </span>
                <span style={{ fontSize: '12px', color: '#64748b', display: 'block', marginBottom: '8px' }}>
                  Tu código de descuento para tu siguiente pedido es:
                </span>
                <div style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', background: '#f8fafc', padding: '6px 14px', borderRadius: '8px', border: '2px dashed #f59e0b', marginBottom: '8px' }}>
                  <strong style={{ fontSize: '15px', color: '#b45309', letterSpacing: '0.05em' }}>
                    {ugcRewardResult.discount_code}
                  </strong>
                  <button
                    type="button"
                    onClick={() => handleCopyCode(ugcRewardResult.discount_code)}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '2px', display: 'flex' }}
                    aria-label="Copiar código"
                  >
                    {copiedCode ? <Check size={16} color="#16a34a" /> : <Copy size={16} color="#64748b" />}
                  </button>
                </div>
                {copiedCode && <span style={{ fontSize: '11px', color: '#16a34a', display: 'block', fontWeight: 600 }}>¡Copiado al portapapeles!</span>}
              </div>
            ) : !showPhotoUpload ? (
              <div>
                <p style={{ fontSize: '12px', color: '#a16207', margin: '0 0 10px', lineHeight: 1.4 }}>
                  Comparte una foto de tu comida cuando te la sirvan. Tras moderarse aparecerá en el menú y recibirás un cupón de 10% de descuento.
                </p>
                <button
                  type="button"
                  onClick={() => setShowPhotoUpload(true)}
                  style={{
                    background: '#854d0e',
                    color: '#ffffff',
                    border: 'none',
                    padding: '8px 16px',
                    borderRadius: '9999px',
                    fontSize: '12px',
                    fontWeight: 700,
                    cursor: 'pointer',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '6px',
                  }}
                >
                  <Camera size={14} />
                  <span>Subir Foto y Recibir Cupón</span>
                </button>
              </div>
            ) : (
              <div style={{ background: '#ffffff', borderRadius: '12px', padding: '12px', border: '1px solid #e2e8f0' }}>
                <label style={{ fontSize: '12px', fontWeight: 700, color: '#334155', display: 'block', marginBottom: '4px' }}>
                  ¿De qué platillo es tu foto?
                </label>
                <select
                  value={selectedDishId}
                  onChange={(e) => setSelectedDishId(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '8px',
                    borderRadius: '8px',
                    border: '1px solid #cbd5e1',
                    fontSize: '12px',
                    marginBottom: '10px',
                    background: '#ffffff',
                  }}
                >
                  {orderResult.items?.map((item) => (
                    <option key={item.cart_id} value={item.product.id}>
                      {item.product.name}
                    </option>
                  ))}
                  {(!orderResult.items || orderResult.items.length === 0) && (
                    <option value="">Selecciona un platillo</option>
                  )}
                </select>

                <div style={{ marginBottom: '10px' }}>
                  <label style={{ fontSize: '12px', fontWeight: 700, color: '#334155', display: 'block', marginBottom: '4px' }}>
                    Foto de tu comida:
                  </label>
                  <input
                    type="file"
                    accept="image/*"
                    onChange={handlePhotoFileChange}
                    style={{ fontSize: '12px', width: '100%' }}
                  />
                  {photoPreview && (
                    <div style={{ marginTop: '8px', position: 'relative', width: '80px', height: '80px', borderRadius: '8px', overflow: 'hidden', border: '1px solid #cbd5e1' }}>
                      <img src={photoPreview} alt="Preview" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                    </div>
                  )}
                </div>

                <div style={{ marginBottom: '10px' }}>
                  <input
                    type="text"
                    placeholder="Comentario breve (ej: ¡Exquisito!)"
                    value={photoCaption}
                    onChange={(e) => setPhotoCaption(e.target.value)}
                    maxLength={140}
                    style={{
                      width: '100%',
                      padding: '8px',
                      borderRadius: '8px',
                      border: '1px solid #cbd5e1',
                      fontSize: '12px',
                      boxSizing: 'border-box',
                    }}
                  />
                </div>

                {uploadError && (
                  <span style={{ fontSize: '11px', color: '#dc2626', display: 'block', marginBottom: '8px' }}>
                    {uploadError}
                  </span>
                )}

                <div style={{ display: 'flex', gap: '8px' }}>
                  <button
                    type="button"
                    disabled={isUploadingPhoto || !photoPreview || !selectedDishId}
                    onClick={handleSendCommunityPhoto}
                    style={{
                      background: isUploadingPhoto || !photoPreview || !selectedDishId ? '#94a3b8' : '#16a34a',
                      color: '#ffffff',
                      border: 'none',
                      padding: '8px 16px',
                      borderRadius: '9999px',
                      fontSize: '12px',
                      fontWeight: 700,
                      cursor: isUploadingPhoto || !photoPreview || !selectedDishId ? 'not-allowed' : 'pointer',
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '6px',
                    }}
                  >
                    <Upload size={14} />
                    <span>{isUploadingPhoto ? 'Enviando...' : 'Enviar y Obtener Cupón'}</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => setShowPhotoUpload(false)}
                    style={{
                      background: 'none',
                      border: 'none',
                      color: '#64748b',
                      fontSize: '12px',
                      cursor: 'pointer',
                    }}
                  >
                    Cancelar
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Persistent Profile & Loyalty Info */}
          <div className="order-success-profile-card">
            <div className="order-success-profile-header">
              <span className="order-success-profile-icon">⚡</span>
              <div className="order-success-profile-text">
                <strong style={{ fontSize: '13px', color: '#0f172a', display: 'block' }}>
                  Datos recordados en mimenu
                </strong>
                <span style={{ fontSize: '12px', color: '#64748b', lineHeight: 1.4 }}>
                  Para tus próximos pedidos en cualquier restaurante, tu nombre ({orderResult.customer_info.name}) y teléfono ya estarán listos.
                </span>
              </div>
            </div>
            <div className="order-success-profile-loyalty-hint">
              <Sparkles size={14} color="#f59e0b" />
              <span>Próximamente: Vincula con Google para ganar puntos y recompensas en tus visitas.</span>
            </div>
          </div>

          {isWhatsAppEnabled && orderResult.whatsapp_url && (
            <div style={{
              background: '#f0fdf4',
              border: '1px solid #bbf7d0',
              borderRadius: '16px',
              padding: '12px 16px',
              marginBottom: '12px',
              fontSize: '13px',
              color: '#15803d',
              lineHeight: 1.4,
              textAlign: 'center',
              boxSizing: 'border-box',
              width: '100%',
            }}>
              <strong style={{ display: 'block', fontSize: '13px', marginBottom: '2px' }}>
                📲 Envía tu pedido por WhatsApp
              </strong>
              <span>
                Tu pedido quedó registrado en el sistema. Toca el botón verde para enviar los detalles al restaurante.
              </span>
            </div>
          )}

          {isWhatsAppEnabled && orderResult.whatsapp_url && (
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
