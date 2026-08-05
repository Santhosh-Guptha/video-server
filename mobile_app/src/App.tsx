import { useState, useEffect } from 'react';
import { useLiveQuery } from 'dexie-react-hooks';
import { db, seedInitialData, loadUserNvrConfig } from './db/database';
import type { CameraConfig, StreamMode } from './types/camera';
import { isSessionUnlocked, setLocalSessionUnlocked } from './services/authService';

import { Header } from './components/Header';
import { Navigation, type NavTab } from './components/Navigation';
import { AuthModal } from './components/AuthModal';
import { CameraFormModal } from './components/CameraFormModal';
import { LiveView } from './components/LiveView';
import { PlaybackView } from './components/PlaybackView';
import { CameraList } from './components/CameraList';
import { SettingsView } from './components/SettingsView';

export function App() {
  const [activeTab, setActiveTab] = useState<NavTab>('live');
  const [activeMode, setActiveMode] = useState<StreamMode>('remote');
  const [isUnlocked, setIsUnlocked] = useState<boolean>(false);
  const [showAddForm, setShowAddForm] = useState<boolean>(false);
  const [editingCamera, setEditingCamera] = useState<CameraConfig | null>(null);
  const [selectedLiveCam, setSelectedLiveCam] = useState<CameraConfig | null>(null);

  // Load cameras from IndexedDB using Dexie react hook
  const cameras = useLiveQuery(() => db.cameras.toArray()) || [];

  useEffect(() => {
    // Populate user's explicit NVR payload (182.76.136.44:8554, channels 101, 201, 401)
    loadUserNvrConfig();
    seedInitialData();
    setIsUnlocked(isSessionUnlocked());
  }, []);

  const handleUnlockSuccess = () => {
    setLocalSessionUnlocked(true);
    setIsUnlocked(true);
  };

  const handleLockApp = () => {
    setLocalSessionUnlocked(false);
    setIsUnlocked(false);
  };

  const handleSaveCamera = async (camData: Omit<CameraConfig, 'id' | 'createdAt' | 'updatedAt'>) => {
    const now = new Date().toISOString();
    if (editingCamera && editingCamera.id) {
      await db.cameras.update(editingCamera.id, {
        ...camData,
        updatedAt: now
      });
    } else {
      await db.cameras.add({
        ...camData,
        createdAt: now,
        updatedAt: now
      });
    }
    setEditingCamera(null);
    setShowAddForm(false);
  };

  const handleDeleteCamera = async (id: number) => {
    if (window.confirm('Are you sure you want to delete this camera?')) {
      await db.cameras.delete(id);
    }
  };

  const handleSelectLive = (cam: CameraConfig) => {
    setSelectedLiveCam(cam);
    setActiveTab('live');
  };

  return (
    <div className="mobile-app-shell">
      {/* Security PIN Lock Overlay */}
      {!isUnlocked && <AuthModal onUnlockSuccess={handleUnlockSuccess} />}

      {/* App Header */}
      <Header
        activeMode={activeMode}
        onToggleMode={(mode) => setActiveMode(mode)}
        onLockApp={handleLockApp}
        isUnlocked={isUnlocked}
        cameraCount={cameras.length}
      />

      {/* Main Viewport Content */}
      <main className="app-content">
        {activeTab === 'live' && (
          <LiveView
            cameras={cameras}
            activeMode={activeMode}
            selectedCamera={selectedLiveCam}
            onSelectCamera={(cam) => setSelectedLiveCam(cam)}
          />
        )}

        {activeTab === 'playback' && (
          <PlaybackView cameras={cameras} activeMode={activeMode} />
        )}

        {activeTab === 'cameras' && (
          <CameraList
            cameras={cameras}
            activeMode={activeMode}
            onAddCamera={() => {
              setEditingCamera(null);
              setShowAddForm(true);
            }}
            onEditCamera={(cam) => {
              setEditingCamera(cam);
              setShowAddForm(true);
            }}
            onDeleteCamera={handleDeleteCamera}
            onSelectLiveCamera={handleSelectLive}
            onToggleMode={(mode) => setActiveMode(mode)}
          />
        )}

        {activeTab === 'settings' && <SettingsView />}
      </main>

      {/* Add / Edit Camera Modal Form */}
      {showAddForm && (
        <CameraFormModal
          initialCamera={editingCamera}
          onSave={handleSaveCamera}
          onClose={() => {
            setShowAddForm(false);
            setEditingCamera(null);
          }}
        />
      )}

      {/* Mobile Bottom Navigation */}
      <Navigation activeTab={activeTab} onTabChange={setActiveTab} />
    </div>
  );
}

export default App;
