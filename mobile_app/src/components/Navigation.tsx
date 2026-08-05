import React from 'react';
import { Video, History, Camera, Settings } from 'lucide-react';

export type NavTab = 'live' | 'playback' | 'cameras' | 'settings';

interface NavigationProps {
  activeTab: NavTab;
  onTabChange: (tab: NavTab) => void;
}

export const Navigation: React.FC<NavigationProps> = ({ activeTab, onTabChange }) => {
  const navItems: { id: NavTab; label: string; icon: React.ReactNode }[] = [
    { id: 'live', label: 'Live Stream', icon: <Video className="w-5 h-5" /> },
    { id: 'playback', label: 'NVR Playback', icon: <History className="w-5 h-5" /> },
    { id: 'cameras', label: 'Cameras', icon: <Camera className="w-5 h-5" /> },
    { id: 'settings', label: 'Settings', icon: <Settings className="w-5 h-5" /> }
  ];

  return (
    <nav className="mobile-nav">
      {navItems.map((item) => {
        const isActive = activeTab === item.id;
        return (
          <button
            key={item.id}
            type="button"
            className={`nav-tab ${isActive ? 'active' : ''}`}
            onClick={() => onTabChange(item.id)}
          >
            <div className="nav-icon">{item.icon}</div>
            <span className="nav-label">{item.label}</span>
          </button>
        );
      })}
    </nav>
  );
};
