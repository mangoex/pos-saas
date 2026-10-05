import React, { useEffect } from 'react';
import { X, ShieldCheck, AlertCircle, FileText, Lock, Building, ExternalLink } from 'lucide-react';

interface PrivacyPolicyModalProps {
  isOpen: boolean;
  onClose: () => void;
  defaultTab?: 'privacy' | 'terms';
}

export const PrivacyPolicyModal: React.FC<PrivacyPolicyModalProps> = ({
  isOpen,
  onClose,
  defaultTab = 'privacy',
}) => {
  const [activeTab, setActiveTab] = React.useState<'privacy' | 'terms'>(defaultTab);

  useEffect(() => {
    setActiveTab(defaultTab);
  }, [defaultTab]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="legal-modal-title"
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(15, 23, 42, 0.75)',
        backdropFilter: 'blur(4px)',
        zIndex: 9999,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '16px',
        animation: 'fadeIn 0.15s ease-out',
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        style={{
          backgroundColor: '#ffffff',
          borderRadius: 16,
          width: '100%',
          maxWidth: 780,
          maxHeight: '90vh',
          display: 'flex',
          flexDirection: 'column',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)',
          overflow: 'hidden',
          border: '1px solid #e2e8f0',
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: '18px 24px',
            borderBottom: '1px solid #e2e8f0',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            backgroundColor: '#f8fafc',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div
              style={{
                width: 36,
                height: 36,
                borderRadius: 10,
                backgroundColor: 'rgba(37, 99, 235, 0.1)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#2563eb',
              }}
            >
              <ShieldCheck size={20} />
            </div>
            <div>
              <h2
                id="legal-modal-title"
                style={{
                  margin: 0,
                  fontSize: '1.15rem',
                  fontWeight: 700,
                  color: '#0f172a',
                }}
              >
                Información Legal y Cumplimiento
              </h2>
              <p
                style={{
                  margin: 0,
                  fontSize: '0.8rem',
                  color: '#64748b',
                }}
              >
                Transparencia, protección de datos y condiciones del servicio SaaS
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            aria-label="Cerrar ventana"
            style={{
              background: 'transparent',
              border: 'none',
              padding: 8,
              borderRadius: 8,
              cursor: 'pointer',
              color: '#64748b',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              transition: 'background-color 0.2s',
            }}
          >
            <X size={20} />
          </button>
        </div>

        {/* Tab Navigation */}
        <div
          style={{
            display: 'flex',
            borderBottom: '1px solid #e2e8f0',
            backgroundColor: '#ffffff',
            padding: '0 24px',
          }}
        >
          <button
            type="button"
            onClick={() => setActiveTab('privacy')}
            style={{
              padding: '12px 16px',
              border: 'none',
              background: 'none',
              fontSize: '0.9rem',
              fontWeight: activeTab === 'privacy' ? 700 : 500,
              color: activeTab === 'privacy' ? '#2563eb' : '#64748b',
              borderBottom: activeTab === 'privacy' ? '2px solid #2563eb' : '2px solid transparent',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 8,
            }}
          >
            <Lock size={16} />
            Aviso de Privacidad Integral
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('terms')}
            style={{
              padding: '12px 16px',
              border: 'none',
              background: 'none',
              fontSize: '0.9rem',
              fontWeight: activeTab === 'terms' ? 700 : 500,
              color: activeTab === 'terms' ? '#2563eb' : '#64748b',
              borderBottom: activeTab === 'terms' ? '2px solid #2563eb' : '2px solid transparent',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 8,
            }}
          >
            <FileText size={16} />
            Términos y Deslinde Alimentario
          </button>
        </div>

        {/* Content Body */}
        <div
          style={{
            padding: '24px',
            overflowY: 'auto',
            fontSize: '0.9rem',
            lineHeight: 1.6,
            color: '#334155',
          }}
        >
          {activeTab === 'privacy' ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
              <div
                style={{
                  padding: '12px 16px',
                  backgroundColor: '#f0fdf4',
                  border: '1px solid #bbf7d0',
                  borderRadius: 8,
                  fontSize: '0.85rem',
                  color: '#166534',
                }}
              >
                <strong>Marco de Cumplimiento:</strong> Este aviso se expide con apego a la <strong>Ley Federal de Protección de Datos Personales en Posesión de los Particulares (LFPDPPP)</strong> y estándares internacionales de ciberseguridad para software en la nube multi-tenant.
              </div>

              <section>
                <h3 style={{ margin: '0 0 6px', fontSize: '1rem', color: '#0f172a', fontWeight: 700 }}>
                  1. Identidad y Domicilio del Responsable
                </h3>
                <p style={{ margin: 0 }}>
                  La plataforma tecnológica <strong>POS-SaaS / mi menú.onl</strong> (en adelante el "SaaS" o el "Responsable"), con portal web oficial en <strong>https://mimenu.onl</strong> y correo de contacto <strong>privacidad@mimenu.onl</strong>, es responsable del tratamiento de los datos personales obtenidos a través de la aplicación web de administración, puntos de venta, terminales de cocina y menús digitales interactivos.
                </p>
              </section>

              <section>
                <h3 style={{ margin: '0 0 6px', fontSize: '1rem', color: '#0f172a', fontWeight: 700 }}>
                  2. Distinción de Roles (Responsable vs. Encargado)
                </h3>
                <p style={{ margin: '0 0 8px' }}>
                  <strong>A. Clientes Comerciales (Restaurantes y Afiliados):</strong> Respecto a la información de los comercios afiliados, representantes y personal operativo (usuarios, correos, RFC, datos de facturación de suscripción), el SaaS actúa en calidad de <strong>Responsable</strong>.
                </p>
                <p style={{ margin: 0 }}>
                  <strong>B. Comensales y Clientes Finales del Restaurante:</strong> El Restaurante afiliado actúa como <strong>Responsable principal</strong> de la relación con sus clientes. El SaaS actúa como <strong>Encargado del Tratamiento</strong>, procesando los datos bajo las instrucciones del comercio para la emisión de comandas, confirmación de pedidos vía WhatsApp y autofacturación CFDI 4.0.
                </p>
              </section>

              <section>
                <h3 style={{ margin: '0 0 6px', fontSize: '1rem', color: '#0f172a', fontWeight: 700 }}>
                  3. Datos Personales Recabados y Datos Sensibles (Salud / Alergias)
                </h3>
                <ul style={{ margin: '0 0 8px', paddingLeft: 20 }}>
                  <li><strong>Datos de Identificación:</strong> Nombre o alias, correo electrónico, teléfono móvil / WhatsApp, rol administrativo.</li>
                  <li><strong>Datos Comerciales y Fiscales:</strong> Nombre de la sucursal, RFC, régimen tributario, sellos para autofacturación fiscal, código postal.</li>
                  <li><strong>Datos de Entrega:</strong> Coordenadas GPS y referencias domiciliarias provistas por el comensal.</li>
                  <li>
                    <strong>DATOS SENSIBLES RELATIVOS A LA SALUD (Alergias e Intolerancias):</strong> Toda indicación de alergias severas, celiaquía o requerimientos alimentarios especiales ingresados voluntariamente en las notas de pedido son clasificados como datos personales sensibles de salud. Son procesados con el único fin de informar a la cocina del restaurante para la confección del platillo.
                  </li>
                </ul>
              </section>

              <section>
                <h3 style={{ margin: '0 0 6px', fontSize: '1rem', color: '#0f172a', fontWeight: 700 }}>
                  4. Finalidades del Tratamiento
                </h3>
                <p style={{ margin: 0 }}>
                  Aprovisionamiento de cuenta, operación de cobros en mostrador/caja, visualización de catálogo digital, conexión con cocina (KDS), envío de pedidos por WhatsApp, emisión de tickets y facturas electrónicas, soporte técnico y mantenimiento de la seguridad multi-tenant.
                </p>
              </section>

              <section>
                <h3 style={{ margin: '0 0 6px', fontSize: '1rem', color: '#0f172a', fontWeight: 700 }}>
                  5. Transferencias de Datos a Terceros
                </h3>
                <p style={{ margin: 0 }}>
                  Los datos podrán transferirse exclusivamente a: pasarelas de pago seguras (Mercado Pago, Stripe) para suscripciones; Proveedores Autorizados de Certificación (PAC) y SAT para facturación fiscal; proveedores de servidores e infraestructura en la nube; y autoridades competentes en términos del artículo 37 de la LFPDPPP. No comercializamos datos personales con terceros.
                </p>
              </section>

              <section>
                <h3 style={{ margin: '0 0 6px', fontSize: '1rem', color: '#0f172a', fontWeight: 700 }}>
                  6. Ejercicio de Derechos ARCO
                </h3>
                <p style={{ margin: 0 }}>
                  El titular tiene derecho a ejercer sus derechos de <strong>Acceso, Rectificación, Cancelación y Oposición (ARCO)</strong> o revocar su consentimiento enviando un correo a <strong>privacidad@mimenu.onl</strong> acompañado de su identificación oficial y la descripción precisa de la solicitud. Plazo máximo de respuesta: 20 días hábiles.
                </p>
              </section>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
              <div
                style={{
                  padding: '12px 16px',
                  backgroundColor: '#fef2f2',
                  border: '1px solid #fecaca',
                  borderRadius: 8,
                  fontSize: '0.85rem',
                  color: '#991b1b',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                }}
              >
                <AlertCircle size={24} style={{ flexShrink: 0 }} />
                <div>
                  <strong>Aviso de Riesgo y Deslinde de Responsabilidad:</strong> El SaaS es un proveedor estrictamente tecnológico. La preparación de alimentos, inocuidad, higiene y veracidad de precios son responsabilidad exclusiva del comercio afiliado.
                </div>
              </div>

              <section>
                <h3 style={{ margin: '0 0 6px', fontSize: '1rem', color: '#0f172a', fontWeight: 700 }}>
                  1. Naturaleza Exclusiva del Servicio de Software
                </h3>
                <p style={{ margin: 0 }}>
                  La Plataforma provee un servicio de software como servicio (SaaS) para la gestión operativa y digital de restaurantes. En ningún momento la Plataforma elabora, almacena, prepara, distribuye, manipula ni comercializa alimentos o bebidas. La relación de consumo de alimentos se celebra única y exclusivamente entre el Restaurante y el Comensal.
                </p>
              </section>

              <section>
                <h3 style={{ margin: '0 0 6px', fontSize: '1rem', color: '#0f172a', fontWeight: 700 }}>
                  2. Responsabilidad por Alérgenos, Inocuidad e Higiene
                </h3>
                <p style={{ margin: '0 0 8px' }}>
                  El Restaurante afiliado asume la responsabilidad total y absoluta sobre la calidad, estado de conservación, inocuidad alimentaria, tiempos de cocción, temperaturas, rotulación de ingredientes y advertencia de posibles alérgenos (frutos secos, mariscos, gluten, lácteos, etc.).
                </p>
                <p style={{ margin: 0 }}>
                  La Plataforma no asume responsabilidad alguna por intoxicaciones, reacciones alérgicas, contaminación cruzada o cualquier perjuicio derivado de la ingesta o consumo de los alimentos ofrecidos por los establecimientos afiliados.
                </p>
              </section>

              <section>
                <h3 style={{ margin: '0 0 6px', fontSize: '1rem', color: '#0f172a', fontWeight: 700 }}>
                  3. Catálogo, Precios, Ofertas y Promociones
                </h3>
                <p style={{ margin: 0 }}>
                  El Restaurante es el autor y custodio exclusivo de su catálogo de productos. Todo error tipográfico, variación de precios entre canales, disponibilidad agotada o promoción no respetada es responsabilidad legal y comercial del Restaurante frente al comensal y ante las autoridades de protección al consumidor (PROFECO o equivalente).
                </p>
              </section>

              <section>
                <h3 style={{ margin: '0 0 6px', fontSize: '1rem', color: '#0f172a', fontWeight: 700 }}>
                  4. Obligación de Indemnidad (Hold Harmless)
                </h3>
                <p style={{ margin: 0 }}>
                  El Restaurante afiliado se compromete expresamente a defender, indemnizar y sacar en paz y a salvo a la Plataforma respecto de cualquier queja, demanda, procedimiento sancionatorio o reclamación de daños interpuesta por comensales o autoridades derivado de la calidad o preparación de los alimentos.
                </p>
              </section>
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <div
          style={{
            padding: '14px 24px',
            borderTop: '1px solid #e2e8f0',
            backgroundColor: '#f8fafc',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <a
            href="/admin/privacy"
            target="_blank"
            rel="noopener noreferrer"
            style={{
              fontSize: '0.85rem',
              color: '#2563eb',
              textDecoration: 'none',
              fontWeight: 600,
              display: 'inline-flex',
              alignItems: 'center',
              gap: 4,
            }}
          >
            Abrir versión completa en pestaña nueva <ExternalLink size={14} />
          </a>

          <button
            type="button"
            onClick={onClose}
            style={{
              padding: '8px 18px',
              borderRadius: 8,
              backgroundColor: '#0f172a',
              color: '#ffffff',
              border: 'none',
              fontSize: '0.875rem',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            Entendido y Cerrar
          </button>
        </div>
      </div>
    </div>
  );
};
