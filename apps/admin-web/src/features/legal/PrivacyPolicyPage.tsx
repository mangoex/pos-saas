import React, { useState } from 'react';
import { ShieldCheck, Lock, FileText, ArrowLeft, Building2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export const PrivacyPolicyPage: React.FC = () => {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<'privacy' | 'terms'>('privacy');

  return (
    <div
      style={{
        minHeight: '100vh',
        backgroundColor: '#f8fafc',
        color: '#0f172a',
        padding: '32px 16px 64px',
        fontFamily: 'system-ui, -apple-system, sans-serif',
      }}
    >
      <div
        style={{
          maxWidth: 860,
          margin: '0 auto',
        }}
      >
        {/* Navigation back */}
        <div style={{ marginBottom: 20 }}>
          <button
            type="button"
            onClick={() => navigate(-1)}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              background: 'none',
              border: 'none',
              color: '#2563eb',
              fontSize: '0.9rem',
              fontWeight: 600,
              cursor: 'pointer',
              padding: '6px 0',
            }}
          >
            <ArrowLeft size={16} /> Volver
          </button>
        </div>

        {/* Header card */}
        <div
          style={{
            backgroundColor: '#ffffff',
            borderRadius: 16,
            padding: '32px 28px',
            border: '1px solid #e2e8f0',
            boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.05)',
            marginBottom: 24,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
            <div
              style={{
                width: 44,
                height: 44,
                borderRadius: 12,
                backgroundColor: 'rgba(37, 99, 235, 0.1)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#2563eb',
              }}
            >
              <ShieldCheck size={24} />
            </div>
            <div>
              <h1 style={{ margin: 0, fontSize: '1.5rem', fontWeight: 800 }}>
                Centro Legal, Privacidad y Términos
              </h1>
              <p style={{ margin: 0, fontSize: '0.875rem', color: '#64748b' }}>
                POS-SaaS · mi menú.onl — Conforme a la legislación vigente (LFPDPPP México y estándares internacionales)
              </p>
            </div>
          </div>

          {/* Tab Selector */}
          <div
            style={{
              display: 'flex',
              gap: 8,
              marginTop: 20,
              borderTop: '1px solid #e2e8f0',
              paddingTop: 16,
            }}
          >
            <button
              type="button"
              onClick={() => setActiveTab('privacy')}
              style={{
                padding: '8px 16px',
                borderRadius: 8,
                border: 'none',
                backgroundColor: activeTab === 'privacy' ? '#2563eb' : '#f1f5f9',
                color: activeTab === 'privacy' ? '#ffffff' : '#475569',
                fontWeight: 600,
                fontSize: '0.875rem',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 6,
              }}
            >
              <Lock size={15} /> Aviso de Privacidad Integral
            </button>

            <button
              type="button"
              onClick={() => setActiveTab('terms')}
              style={{
                padding: '8px 16px',
                borderRadius: 8,
                border: 'none',
                backgroundColor: activeTab === 'terms' ? '#2563eb' : '#f1f5f9',
                color: activeTab === 'terms' ? '#ffffff' : '#475569',
                fontWeight: 600,
                fontSize: '0.875rem',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 6,
              }}
            >
              <FileText size={15} /> Términos del Servicio y Deslinde Alimentario
            </button>
          </div>
        </div>

        {/* Content card */}
        <div
          style={{
            backgroundColor: '#ffffff',
            borderRadius: 16,
            padding: '36px 32px',
            border: '1px solid #e2e8f0',
            boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.05)',
            lineHeight: 1.7,
            color: '#334155',
            fontSize: '0.9375rem',
          }}
        >
          {activeTab === 'privacy' ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
              <div>
                <h2 style={{ fontSize: '1.25rem', fontWeight: 800, color: '#0f172a', margin: '0 0 10px' }}>
                  Aviso de Privacidad Integral
                </h2>
                <p style={{ color: '#64748b', fontSize: '0.85rem', margin: 0 }}>
                  Última actualización: Octubre de 2026
                </p>
              </div>

              <section>
                <h3 style={{ fontSize: '1.05rem', fontWeight: 700, color: '#0f172a', margin: '0 0 8px' }}>
                  1. Identidad y Domicilio del Responsable
                </h3>
                <p style={{ margin: 0 }}>
                  La plataforma tecnológica <strong>POS-SaaS / mi menú.onl</strong> (en lo sucesivo, el "SaaS" o el "Responsable"), accesible vía <strong>https://mimenu.onl</strong> y correo de contacto <strong>privacidad@mimenu.onl</strong>, pone a su disposición este Aviso de Privacidad Integral en cumplimiento con la <strong>Ley Federal de Protección de Datos Personales en Posesión de los Particulares (LFPDPPP)</strong> y su normatividad complementaria.
                </p>
              </section>

              <section>
                <h3 style={{ fontSize: '1.05rem', fontWeight: 700, color: '#0f172a', margin: '0 0 8px' }}>
                  2. Distinción de Roles en el Tratamiento (Responsable vs. Encargado)
                </h3>
                <p style={{ margin: '0 0 8px' }}>
                  <strong>A. Clientes Comerciales (Restaurantes, Cafeterías y Afiliados B2B):</strong> Respecto a la información de los comercios afiliados, sus administradores, supervisores y cajeros (nombres, correos, constancias fiscales, sellos digitales de facturación y tarjetas tokenizadas), la Plataforma actúa en calidad de <strong>Responsable</strong> directo del tratamiento.
                </p>
                <p style={{ margin: 0 }}>
                  <strong>B. Comensales y Clientes Finales (B2B2C):</strong> El Restaurante es el <strong>Responsable principal</strong> de recabar el consentimiento de sus comensales. La Plataforma actúa en calidad de <strong>Encargada del Tratamiento</strong>, procesando los datos estrictamente por cuenta y orden del Restaurante para el envío de comandas a cocina, despacho por WhatsApp y autofacturación CFDI 4.0.
                </p>
              </section>

              <section>
                <h3 style={{ fontSize: '1.05rem', fontWeight: 700, color: '#0f172a', margin: '0 0 8px' }}>
                  3. Datos Personales Recabados y Datos Sensibles (Alergias / Salud)
                </h3>
                <p style={{ margin: '0 0 8px' }}>
                  Recabamos datos de identificación (nombre, usuario, contraseña encriptada), contacto (teléfono celular, WhatsApp, correo electrónico), fiscales (RFC, razón social, régimen tributario, CSD para CFDI 4.0) y geolocalización o dirección de entrega para pedidos a domicilio.
                </p>
                <div
                  style={{
                    backgroundColor: '#fffbeb',
                    border: '1px solid #fef3c7',
                    borderRadius: 8,
                    padding: '12px 16px',
                    color: '#92400e',
                    fontSize: '0.875rem',
                  }}
                >
                  <strong>Tratamiento de Datos Personales Sensibles de Salud:</strong> Cuando el comensal especifica de forma voluntaria en las notas de pedido notas relativas a celiaquía, diabetes, alergias a nueces, mariscos, lácteos u otras condiciones fisiológicas, estos datos se clasifican como datos sensibles de salud y se procesan <strong>únicamente</strong> para comunicar la advertencia al personal de cocina del restaurante.
                </div>
              </section>

              <section>
                <h3 style={{ fontSize: '1.05rem', fontWeight: 700, color: '#0f172a', margin: '0 0 8px' }}>
                  4. Finalidades del Tratamiento
                </h3>
                <p style={{ margin: 0 }}>
                  El tratamiento tiene por finalidades primarias aprovisionar cuentas multi-tenant seguras, operar el punto de venta y cocina (POS/KDS), procesar órdenes presenciales y digitales, generar pedidos por WhatsApp, auditar turnos y cortes de caja, proveer autofacturación desatendida CFDI 4.0 y gestionar las suscripciones de los comercios.
                </p>
              </section>

              <section>
                <h3 style={{ fontSize: '1.05rem', fontWeight: 700, color: '#0f172a', margin: '0 0 8px' }}>
                  5. Transferencias de Datos a Terceros
                </h3>
                <p style={{ margin: 0 }}>
                  No vendemos ni comercializamos datos personales. Las transferencias operativas se realizan bajo el artículo 37 de la LFPDPPP con pasarelas de pago (Mercado Pago, Stripe), Proveedores Autorizados de Certificación (PAC) del SAT, proveedores de nube y autoridades competentes en estricto cumplimiento legal.
                </p>
              </section>

              <section>
                <h3 style={{ fontSize: '1.05rem', fontWeight: 700, color: '#0f172a', margin: '0 0 8px' }}>
                  6. Ejercicio de Derechos ARCO y Revocación
                </h3>
                <p style={{ margin: 0 }}>
                  Para ejercer sus derechos de Acceso, Rectificación, Cancelación u Oposición (ARCO), o para revocar su consentimiento, comuníquese con nuestro departamento de protección de datos al correo <strong>privacidad@mimenu.onl</strong>. La solicitud será atendida y resuelta en un plazo no mayor a 20 días hábiles.
                </p>
              </section>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
              <div>
                <h2 style={{ fontSize: '1.25rem', fontWeight: 800, color: '#0f172a', margin: '0 0 10px' }}>
                  Términos y Condiciones del Servicio y Deslinde de Responsabilidad
                </h2>
                <p style={{ color: '#64748b', fontSize: '0.85rem', margin: 0 }}>
                  Condiciones de Uso del Software y Delimitación de Responsabilidad Alimentaria
                </p>
              </div>

              <div
                style={{
                  backgroundColor: '#fef2f2',
                  border: '1px solid #fee2e2',
                  borderRadius: 8,
                  padding: '14px 18px',
                  color: '#991b1b',
                  fontSize: '0.875rem',
                }}
              >
                <strong>Delimitación Fundamental de Responsabilidad:</strong> La Plataforma provee software de información. En ningún caso la Plataforma cocina, almacena, empaca ni expende alimentos o bebidas.
              </div>

              <section>
                <h3 style={{ fontSize: '1.05rem', fontWeight: 700, color: '#0f172a', margin: '0 0 8px' }}>
                  1. Naturaleza como Proveedor Tecnológico Exclusivo
                </h3>
                <p style={{ margin: 0 }}>
                  POS-SaaS / mi menú.onl es una infraestructura tecnológica de Software as a Service (SaaS). El contrato de compraventa y consumo de alimentos y bebidas se perfecciona única y exclusivamente entre el Restaurante afiliado y el Comensal.
                </p>
              </section>

              <section>
                <h3 style={{ fontSize: '1.05rem', fontWeight: 700, color: '#0f172a', margin: '0 0 8px' }}>
                  2. Responsabilidad por Alimentos, Alérgenos y Normativa Sanitaria
                </h3>
                <p style={{ margin: '0 0 8px' }}>
                  El Restaurante afiliado es el único y exclusivo responsable legal de la higiene, inocuidad alimentaria, manipulación, caducidad, preparación, almacenamiento, cocción y entrega de todos los productos y alimentos comercializados con apoyo del software.
                </p>
                <p style={{ margin: 0 }}>
                  La Plataforma <strong>no asume responsabilidad alguna</strong> por contaminación cruzada, omisión de advertencias de alérgenos (frutos secos, gluten, lácteos, mariscos, etc.), intoxicaciones o reacciones adversas a la salud derivadas de la ingesta de los productos.
                </p>
              </section>

              <section>
                <h3 style={{ fontSize: '1.05rem', fontWeight: 700, color: '#0f172a', margin: '0 0 8px' }}>
                  3. Precios, Promociones y Cumplimiento ante el Consumidor
                </h3>
                <p style={{ margin: 0 }}>
                  El Restaurante es el autor de los precios, fotos y descripciones que publica. Cualquier discrepancia o queja referente a precios, promociones vencidas o disponibilidad de platillos es responsabilidad directa del Restaurante ante el comensal y ante autoridades de protección al consumidor (PROFECO).
                </p>
              </section>

              <section>
                <h3 style={{ fontSize: '1.05rem', fontWeight: 700, color: '#0f172a', margin: '0 0 8px' }}>
                  4. Cláusula de Indemnidad (Hold Harmless)
                </h3>
                <p style={{ margin: 0 }}>
                  El comercio afiliado se obliga a indemnizar y mantener a salvo a la Plataforma frente a cualquier reclamo, multa, sanción administrativa o litigio promovido por comensales o dependencias gubernamentales derivado de la manipulación de alimentos, errores de cobro en sus platillos o incumplimiento de medidas sanitarias locales.
                </p>
              </section>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default PrivacyPolicyPage;
