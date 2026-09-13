import React, { useEffect, useRef, useState } from 'react';
import { Check, Mic, MicOff, RotateCcw, Sparkles, X } from 'lucide-react';
import { CartItem, Product } from '../types';
import {
  appendVoiceTranscript,
  isVoiceDraftComplete,
  toggleVoiceDraftOption,
  voiceDraftToCartItems,
  type VoiceOrderDraft,
} from '../features/voice/voiceOrderDraft';

interface VoiceOrderModalProps {
  isOpen: boolean;
  onClose: () => void;
  publicKey: string | null;
  products: Product[];
  onAddCartItems: (newItems: CartItem[]) => void;
}

interface SpeechRecognitionResultEventLike {
  results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }>;
}

interface SpeechRecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  onstart: (() => void) | null;
  onresult: ((event: SpeechRecognitionResultEventLike) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
}

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;

const API_BASE_URL = '/api/v1';

const getSpeechRecognition = (): SpeechRecognitionConstructor | null => {
  const browserWindow = window as typeof window & {
    SpeechRecognition?: SpeechRecognitionConstructor;
    webkitSpeechRecognition?: SpeechRecognitionConstructor;
  };
  return browserWindow.SpeechRecognition || browserWindow.webkitSpeechRecognition || null;
};

const errorFromResponse = (data: unknown): string => {
  if (!data || typeof data !== 'object') return 'No se pudo interpretar el pedido.';
  const detail = (data as { detail?: unknown }).detail;
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object') {
    const message = (detail as { message?: unknown }).message;
    if (typeof message === 'string') return message;
  }
  return 'No se pudo interpretar el pedido. Intenta escribirlo de otra forma.';
};

