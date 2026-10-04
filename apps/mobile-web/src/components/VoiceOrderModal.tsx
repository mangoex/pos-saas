import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Check, Loader2, Mic, MicOff, RotateCcw, Sparkles, Volume2, X } from 'lucide-react';
import { CartItem, Product } from '../types';
import {
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

const API_BASE_URL = '/api/v1';
const MAX_RECORDING_SECONDS = 30;

const getSupportedMimeType = (): string => {
  if (typeof window === 'undefined' || typeof MediaRecorder === 'undefined') return '';
  const candidates = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/mp4',
    'audio/aac',
    'audio/ogg;codecs=opus',
  ];
  for (const candidate of candidates) {
    if (MediaRecorder.isTypeSupported(candidate)) return candidate;
  }
  return '';
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
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [volumeLevel, setVolumeLevel] = useState(0);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [speechSupported, setSpeechSupported] = useState(true);
  const [draft, setDraft] = useState<VoiceOrderDraft | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const timerIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const animFrameRef = useRef<number | null>(null);
  const sessionTokenRef = useRef(0);

  const isInAppBrowser = useMemo(() => {
    if (typeof window === 'undefined' || !navigator?.userAgent) return false;
    return /WhatsApp|FBAN|FBAV|Instagram|TikTok|Line|MicroMessenger/i.test(navigator.userAgent);
  }, []);

  const cleanupAudioStream = () => {
    if (timerIntervalRef.current) {
      clearInterval(timerIntervalRef.current);
      timerIntervalRef.current = null;
    }
    if (animFrameRef.current) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = null;
    }
    if (audioContextRef.current) {
      try {
        void audioContextRef.current.close();
      } catch {
        // Safe context close
      }
      audioContextRef.current = null;
    }
    const stream = mediaStreamRef.current;
    if (stream) {
      try {
        stream.getTracks().forEach((track) => track.stop());
      } catch {
        // Safe stream cleanup
      }
      mediaStreamRef.current = null;
    }
    setVolumeLevel(0);
  };

  const stopRecording = (discard = false) => {
    if (discard) {
      sessionTokenRef.current += 1;
      cleanupAudioStream();
      const recorder = mediaRecorderRef.current;
      mediaRecorderRef.current = null;
      if (recorder && recorder.state !== 'inactive') {
        try {
          recorder.ondataavailable = null;
          recorder.onstop = null;
          recorder.stop();
        } catch {
          // Safe recorder stop
        }
      }
      setIsRecording(false);
      setIsStarting(false);
      setRecordingSeconds(0);
      return;
    }

    // Normal user finish: stop timer, switch UI to interpreting, and let recorder.stop trigger onstop
    if (timerIntervalRef.current) {
      clearInterval(timerIntervalRef.current);
      timerIntervalRef.current = null;
    }
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== 'inactive') {
      try {
        recorder.stop();
      } catch {
        // Safe recorder stop
      }
    }
    setIsRecording(false);
    setIsStarting(false);
    setIsLoading(true);
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
    const hasMediaDevices = typeof window !== 'undefined'
      && Boolean(navigator?.mediaDevices?.getUserMedia)
      && typeof MediaRecorder !== 'undefined';
    setSpeechSupported(hasMediaDevices);
    if (!hasMediaDevices) {
      setErrorMessage('Tu navegador no admite grabación de audio directa. Puedes escribir tu pedido en el cuadro.');
    }
    return () => {
      stopRecording(true);
    };
  }, [isOpen]);

  const handleSendAudio = async (audioBase64: string, mimeType: string, token: number) => {
    if (!publicKey) {
      setErrorMessage('La sucursal no está disponible para pedidos por voz.');
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    setErrorMessage(null);
    setDraft(null);
    try {
      const response = await fetch(
        `${API_BASE_URL}/public/branches/${encodeURIComponent(publicKey)}/voice-audio-draft`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            audio_base64: audioBase64,
            mime_type: mimeType,
          }),
        },
      );
      if (sessionTokenRef.current !== token) return;
      const data: unknown = await response.json().catch(() => null);
      if (!response.ok) throw new Error(errorFromResponse(data));
      const result = data as VoiceOrderDraft & { transcript?: string };
      if (result.transcript) {
        setTranscript(result.transcript);
      }
      setDraft(result);
    } catch (error) {
      if (sessionTokenRef.current === token) {
        setErrorMessage(
          error instanceof Error
            ? error.message
            : 'No se pudo interpretar el audio. Puedes escribir tu pedido directamente.',
        );
      }
    } finally {
      if (sessionTokenRef.current === token) {
        setIsLoading(false);
      }
    }
  };

  const startRecording = async () => {
    if (isRecording) {
      stopRecording(false);
      return;
    }
    if (isStarting || isLoading) return;

    if (!navigator?.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      setSpeechSupported(false);
      setErrorMessage('Tu dispositivo no soporta grabación de audio. Puedes escribir tu pedido.');
      return;
    }

    setIsStarting(true);
    setErrorMessage(null);
    setDraft(null);
    audioChunksRef.current = [];

    const token = sessionTokenRef.current + 1;
    sessionTokenRef.current = token;

    try {
      let stream: MediaStream;
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: true, noiseSuppression: true },
        });
      } catch {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      }

      if (sessionTokenRef.current !== token) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }

      mediaStreamRef.current = stream;

      // Audio volume meter for real-time visual feedback
      try {
        const AudioCtx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
        if (AudioCtx) {
          const audioCtx = new AudioCtx();
          audioContextRef.current = audioCtx;
          const analyser = audioCtx.createAnalyser();
          analyser.fftSize = 64;
          const source = audioCtx.createMediaStreamSource(stream);
          source.connect(analyser);
          const dataArray = new Uint8Array(analyser.frequencyBinCount);

          const updateVolume = () => {
            if (mediaStreamRef.current !== stream) return;
            analyser.getByteFrequencyData(dataArray);
            let sum = 0;
            for (let i = 0; i < dataArray.length; i += 1) {
              sum += dataArray[i];
            }
            const avg = sum / dataArray.length;
            setVolumeLevel(Math.min(100, Math.round((avg / 128) * 100)));
            animFrameRef.current = requestAnimationFrame(updateVolume);
          };
          updateVolume();
        }
      } catch {
        // Visualizer is purely enhancement
      }

      const mimeType = getSupportedMimeType();
      const recorderOptions: MediaRecorderOptions = mimeType ? { mimeType } : {};
      const recorder = new MediaRecorder(stream, recorderOptions);
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (event: BlobEvent) => {
        if (event.data && event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      recorder.onstop = () => {
        cleanupAudioStream();
        if (sessionTokenRef.current !== token) return;
        const recordedBlob = new Blob(audioChunksRef.current, {
          type: recorder.mimeType || mimeType || 'audio/webm',
        });
        if (recordedBlob.size < 100) {
          setIsLoading(false);
          setErrorMessage('La grabación fue muy breve. Toca el micrófono para intentar de nuevo.');
          return;
        }
        const reader = new FileReader();
        reader.onloadend = () => {
          if (sessionTokenRef.current !== token) return;
          const resultStr = typeof reader.result === 'string' ? reader.result : '';
          const commaIndex = resultStr.indexOf(',');
          const base64Data = commaIndex >= 0 ? resultStr.substring(commaIndex + 1) : resultStr;
          void handleSendAudio(base64Data, recordedBlob.type || 'audio/webm', token);
        };
        reader.readAsDataURL(recordedBlob);
      };

      recorder.start(250);
      setIsStarting(false);
      setIsRecording(true);
      setRecordingSeconds(0);

      // Duration counter and safety auto-stop at MAX_RECORDING_SECONDS
      let elapsed = 0;
      timerIntervalRef.current = setInterval(() => {
        elapsed += 1;
        setRecordingSeconds(elapsed);
        if (elapsed >= MAX_RECORDING_SECONDS) {
          stopRecording(false);
        }
      }, 1000);
    } catch {
      cleanupAudioStream();
      setIsStarting(false);
      setIsRecording(false);
      setErrorMessage('No se pudo acceder al micrófono. Verifica los permisos de tu navegador o escribe tu pedido abajo.');
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
    stopRecording(true);
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
            <div><h3 style={{ margin: 0, color: '#1e293b', fontSize: '1.15rem' }}>Pedido por voz</h3><p style={{ margin: 0, color: '#64748b', fontSize: '.8rem' }}>Graba tu audio o escribe tu pedido</p></div>
          </div>
          <button type="button" onClick={onClose} disabled={isLoading} aria-label="Cerrar" style={{ border: 0, borderRadius: '50%', width: 36, height: 36, color: '#475569', background: '#f1f5f9' }}><X size={20} /></button>
        </header>

        {isInAppBrowser && (
          <div
            style={{
              marginBottom: 12,
              padding: '8px 12px',
              borderRadius: 10,
              background: '#fef3c7',
              border: '1px solid #fde68a',
              color: '#92400e',
              fontSize: '.78rem',
              lineHeight: 1.35,
            }}
          >
            Estás navegando dentro de una aplicación (WhatsApp/Instagram). Puedes grabar tu nota de voz o escribir tu pedido directamente abajo.
          </div>
        )}

        <div style={{ display: 'grid', placeItems: 'center', padding: '16px 0', marginBottom: 14, border: `1.5px ${isRecording ? 'solid #fca5a5' : 'dashed #cbd5e1'}`, borderRadius: 16, background: isRecording ? '#fef2f2' : '#f8fafc' }}>
          <button
            type="button"
            onClick={startRecording}
            disabled={isLoading || isStarting || !speechSupported}
            aria-label={isRecording ? 'Detener grabación y enviar' : 'Iniciar grabación'}
            style={{
              display: 'grid',
              placeItems: 'center',
              width: 76,
              height: 76,
              border: 0,
              borderRadius: '50%',
              color: '#fff',
              background: isRecording ? '#dc2626' : isStarting ? '#f97316' : '#ea580c',
              cursor: speechSupported ? 'pointer' : 'not-allowed',
              boxShadow: isRecording
                ? `0 0 0 ${8 + Math.round(volumeLevel * 0.12)}px rgba(220, 38, 38, ${0.2 + (volumeLevel / 200)})`
                : 'none',
              transition: 'box-shadow 0.1s ease, background 0.2s ease',
            }}
          >
            {isLoading ? <Loader2 size={34} className="animate-spin" /> : isRecording ? <MicOff size={34} /> : <Mic size={34} />}
          </button>

          <strong style={{ marginTop: 12, color: isRecording ? '#dc2626' : isLoading ? '#ea580c' : '#475569', fontSize: '.88rem' }}>
            {isRecording
              ? `Grabando… ${recordingSeconds}s / ${MAX_RECORDING_SECONDS}s (toca para enviar)`
              : isStarting
              ? 'Iniciando micrófono…'
              : isLoading
              ? 'Interpretando audio con IA…'
              : speechSupported
              ? 'Toca para grabar nota de voz'
              : 'Escribe tu pedido abajo'}
          </strong>

          {isRecording && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 6, color: '#dc2626', fontSize: '.78rem' }}>
              <Volume2 size={15} />
              <span>Micrófono captando audio {volumeLevel > 5 ? '🎙️' : '...'}</span>
            </div>
          )}
        </div>

        <label style={{ display: 'block', color: '#334155', fontSize: '.8rem', fontWeight: 700, marginBottom: 6 }}>Tu pedido dictado o escrito</label>
        <div style={{ position: 'relative', marginBottom: 12 }}>
          <textarea
            value={transcript}
            maxLength={1000}
            rows={3}
            disabled={isLoading || isRecording}
            onChange={(event) => { setTranscript(event.target.value); setDraft(null); setErrorMessage(null); }}
            placeholder="Ejemplo: dos hamburguesas y una limonada"
            style={{ width: '100%', boxSizing: 'border-box', resize: 'vertical', border: '1.5px solid #cbd5e1', borderRadius: 12, padding: 12, font: 'inherit' }}
          />
          {transcript && !isLoading && !isRecording && (
            <button
              type="button"
              onClick={() => { setTranscript(''); setDraft(null); }}
              style={{ position: 'absolute', right: 8, bottom: 8, display: 'flex', gap: 4, border: 0, borderRadius: 6, padding: '4px 8px', color: '#64748b', background: '#f1f5f9' }}
            >
              <RotateCcw size={12} /> Borrar
            </button>
          )}
        </div>

        {errorMessage && <div role="alert" style={{ marginBottom: 12, padding: '10px 12px', border: '1px solid #fecaca', borderRadius: 10, color: '#b91c1c', background: '#fef2f2', fontSize: '.82rem' }}>{errorMessage}</div>}

        {draft && draft.unmatched_items && draft.unmatched_items.length > 0 && (
          <div
            role="alert"
            style={{
              marginBottom: 12,
              padding: '12px 14px',
              borderRadius: 12,
              background: '#fffbeb',
              border: '1.5px solid #f59e0b',
              color: '#92400e',
              boxShadow: '0 2px 6px rgba(245,158,11,0.08)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 700, fontSize: '.9rem', marginBottom: 4 }}>
              <span style={{ fontSize: '1.15rem' }}>⚠️</span>
              <span>No disponible en el menú:</span>
            </div>
            <p style={{ margin: 0, fontSize: '.84rem', lineHeight: 1.4 }}>
              No se incluyó:{' '}
              <b style={{ color: '#b45309' }}>{draft.unmatched_items.join(', ')}</b>{' '}
              porque no forma parte del menú de este restaurante. Abajo puedes revisar los productos que sí se agregaron al borrador.
            </p>
          </div>
        )}

        {draft && (
          <div style={{ marginBottom: 14, padding: 12, border: '1px solid #bbf7d0', borderRadius: 12, background: '#f0fdf4' }}>
            <strong style={{ color: '#166534' }}>Borrador para revisar</strong>
            {draft.lines.map((line, index) => (
              <div key={`${line.product_id}-${index}`} style={{ marginTop: 8, color: '#334155' }}>
                <b>{line.quantity} × {line.product_name}</b>
                {line.selected_options.length > 0 && (
                  <div style={{ fontSize: '.78rem', color: '#64748b' }}>
                    {line.selected_options.map((option) => option.option_name).join(', ')}
                  </div>
                )}
              </div>
            ))}
            {optionGroups.map((question) => (
              <fieldset key={`${question.line_index}-${question.group_id}`} style={{ marginTop: 12, border: 0, padding: 0 }}>
                <legend style={{ fontSize: '.82rem', fontWeight: 700, color: '#334155' }}>{question.prompt}</legend>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7, marginTop: 7 }}>
                  {question.options.map((option) => {
                    const selected = draft.lines[question.line_index]?.selected_options.some(
                      (candidate) => candidate.group_id === question.group_id && candidate.option_id === option.id,
                    );
                    return (
                      <button
                        key={option.id}
                        type="button"
                        aria-pressed={selected}
                        onClick={() => setDraft((current) => (current ? toggleVoiceDraftOption(current, question, option) : current))}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 5,
                          border: `1px solid ${selected ? '#16a34a' : '#cbd5e1'}`,
                          borderRadius: 999,
                          padding: '7px 10px',
                          color: selected ? '#166534' : '#475569',
                          background: selected ? '#dcfce7' : '#fff',
                        }}
                      >
                        {selected && <Check size={14} />}
                        {option.name}
                      </button>
                    );
                  })}
                </div>
              </fieldset>
            ))}
          </div>
        )}

        {!draft ? (
          <button
            type="button"
            onClick={() => void handleSubmit()}
            disabled={isLoading || isRecording || !transcript.trim()}
            style={{
              width: '100%',
              padding: 14,
              border: 0,
              borderRadius: 14,
              color: '#fff',
              fontWeight: 800,
              background: isLoading || isRecording || !transcript.trim() ? '#cbd5e1' : 'linear-gradient(135deg,#10b981,#059669)',
            }}
          >
            {isLoading ? 'Interpretando…' : 'Crear borrador con texto'}
          </button>
        ) : (
          <button
            type="button"
            onClick={applyDraft}
            disabled={!complete}
            style={{
              width: '100%',
              padding: 14,
              border: 0,
              borderRadius: 14,
              color: '#fff',
              fontWeight: 800,
              background: complete ? 'linear-gradient(135deg,#10b981,#059669)' : '#cbd5e1',
            }}
          >
            {complete ? 'Agregar borrador al carrito' : 'Completa las opciones requeridas'}
          </button>
        )}
      </section>
    </div>
  );
};
