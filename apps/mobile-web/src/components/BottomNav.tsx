import React, { useState, useRef } from 'react';
import { Compass, Mic, Heart, ShoppingBag } from 'lucide-react';

export type NavTab = 'explore' | 'trending' | 'favorites' | 'cart';

interface BottomNavProps {
  currentTab: NavTab;
  onSelectTab: (tab: NavTab) => void;
  cartCount: number;
  favoritesCount: number;
}

export const BottomNav: React.FC<BottomNavProps> = ({
  currentTab,
  onSelectTab,
  cartCount,
  favoritesCount,
}) => {
  const [isRecording, setIsRecording] = useState(false);

  const handleDictate = async () => {
    const SpeechRecognition = window.SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      alert("Tu navegador no soporta reconocimiento de voz.");
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = 'es-MX';
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
      setIsRecording(true);
    };

    recognition.onresult = async (event: any) => {
      setIsRecording(false);
      const transcript = event.results[0][0].transcript;
      try {
        // Find branch_id from somewhere or assume it's available globally or in route
        // Assuming there is a global or we extract from URL. Let's get branch_id from window.location or similar.
        // The store is probably in useCart
        
        // Actually I will just dispatch an event and let App.tsx handle it, or fetch here.
        // Wait, the prompt says "agrégalo al estado global (useCart / Zustand si existe, o despacha un evento)".
        // I'll dispatch a custom event.
        const customEvent = new CustomEvent('voice-transcript-ready', { detail: { transcript } });
        window.dispatchEvent(customEvent);
      } catch (e) {
        console.error(e);
      }
    };

    recognition.onerror = () => {
      setIsRecording(false);
    };

    recognition.onend = () => {
      setIsRecording(false);
    };

    recognition.start();
  };

  return (
    <>
      {isRecording && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', justifyContent: 'center', alignItems: 'center', zIndex: 9999 }}>
          <div style={{ background: 'white', padding: '2rem', borderRadius: '1rem', textAlign: 'center' }}>
            <Mic size={48} color="red" />
            <p>Escuchando...</p>
          </div>
        </div>
      )}
      <nav className="mobile-bottom-nav" role="navigation" aria-label="Navegación principal">
        <div className="mobile-bottom-nav-glass">
          <button
            type="button"
            className={`mobile-nav-btn ${currentTab === 'explore' ? 'active' : ''}`}
            onClick={() => onSelectTab('explore')}
          >
            <Compass size={22} strokeWidth={currentTab === 'explore' ? 2.5 : 2} />
            <span>Menú</span>
          </button>

          <button
            type="button"
            className={`mobile-nav-btn`}
            onClick={handleDictate}
          >
            <Mic
              size={22}
              color={isRecording ? 'red' : 'currentColor'}
              strokeWidth={2}
            />
            <span>Dictar</span>
          </button>

          <button
            type="button"
            className={`mobile-nav-btn ${currentTab === 'favorites' ? 'active' : ''}`}
            onClick={() => onSelectTab('favorites')}
          >
            <div className="mobile-nav-icon-container">
              <Heart
                size={22}
                fill={currentTab === 'favorites' ? '#ef4444' : 'none'}
                strokeWidth={currentTab === 'favorites' ? 2.5 : 2}
              />
              {favoritesCount > 0 && (
                <span className="mobile-nav-badge-count">{favoritesCount}</span>
              )}
            </div>
            <span>Favoritos</span>
          </button>

          <button
            type="button"
            className={`mobile-nav-btn ${currentTab === 'cart' ? 'active' : ''}`}
            onClick={() => onSelectTab('cart')}
          >
            <div className="mobile-nav-icon-container">
              <ShoppingBag size={22} strokeWidth={currentTab === 'cart' ? 2.5 : 2} />
              {cartCount > 0 && (
                <span className="mobile-nav-badge-count green">{cartCount}</span>
              )}
            </div>
            <span>Carrito</span>
          </button>
        </div>
      </nav>
    </>
  );
};
