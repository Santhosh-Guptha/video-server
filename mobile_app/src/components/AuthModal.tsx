import React, { useState } from 'react';
import { ShieldCheck, KeyRound, AlertCircle } from 'lucide-react';
import { verifyUserPin } from '../services/authService';

interface AuthModalProps {
  onUnlockSuccess: () => void;
}

export const AuthModal: React.FC<AuthModalProps> = ({ onUnlockSuccess }) => {
  const [pin, setPin] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleKeyPress = (num: string) => {
    if (pin.length < 4) {
      const newPin = pin + num;
      setPin(newPin);
      setError('');
      if (newPin.length === 4) {
        verifyPin(newPin);
      }
    }
  };

  const handleBackspace = () => {
    setPin(prev => prev.slice(0, -1));
    setError('');
  };

  const verifyPin = async (inputPin: string) => {
    setLoading(true);
    try {
      const isValid = await verifyUserPin(inputPin);
      if (isValid) {
        onUnlockSuccess();
      } else {
        setError('Incorrect Security PIN. Default PIN is 1234.');
        setPin('');
      }
    } catch (err) {
      setError('Authentication failed. Please try again.');
      setPin('');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-overlay">
      <div className="auth-card">
        <div className="auth-header">
          <div className="lock-icon-wrapper">
            <ShieldCheck className="w-10 h-10 text-emerald-400" />
          </div>
          <h2 className="auth-title">Godown Vision Security</h2>
          <p className="auth-subtitle">Enter your 4-digit PIN to access camera feeds</p>
        </div>

        {/* PIN Indicators */}
        <div className="pin-dots">
          {[0, 1, 2, 3].map((index) => (
            <div
              key={index}
              className={`pin-dot ${pin.length > index ? 'filled' : ''} ${error ? 'error' : ''}`}
            />
          ))}
        </div>

        {error && (
          <div className="auth-error-badge">
            <AlertCircle className="w-4 h-4 text-red-400" />
            <span>{error}</span>
          </div>
        )}

        {/* Numeric Keypad */}
        <div className="keypad-grid">
          {['1', '2', '3', '4', '5', '6', '7', '8', '9'].map((num) => (
            <button
              key={num}
              type="button"
              className="keypad-btn"
              onClick={() => handleKeyPress(num)}
              disabled={loading}
            >
              {num}
            </button>
          ))}
          <button
            type="button"
            className="keypad-btn secondary"
            onClick={() => setPin('')}
            disabled={loading}
          >
            Clear
          </button>
          <button
            type="button"
            className="keypad-btn"
            onClick={() => handleKeyPress('0')}
            disabled={loading}
          >
            0
          </button>
          <button
            type="button"
            className="keypad-btn secondary"
            onClick={handleBackspace}
            disabled={loading}
          >
            ⌫
          </button>
        </div>

        <div className="auth-footer-hint">
          <KeyRound className="w-3.5 h-3.5 text-slate-400" />
          <span>Default Demo PIN: <strong>1234</strong></span>
        </div>
      </div>
    </div>
  );
};
