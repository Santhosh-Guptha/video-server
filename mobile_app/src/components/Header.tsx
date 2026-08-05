import React from 'react';
import { Wifi, Globe, Lock, Video } from 'lucide-react';
import type { StreamMode } from '../types/camera';

interface HeaderProps {
  activeMode: StreamMode;
  onToggleMode: (mode: StreamMode) => void;
  onLockApp: () => void;
  isUnlocked: boolean;
  cameraCount: number;
}

export const Header: React.FC<HeaderProps> = ({
  activeMode,
  onToggleMode,
  onLockApp,
  isUnlocked,
  cameraCount
}) => {
  return (
    <header className="app-header">
      <div className="header-brand">
        <div className="brand-icon">
          <Video className="w-5 h-5 text-emerald-400" />
        </div>
        <div>
          <h1 className="brand-title">Godown Vision</h1>
          <span className="brand-subtitle">{cameraCount} Direct RTSP Cameras</span>
        </div>
      </div>

      <div className="header-actions">
        {/* Network Mode Switcher (Godown Wi-Fi vs Home DDNS) */}
        <div className="mode-toggle-group">
          <button
            type="button"
            className={`mode-btn ${activeMode === 'local' ? 'active-local' : ''}`}
            onClick={() => onToggleMode('local')}
            title="Local Wi-Fi Mode (Inside Godown)"
          >
            <Wifi className="w-3.5 h-3.5" />
            <span>Godown Wi-Fi</span>
          </button>
          <button
            type="button"
            className={`mode-btn ${activeMode === 'remote' ? 'active-remote' : ''}`}
            onClick={() => onToggleMode('remote')}
            title="Remote DDNS Mode (At Home / 4G)"
          >
            <Globe className="w-3.5 h-3.5" />
            <span>Home 4G/DDNS</span>
          </button>
        </div>

        {/* Security Lock Button */}
        {isUnlocked && (
          <button
            type="button"
            onClick={onLockApp}
            className="lock-btn"
            title="Lock Mobile App"
          >
            <Lock className="w-4 h-4 text-amber-400" />
          </button>
        )}
      </div>
    </header>
  );
};