export const VoiceOrderModal: React.FC<VoiceOrderModalProps> = ({
  isOpen,
  onClose,
  publicKey,
  products,
  onAddCartItems,
}) => {
  const [transcript, setTranscript] = useState('');
  const [isRecording, setIsRecording] = useState(false);
  const [isStarting, setIsStarting] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [speechSupported, setSpeechSupported] = useState(true);
  const [draft, setDraft] = useState<VoiceOrderDraft | null>(null);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const sessionTokenRef = useRef(0);
  const baseTranscriptRef = useRef('');

  const stopRecording = (abort = false) => {
    sessionTokenRef.current += 1;
    const recognition = recognitionRef.current;
    recognitionRef.current = null;
    if (recognition) {
      try {
        if (abort) recognition.abort();
        else recognition.stop();
      } catch {
        // The browser may have already ended the recognition session.
      }
    }
    setIsRecording(false);
    setIsStarting(false);
  };

  useEffect(() => {
    if (!isOpen) {
      stopRecording(true);
      setTranscript('');
      setDraft(null);
      setErrorMessage(null);
      setIsLoading(false);
      return;
    }
    const supported = Boolean(getSpeechRecognition());
    setSpeechSupported(supported);
    if (!supported) {
      setErrorMessage('Tu navegador no soporta reconocimiento de voz. Puedes escribir tu pedido.');
    }
    return () => stopRecording(true);
  }, [isOpen]);

  const startRecording = () => {
    if (isRecording || isStarting || isLoading) return;
    const SpeechRecognition = getSpeechRecognition();
    if (!SpeechRecognition) {
      setSpeechSupported(false);
      setErrorMessage('Tu navegador no soporta reconocimiento de voz. Puedes escribir tu pedido.');
      return;
    }
    stopRecording(true);
    setIsStarting(true);
    setErrorMessage(null);
    setDraft(null);
    const token = sessionTokenRef.current;
    const recognition = new SpeechRecognition();
    recognitionRef.current = recognition;
    baseTranscriptRef.current = transcript.trim();
    recognition.lang = 'es-MX';
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;
    recognition.onstart = () => {
      if (sessionTokenRef.current !== token || recognitionRef.current !== recognition) return;
      setIsStarting(false);
      setIsRecording(true);
    };
    recognition.onresult = (event) => {
      if (sessionTokenRef.current !== token || recognitionRef.current !== recognition) return;
      let recognized = '';
      for (let index = 0; index < event.results.length; index += 1) {
        recognized += `${event.results[index][0].transcript} `;
      }
      setTranscript(appendVoiceTranscript(baseTranscriptRef.current, recognized));
    };
    recognition.onerror = (event) => {
      if (sessionTokenRef.current !== token || recognitionRef.current !== recognition) return;
      const messages: Record<string, string> = {
        'not-allowed': 'Permiso de micrófono denegado. Puedes escribir tu pedido.',
        network: 'No se pudo usar el servicio de voz. Tu texto permanece disponible.',
        'no-speech': 'No se escuchó voz. Toca de nuevo o escribe tu pedido.',
      };
      setErrorMessage(messages[event.error] || 'No se pudo continuar el dictado. Puedes escribir tu pedido.');
      setIsStarting(false);
      setIsRecording(false);
    };
    recognition.onend = () => {
      if (sessionTokenRef.current !== token || recognitionRef.current !== recognition) return;
      recognitionRef.current = null;
      setIsStarting(false);
      setIsRecording(false);
    };
    try {
      recognition.start();
    } catch {
      if (sessionTokenRef.current === token) {
        recognitionRef.current = null;
        setIsStarting(false);
        setErrorMessage('No se pudo activar el micrófono. Puedes escribir tu pedido.');
      }
    }
  };

  const handleSubmit = async () => {
    const text = transcript.trim();
    if (!text) {
      setErrorMessage('Dicta o escribe lo que deseas ordenar.');
      return;
    }
    if (!publicKey) {
      setErrorMessage('La sucursal no está disponible para pedidos asistidos.');
      return;
    }
    stopRecording();
    setIsLoading(true);
    setErrorMessage(null);
    setDraft(null);
    try {
      const response = await fetch(
        `${API_BASE_URL}/public/branches/${encodeURIComponent(publicKey)}/voice-order-draft`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text }),
        },
      );
      const data: unknown = await response.json().catch(() => null);
      if (!response.ok) throw new Error(errorFromResponse(data));
      setDraft(data as VoiceOrderDraft);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Ocurrió un error al procesar tu pedido.');
    } finally {
      setIsLoading(false);
    }
  };

  const applyDraft = () => {
    if (!draft || !isVoiceDraftComplete(draft)) return;
    try {
      const items = voiceDraftToCartItems(draft, products);
      onAddCartItems(items);
      onClose();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'No se pudo agregar el borrador.');
    }
  };

  if (!isOpen) return null;
  const complete = draft ? isVoiceDraftComplete(draft) : false;
  const optionGroups = draft?.option_groups ?? draft?.questions ?? [];

  return (
    <div
      role="presentation"
      onClick={(event) => event.target === event.currentTarget && !isLoading && onClose()}
      style={{ position: 'fixed', inset: 0, zIndex: 10000, display: 'flex', alignItems: 'flex-end', justifyContent: 'center', background: 'rgba(0,0,0,.65)', backdropFilter: 'blur(6px)' }}
    >
      <section role="dialog" aria-modal="true" aria-label="Pedido asistido por voz" style={{ width: '100%', maxWidth: 520, maxHeight: '92vh', overflowY: 'auto', boxSizing: 'border-box', borderRadius: '24px 24px 0 0', padding: '22px 20px', background: '#fff', boxShadow: '0 -10px 40px rgba(0,0,0,.2)' }}>
        <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, marginBottom: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ display: 'grid', placeItems: 'center', width: 40, height: 40, borderRadius: 12, color: '#fff', background: 'linear-gradient(135deg,#f97316,#ea580c)' }}><Sparkles size={22} /></span>
            <div><h3 style={{ margin: 0, color: '#1e293b', fontSize: '1.15rem' }}>Pedido por voz</h3><p style={{ margin: 0, color: '#64748b', fontSize: '.8rem' }}>Revisa el borrador antes de agregarlo</p></div>
          </div>
          <button type="button" onClick={onClose} disabled={isLoading} aria-label="Cerrar" style={{ border: 0, borderRadius: '50%', width: 36, height: 36, color: '#475569', background: '#f1f5f9' }}><X size={20} /></button>
        </header>

        <div style={{ display: 'grid', placeItems: 'center', padding: '14px 0', marginBottom: 14, border: `1.5px ${isRecording ? 'solid #fca5a5' : 'dashed #cbd5e1'}`, borderRadius: 16, background: isRecording ? '#fef2f2' : '#f8fafc' }}>
          <button type="button" onClick={() => isRecording ? stopRecording() : startRecording()} disabled={isLoading || isStarting || !speechSupported} aria-label={isRecording ? 'Detener dictado' : 'Iniciar dictado'} style={{ display: 'grid', placeItems: 'center', width: 68, height: 68, border: 0, borderRadius: '50%', color: '#fff', background: isRecording ? '#dc2626' : '#ea580c', cursor: speechSupported ? 'pointer' : 'not-allowed' }}>
            {isRecording ? <MicOff size={30} /> : <Mic size={30} />}
          </button>
          <strong style={{ marginTop: 9, color: isRecording ? '#dc2626' : '#475569', fontSize: '.86rem' }}>{isRecording ? 'Escuchando…' : isStarting ? 'Activando micrófono…' : speechSupported ? 'Toca para dictar' : 'Escribe tu pedido abajo'}</strong>
        </div>

        <label style={{ display: 'block', color: '#334155', fontSize: '.8rem', fontWeight: 700, marginBottom: 6 }}>Tu pedido dictado o escrito</label>
        <div style={{ position: 'relative', marginBottom: 12 }}>
          <textarea value={transcript} maxLength={1000} rows={3} disabled={isLoading} onChange={(event) => { setTranscript(event.target.value); setDraft(null); setErrorMessage(null); }} placeholder="Ejemplo: dos hamburguesas y una limonada" style={{ width: '100%', boxSizing: 'border-box', resize: 'vertical', border: '1.5px solid #cbd5e1', borderRadius: 12, padding: 12, font: 'inherit' }} />
          {transcript && !isLoading && <button type="button" onClick={() => { setTranscript(''); setDraft(null); }} style={{ position: 'absolute', right: 8, bottom: 8, display: 'flex', gap: 4, border: 0, borderRadius: 6, padding: '4px 8px', color: '#64748b', background: '#f1f5f9' }}><RotateCcw size={12} /> Borrar</button>}
        </div>

        {errorMessage && <div role="alert" style={{ marginBottom: 12, padding: '10px 12px', border: '1px solid #fecaca', borderRadius: 10, color: '#b91c1c', background: '#fef2f2', fontSize: '.82rem' }}>{errorMessage}</div>}

        {draft && <div style={{ marginBottom: 14, padding: 12, border: '1px solid #bbf7d0', borderRadius: 12, background: '#f0fdf4' }}>
          <strong style={{ color: '#166534' }}>Borrador para revisar</strong>
          {draft.lines.map((line, index) => <div key={`${line.product_id}-${index}`} style={{ marginTop: 8, color: '#334155' }}><b>{line.quantity} × {line.product_name}</b>{line.selected_options.length > 0 && <div style={{ fontSize: '.78rem', color: '#64748b' }}>{line.selected_options.map((option) => option.option_name).join(', ')}</div>}</div>)}
          {optionGroups.map((question) => <fieldset key={`${question.line_index}-${question.group_id}`} style={{ marginTop: 12, border: 0, padding: 0 }}><legend style={{ fontSize: '.82rem', fontWeight: 700, color: '#334155' }}>{question.prompt}</legend><div style={{ display: 'flex', flexWrap: 'wrap', gap: 7, marginTop: 7 }}>{question.options.map((option) => {
            const selected = draft.lines[question.line_index]?.selected_options.some((candidate) => candidate.group_id === question.group_id && candidate.option_id === option.id);
            return <button key={option.id} type="button" aria-pressed={selected} onClick={() => setDraft((current) => current ? toggleVoiceDraftOption(current, question, option) : current)} style={{ display: 'flex', alignItems: 'center', gap: 5, border: `1px solid ${selected ? '#16a34a' : '#cbd5e1'}`, borderRadius: 999, padding: '7px 10px', color: selected ? '#166534' : '#475569', background: selected ? '#dcfce7' : '#fff' }}>{selected && <Check size={14} />}{option.name}</button>;
          })}</div></fieldset>)}
          {draft.unmatched_items && draft.unmatched_items.length > 0 && (
            <div style={{ marginTop: 10, padding: '8px 10px', borderRadius: 8, background: '#fffbeb', border: '1px solid #fde68a', color: '#92400e', fontSize: '.78rem' }}>
              ⚠️ No disponibles en el menú: {draft.unmatched_items.join(', ')}
            </div>
          )}
        </div>}

        {!draft ? <button type="button" onClick={() => void handleSubmit()} disabled={isLoading || !transcript.trim()} style={{ width: '100%', padding: 14, border: 0, borderRadius: 14, color: '#fff', fontWeight: 800, background: isLoading || !transcript.trim() ? '#cbd5e1' : 'linear-gradient(135deg,#10b981,#059669)' }}>{isLoading ? 'Interpretando…' : 'Crear borrador'}</button>
          : <button type="button" onClick={applyDraft} disabled={!complete} style={{ width: '100%', padding: 14, border: 0, borderRadius: 14, color: '#fff', fontWeight: 800, background: complete ? 'linear-gradient(135deg,#10b981,#059669)' : '#cbd5e1' }}>{complete ? 'Agregar borrador al carrito' : 'Completa las opciones requeridas'}</button>}
      </section>
    </div>
  );
};
