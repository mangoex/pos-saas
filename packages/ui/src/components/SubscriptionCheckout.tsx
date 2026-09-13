import React, { useState } from 'react';
import { initMercadoPago, CardPayment } from '@mercadopago/sdk-react';

// Inicializar Mercado Pago con la clave pública
// Soporta tanto Vite (import.meta.env) como Next/CRA (process.env)
const getPublicKey = () => {
  if (typeof process !== 'undefined' && process.env && process.env.NEXT_PUBLIC_MERCADOPAGO_PUBLIC_KEY) {
    return process.env.NEXT_PUBLIC_MERCADOPAGO_PUBLIC_KEY;
  }
  if (typeof import.meta !== 'undefined' && (import.meta as any).env && (import.meta as any).env.VITE_MERCADOPAGO_PUBLIC_KEY) {
    return (import.meta as any).env.VITE_MERCADOPAGO_PUBLIC_KEY;
  }
  return ''; // Reemplaza esto con una default key si es necesario para pruebas
};

const PUBLIC_KEY = getPublicKey();
initMercadoPago(PUBLIC_KEY, { locale: 'es-MX' });

export interface SubscriptionCheckoutProps {
  /** Callback emitido cuando se genera el token de forma segura */
  onTokenGenerated: (tokenId: string, formData: any) => void;
  /** Callback para manejar errores en la inicialización o pago */
  onError?: (error: any) => void;
}

/**
 * Componente de Checkout para Suscripción (Paquete Lite).
 * Implementa CardPayment (Bricks) de Mercado Pago para procesar pagos de manera segura,
 * garantizando que los datos sensibles no toquen nuestros servidores.
 */
export const SubscriptionCheckout: React.FC<SubscriptionCheckoutProps> = ({
  onTokenGenerated,
  onError,
}) => {
  const [isReady, setIsReady] = useState(false);

  // Configuración del paquete Lite
  const initialization = {
    amount: 349, // Costo del Paquete Lite: $349 MXN
  };

  /**
   * Manejador invocado por el Brick de Mercado Pago cuando el usuario envía el formulario.
   * Promesa requerida por el SDK para manejar el ciclo de vida del botón de pago.
   */
  const onSubmit = async (formData: any) => {
    return new Promise<void>((resolve, reject) => {
      // formData.token es el token_id seguro generado por MP
      if (formData && formData.token) {
        onTokenGenerated(formData.token, formData);
        resolve(); // Resuelve para que el botón deje de cargar (si aplica)
      } else {
        const error = new Error('No se pudo generar el token de la tarjeta.');
        if (onError) onError(error);
        reject();
      }
    });
  };

  const onReady = () => {
    setIsReady(true);
  };

  const onErrorHandler = (error: any) => {
    console.error('Error en el componente de Mercado Pago:', error);
    if (onError) onError(error);
  };

  return (
    <section 
      className="subscription-checkout-container"
      aria-labelledby="checkout-title"
    >
      <header className="checkout-header">
        <h2 id="checkout-title" className="checkout-title">
          Suscripción Paquete Lite
        </h2>
        <p className="checkout-price">
          <span className="sr-only">Precio: </span>
          $349 MXN <span className="checkout-period">/ mes</span>
        </p>
      </header>

      <div className="checkout-form-wrapper" aria-live="polite">
        {!isReady && (
          <div className="loading-state">
            <span className="loading-spinner" aria-hidden="true"></span>
            <p>Cargando pasarela segura...</p>
          </div>
        )}
        
        {/*
          CardPayment renderiza un iframe seguro (Secure Fields).
          Se inyectan customVariables para mantener coherencia con nuestros tokens de diseño.
        */}
        <CardPayment
          initialization={initialization}
          onSubmit={onSubmit}
          onReady={onReady}
          onError={onErrorHandler}
          customization={{
            visual: {
              style: {
                theme: 'default',
                customVariables: {
                  formBackgroundColor: 'transparent',
                  baseColor: 'var(--color-primary)',
                  textPrimaryColor: 'var(--color-text)',
                  textSecondaryColor: 'var(--color-text-muted)',
                  errorColor: 'var(--color-error)',
                  successColor: 'var(--color-success)',
                  outlinePrimaryColor: 'var(--color-focus)',
                  buttonTextColor: '#ffffff',
                }
              }
            },
            paymentMethods: {
              maxInstallments: 1, // Restringido a 1 cargo por ser suscripción
            }
          }}
        />
      </div>

      <style>{`
        /* Tokens de Diseño Base (Lean Design) */
        .subscription-checkout-container {
          --color-background: #ffffff;
          --color-primary: #009ee3; /* Color de acción por defecto MP, adaptable a la marca */
          --color-text: #1f2937;
          --color-text-muted: #6b7280;
          --color-border: #e5e7eb;
          --color-error: #ef4444;
          --color-success: #10b981;
          --color-focus: rgba(0, 158, 227, 0.4);
          
          --radius-md: 0.5rem;
          --radius-lg: 0.75rem;
          --spacing-sm: 0.5rem;
          --spacing-md: 1rem;
          --spacing-lg: 1.5rem;

          background-color: var(--color-background);
          border: 1px solid var(--color-border);
          border-radius: var(--radius-lg);
          padding: var(--spacing-lg);
          max-width: 400px;
          margin: 0 auto;
          box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
          font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        }

        .checkout-header {
          text-align: center;
          margin-bottom: var(--spacing-lg);
          padding-bottom: var(--spacing-md);
          border-bottom: 1px solid var(--color-border);
        }

        .checkout-title {
          font-size: 1.25rem;
          font-weight: 600;
          color: var(--color-text);
          margin: 0 0 var(--spacing-sm) 0;
        }

        .checkout-price {
          font-size: 2rem;
          font-weight: 700;
          color: var(--color-text);
          margin: 0;
          display: flex;
          align-items: baseline;
          justify-content: center;
          gap: 0.25rem;
        }

        .checkout-period {
          font-size: 1rem;
          font-weight: 400;
          color: var(--color-text-muted);
        }

        .checkout-form-wrapper {
          position: relative;
          min-height: 250px; /* Evita saltos bruscos de Layout (CLS) mientras se carga MP */
        }

        .loading-state {
          position: absolute;
          inset: 0;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          color: var(--color-text-muted);
          font-size: 0.875rem;
          z-index: 10;
        }

        .loading-spinner {
          width: 24px;
          height: 24px;
          border: 2px solid var(--color-border);
          border-top-color: var(--color-primary);
          border-radius: 50%;
          animation: spin 1s linear infinite;
          margin-bottom: var(--spacing-sm);
        }

        @keyframes spin {
          to { transform: rotate(360deg); }
        }

        .sr-only {
          position: absolute;
          width: 1px;
          height: 1px;
          padding: 0;
          margin: -1px;
          overflow: hidden;
          clip: rect(0, 0, 0, 0);
          white-space: nowrap;
          border-width: 0;
        }

        /* a11y: Visibilidad de Focus para teclado */
        .subscription-checkout-container *:focus-visible {
          outline: 2px solid var(--color-primary);
          outline-offset: 2px;
        }
      `}</style>
    </section>
  );
};
