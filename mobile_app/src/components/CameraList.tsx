import React, { useState } from 'react';
import { Plus, Search, Camera as CameraIcon, Wifi, Globe } from 'lucide-react';
import type { CameraConfig, StreamMode } from '../types/camera';
import { CameraCard } from './CameraCard';

interface CameraListProps {
  cameras: CameraConfig[];
  activeMode: StreamMode;
  onAddCamera: () => void;
  onEditCamera: (camera: CameraConfig) => void;
  onDeleteCamera: (id: number) => void;
  onSelectLiveCamera: (camera: CameraConfig) => void;
  onToggleMode: (mode: StreamMode) => void;
}

export const CameraList: React.FC<CameraListProps> = ({
  cameras,
  activeMode,
  onAddCamera,
  onEditCamera,
  onDeleteCamera,
  onSelectLiveCamera,
  onToggleMode
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [filterBrand, setFilterBrand] = useState<string>('all');

  const filteredCameras = cameras.filter((cam) => {
    const matchesSearch =
      cam.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      cam.location.toLowerCase().includes(searchTerm.toLowerCase()) ||
      cam.localIp.includes(searchTerm) ||
      cam.remoteHost.includes(searchTerm);

    const matchesBrand = filterBrand === 'all' || cam.nvrBrand === filterBrand;

    return matchesSearch && matchesBrand;
  });

  return (
    <div className="camera-list-container">
      {/* Search & Actions Bar */}
      <div className="list-top-bar">
        <div className="search-input-wrapper">
          <Search className="w-4 h-4 text-slate-400" />
          <input
            type="text"
            placeholder="Search by name, location, or IP..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>

        <button type="button" className="add-cam-btn" onClick={onAddCamera}>
          <Plus className="w-4 h-4 mr-1" />
          Add Camera
        </button>
      </div>

      {/* Network Mode Switcher Card */}
      <div className="mode-switcher-banner">
        <div className="banner-info">
          <h3>Connection Destination Mode</h3>
          <p>Switch all streams between Godown Local Wi-Fi (`192.168.x.x`) and Home 4G DDNS (`godown.ddns.net`)</p>
        </div>

        <div className="banner-toggle">
          <button
            type="button"
            className={`btn-mode ${activeMode === 'local' ? 'active-local' : ''}`}
            onClick={() => onToggleMode('local')}
          >
            <Wifi className="w-3.5 h-3.5 mr-1 inline" /> Local Wi-Fi
          </button>
          <button
            type="button"
            className={`btn-mode ${activeMode === 'remote' ? 'active-remote' : ''}`}
            onClick={() => onToggleMode('remote')}
          >
            <Globe className="w-3.5 h-3.5 mr-1 inline" /> Home 4G / DDNS
          </button>
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="filter-tabs">
        {['all', 'hikvision', 'dahua', 'uniview', 'onvif'].map((brand) => (
          <button
            key={brand}
            type="button"
            className={`tab-btn ${filterBrand === brand ? 'active' : ''}`}
            onClick={() => setFilterBrand(brand)}
          >
            {brand.toUpperCase()}
          </button>
        ))}
      </div>

      {/* Cameras Grid */}
      {filteredCameras.length === 0 ? (
        <div className="empty-list-card">
          <CameraIcon className="w-10 h-10 text-slate-500 mb-2" />
          <h3>No Cameras Found</h3>
          <p>Click "Add Camera" to configure a new IP Camera or NVR.</p>
        </div>
      ) : (
        <div className="camera-cards-grid">
          {filteredCameras.map((cam) => (
            <CameraCard
              key={cam.id || cam.name}
              camera={cam}
              activeMode={activeMode}
              onEdit={onEditCamera}
              onDelete={onDeleteCamera}
              onSelectLive={onSelectLiveCamera}
            />
          ))}
        </div>
      )}
    </div>
  );
};
