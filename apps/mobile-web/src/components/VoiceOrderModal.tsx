import React, { useState, useEffect, useRef } from 'react';
import { Mic, MicOff, Sparkles, X, RotateCcw } from 'lucide-react';
import { Product } from '../types';

interface VoiceOrderModalProps {
  isOpen: boolean;
  onClose: () => void;
  branchId: string | null;
  products: Product[];
  onAddCartItems: (newItems: any[]) => void;
}

const API_BASE_URL = '/api/v1';

export const VoiceOrderModal: React.FC<VoiceOrderModalProps> = ({
  isOpen,
  onClose,
  branchId,
  products,
  onAddCartItems,
}) => {
  const [transcript, setTranscript] = useState('');
  const [isRecording, setIsRecording] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [speechSupported, setSpeechSupported] = useState(true);

  const recognitionRef = useRef<any>(null);

  // Check speech recognition support and clean up on close
  useEffect(() => {
    if (!isOpen) {
      stopRecording();
      setTranscript('');
      setErrorMessage(null);
      setIsLoading(false);
      return;
    }

    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

    if (!SpeechRecognition) {
      setSpeechSupported(false);
      return;
    }

    setSpeechSupported(true);
    startRecording();

    return () => {
      stopRecording();
    };
  }, [isOpen]);

  const startRecording = () => {
    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

    if (!SpeechRecognition) {
      setSpeechSupported(false);
      return;
    }

    try {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.abort();
        } catch {
          // ignore
        }
      }

      const recognition = new SpeechRecognition();
      recognitionRef.current = recognition;
      recognition.lang = 'es-MX';
      recognition.continuous = true;
      recognition.interimResults = true;

      recognition.onstart = () => {
        setIsRecording(true);
        setErrorMessage(null);
      };

      recognition.onresult = (event: any) => {
        let finalTranscript = '';
        let interimTranscript = '';

        for (let i = 0; i < event.results.length; i++) {
          const result = event.results[i];
          if (result.isFinal) {
            finalTranscript += result[0].transcript + ' ';
          } else {
            interimTranscript += result[0].transcript;
          }
        }

        const full = (finalTranscript + interimTranscript).trim();
        if (full) {
          setTranscript(full);
        }
      };

      recognition.onerror = (event: any) => {
        console.warn('Speech recognition event error:', event.error);
        if (event.error === 'not-allowed') {
          setErrorMessage('Permiso de micrófono denegado. Escribe tu pedido abajo.');
          setIsRecording(false);
        } else if (event.error === 'network') {
          setErrorMessage('Error de red al procesar voz. Puedes escribir tu pedido abajo.');
          setIsRecording(false);
        }
      };

      recognition.onend = () => {
        setIsRecording(false);
      };

      recognition.start();
    } catch (err) {
      console.error('Failed to start speech recognition:', err);
      setIsRecording(false);
    }
  };

  const stopRecording = () => {
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop();
      } catch {
        // ignore
      }
      recognitionRef.current = null;
    }
    setIsRecording(false);
  };

  const toggleRecording = () => {
    if (isRecording) {
      stopRecording();
    } else {
      startRecording();
    }
  };

  const handleSubmit = async () => {
    const textToSubmit = transcript.trim();
    if (!textToSubmit) {
      setErrorMessage('Por favor dicta o escribe lo que deseas ordenar.');
      return;
    }

    if (!branchId) {
      setErrorMessage('No hay una sucursal seleccionada para el pedido.');
      return;
    }

    stopRecording();
    setIsLoading(true);
    setErrorMessage(null);

    try {
      const response = await fetch(`${API_BASE_URL}/storefront/orders/voice`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          transcript: textToSubmit,
          branch_id: branchId,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          typeof data.detail === 'string'
            ? data.detail
            : 'No se pudo interpretar el pedido por voz.'
        );
      }

      if (!data.items || !Array.isArray(data.items) || data.items.length === 0) {
        throw new Error(
          'No encontramos productos coincidentes en el menú. Intenta con nombres más específicos.'
        );
      }

      // Map returned items to actual products in catalog
      const newCartItems = data.items
        .map((item: any) => {
          const product = products.find((p: Product) => p.id === item.product_id);
          if (!product) return null;
          return {
            cart_id: Math.random().toString(36).substring(2, 9),
            product,
            quantity: item.quantity || 1,
            selected_options: [],
          };
        })
        .filter(Boolean);

      if (newCartItems.length === 0) {
        throw new Error(
          'No se pudieron relacionar los productos con el menú actual de la sucursal.'
        );
      }

      onAddCartItems(newCartItems);
      onClose();
    } catch (err: any) {
      console.error('Voice order submit error:', err);
      setErrorMessage(err.message || 'Ocurrió un error al procesar tu pedido.');
    } finally {
      setIsLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.65)',
        backdropFilter: 'blur(6px)',
        WebkitBackdropFilter: 'blur(6px)',
        zIndex: 10000,
        display: 'flex',
        alignItems: 'flex-end',
        justifyContent: 'center',
        padding: 0,
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget && !isLoading) {
          onClose();
        }
      }}
    >
      <div
        style={{
          backgroundColor: '#ffffff',
          width: '100%',
          maxWidth: '520px',
          borderTopLeftRadius: '24px',
          borderTopRightRadius: '24px',
          padding: '24px 20px',
          boxShadow: '0 -10px 40px rgba(0,0,0,0.2)',
          display: 'flex',
          flexDirection: 'column',
          maxHeight: '90vh',
        }}
      >
        {/* Header */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginBottom: '18px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div
              style={{
                width: '40px',
                height: '40px',
                borderRadius: '12px',
                background: 'linear-gradient(135deg, #f97316 0%, #ea580c 100%)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#fff',
              }}
            >
              <Sparkles size={22} />
            </div>
            <div>
              <h3 style={{ margin: 0, fontSize: '1.15rem', fontWeight: 800, color: '#1e293b' }}>
                Pedido por Voz
              </h3>
              <p style={{ margin: 0, fontSize: '0.8rem', color: '#64748b' }}>
                Dicta o escribe y la IA armará tu carrito
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={isLoading}
            style={{
              background: '#f1f5f9',
              border: 'none',
              borderRadius: '50%',
              width: '36px',
              height: '36px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: 'pointer',
              color: '#475569',
            }}
          >
            <X size={20} />
          </button>
        </div>

        {/* Mic Pulse Button & Live Indicator */}
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '16px 0',
            background: isRecording ? '#fef2f2' : '#f8fafc',
            borderRadius: '16px',
            border: isRecording ? '1.5px solid #fca5a5' : '1.5px dashed #cbd5e1',
            marginBottom: '16px',
            transition: 'all 0.2s ease',
          }}
        >
          <button
            type="button"
            onClick={toggleRecording}
            disabled={isLoading || !speechSupported}
            style={{
              width: '72px',
              height: '72px',
              borderRadius: '50%',
              border: 'none',
              background: isRecording
                ? 'linear-gradient(135deg, #ef4444 0%, #dc2626 100%)'
                : 'linear-gradient(135deg, #f97316 0%, #ea580c 100%)',
              color: '#ffffff',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: isRecording
                ? '0 0 0 8px rgba(239, 68, 68, 0.25), 0 8px 16px rgba(239, 68, 68, 0.4)'
                : '0 4px 12px rgba(249, 115, 22, 0.3)',
              cursor: speechSupported ? 'pointer' : 'not-allowed',
              transform: isRecording ? 'scale(1.05)' : 'scale(1)',
              transition: 'all 0.2s cubic-bezier(0.34, 1.56, 0.64, 1)',
            }}
          >
            {isRecording ? <Mic size={34} /> : <MicOff size={30} />}
          </button>

          <span
            style={{
              marginTop: '12px',
              fontSize: '0.9rem',
              fontWeight: 700,
              color: isRecording ? '#dc2626' : '#475569',
            }}
          >
            {isRecording
              ? '🔴 Escuchando... Di tu pedido'
              : speechSupported
              ? 'Toca el micrófono para dictar'
              : 'Micrófono no disponible en este navegador'}
          </span>

          <span style={{ fontSize: '0.75rem', color: '#94a3b8', marginTop: '4px' }}>
            {isRecording
              ? 'Toca el micrófono al terminar de hablar'
              : 'También puedes editar o escribir abajo'}
          </span>
        </div>

        {/* Transcript / Text Input Area */}
        <div style={{ position: 'relative', marginBottom: '14px' }}>
          <label
            style={{
              display: 'block',
              fontSize: '0.8rem',
              fontWeight: 700,
              color: '#334155',
              marginBottom: '6px',
            }}
          >
            Tu pedido dictado o escrito:
          </label>
          <textarea
            value={transcript}
            onChange={(e) => setTranscript(e.target.value)}
            disabled={isLoading}
            placeholder="Ej: Quiero 3 tacos al pastor, una gringa y una coca bien fría..."
            rows={3}
            style={{
              width: '100%',
              padding: '12px',
              borderRadius: '12px',
              border: '1.5px solid #cbd5e1',
              fontSize: '0.95rem',
              color: '#0f172a',
              resize: 'none',
              boxSizing: 'border-box',
              outline: 'none',
              fontFamily: 'inherit',
            }}
          />
          {transcript && !isLoading && (
            <button
              type="button"
              onClick={() => setTranscript('')}
              style={{
                position: 'absolute',
                right: '10px',
                bottom: '12px',
                background: '#f1f5f9',
                border: 'none',
                borderRadius: '6px',
                padding: '4px 8px',
                fontSize: '0.75rem',
                color: '#64748b',
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
                cursor: 'pointer',
              }}
            >
              <RotateCcw size={12} /> Borrar
            </button>
          )}
        </div>

        {/* Error message */}
        {errorMessage && (
          <div
            style={{
              backgroundColor: '#fef2f2',
              border: '1px solid #fecaca',
              borderRadius: '10px',
              padding: '10px 12px',
              fontSize: '0.825rem',
              color: '#b91c1c',
              marginBottom: '14px',
            }}
          >
            {errorMessage}
          </div>
        )}

        {/* Examples Pills */}
        {!transcript && (
          <div style={{ marginBottom: '16px' }}>
            <span style={{ fontSize: '0.75rem', color: '#94a3b8', display: 'block', marginBottom: '6px' }}>
              Ideas para probar:
            </span>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
              {[
                '3 tacos al pastor y una coca',
                'Una gringa y agua de horchata',
                '2 tacos sin cebolla',
              ].map((example) => (
                <button
                  key={example}
                  type="button"
                  onClick={() => setTranscript(example)}
                  style={{
                    background: '#f8fafc',
                    border: '1px solid #e2e8f0',
                    borderRadius: '20px',
                    padding: '4px 10px',
                    fontSize: '0.75rem',
                    color: '#475569',
                    cursor: 'pointer',
                  }}
                >
                  {example}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Submit Button */}
        <button
          type="button"
          onClick={handleSubmit}
          disabled={isLoading || !transcript.trim()}
          style={{
            width: '100%',
            padding: '15px',
            borderRadius: '14px',
            border: 'none',
            background:
              isLoading || !transcript.trim()
                ? '#cbd5e1'
                : 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
            color: '#ffffff',
            fontSize: '1rem',
            fontWeight: 800,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '8px',
            cursor: isLoading || !transcript.trim() ? 'not-allowed' : 'pointer',
            boxShadow:
              isLoading || !transcript.trim()
                ? 'none'
                : '0 4px 14px rgba(16, 185, 129, 0.35)',
            transition: 'all 0.2s ease',
          }}
        >
          {isLoading ? (
            <span>Interpretando pedido con IA...</span>
          ) : (
            <>
              <Sparkles size={20} />
              <span>Agregar al Carrito</span>
            </>
          )}
        </button>
      </div>
    </div>
  );
};
