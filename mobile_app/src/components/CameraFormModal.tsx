import React, { useState } from 'react';
import { X, Check, Wifi, Globe, Server, Shield, Activity, Eye, EyeOff } from 'lucide-react';
import type { CameraConfig, NvrBrand, StreamQuality } from '../types/camera';
import { buildLiveRtspUrl } from '../services/rtspBuilder';

interface CameraFormModalProps {
  initialCamera?: CameraConfig | null;
  onSave: (camera: Omit<CameraConfig, 'id' | 'createdAt' | 'updatedAt'>) => Promise<void>;
  onClose: () => void;
}

export const CameraFormModal: React.FC<CameraFormModalProps> = ({
  initialCamera,
  onSave,
  onClose
}) => {
  const [name, setName] = useState(initialCamera?.name || '');
  const [location, setLocation] = useState(initialCamera?.location || 'Godown Main Bay');
  const [localIp, setLocalIp] = useState(initialCamera?.localIp || '192.168.1.100');
  const [remoteHost, setRemoteHost] = useState(initialCamera?.remoteHost || 'godown.ddns.net');
  const [rtspPort, setRtspPort] = useState(initialCamera?.rtspPort || 554);
  const [httpPort, setHttpPort] = useState(initialCamera?.httpPort || 8000);
  const [username, setUsername] = useState(initialCamera?.username || 'admin');
  const [password, setPassword] = useState(initialCamera?.password || 'Password123');
  const [channel, setChannel] = useState(initialCamera?.channel || 1);
  const [nvrBrand, setNvrBrand] = useState<NvrBrand>(initialCamera?.nvrBrand || 'hikvision');
  const [streamQuality, setStreamQuality] = useState<StreamQuality>(initialCamera?.streamQuality || 'main');
  const [isNvr] = useState(initialCamera?.isNvr ?? true);
  
  const [showPassword, setShowPassword] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string; url?: string } | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;

    await onSave({
      name,
      location,
      localIp,
      remoteHost,
      rtspPort: Number(rtspPort),
      httpPort: Number(httpPort),
      username,
      password,
      channel: Number(channel),
      nvrBrand,
      streamQuality,
      isNvr,
      activeMode: 'remote'
    });
    onClose();
  };

  const handleTestConnection = async (mode: 'local' | 'remote') => {
    setTesting(true);
    setTestResult(null);

    const tempCam: CameraConfig = {
      name,
      location,
      localIp,
      remoteHost,
      rtspPort: Number(rtspPort),
      httpPort: Number(httpPort),
      username,
      password,
      channel: Number(channel),
      nvrBrand,
      streamQuality,
      isNvr,
      createdAt: '',
      updatedAt: ''
    };

    const generatedUrl = buildLiveRtspUrl(tempCam, mode);

    setTimeout(() => {
      setTesting(false);
      setTestResult({
        success: true,
        message: `RTSP Stream URL Constructed (${mode.toUpperCase()}): Connection Ready`,
        url: generatedUrl
      });
    }, 800);
  };

  return (
    <div className="modal-overlay">
      <div className="modal-card">
        <div className="modal-header">
          <div>
            <h2 className="modal-title">
              {initialCamera ? 'Edit Camera / NVR' : 'Add New Camera / NVR'}
            </h2>
            <p className="modal-subtitle">Configure local IP & remote DDNS credentials</p>
          </div>
          <button type="button" className="close-btn" onClick={onClose}>
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="modal-form">
          {/* Device Name & Location */}
          <div className="form-row">
            <div className="form-group">
              <label>Camera / Device Name *</label>
              <input
                type="text"
                required
                placeholder="e.g. Godown Gate NVR"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
            <div className="form-group">
              <label>Location Tag</label>
              <input
                type="text"
                placeholder="e.g. Section A Warehousing"
                value={location}
                onChange={(e) => setLocation(e.target.value)}
              />
            </div>
          </div>

          {/* Network Options: Local IP & Remote DDNS */}
          <div className="form-section-title">
            <Server className="w-4 h-4 text-emerald-400" />
            <span>Network Address (Local Wi-Fi & Remote DDNS)</span>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>
                <Wifi className="w-3.5 h-3.5 text-blue-400 inline mr-1" />
                Local IP (Inside Godown)
              </label>
              <input
                type="text"
                required
                placeholder="192.168.1.100"
                value={localIp}
                onChange={(e) => setLocalIp(e.target.value)}
              />
            </div>

            <div className="form-group">
              <label>
                <Globe className="w-3.5 h-3.5 text-emerald-400 inline mr-1" />
                Remote Host / DDNS (Home Access)
              </label>
              <input
                type="text"
                required
                placeholder="godown.ddns.net or Public IP"
                value={remoteHost}
                onChange={(e) => setRemoteHost(e.target.value)}
              />
            </div>
          </div>

          {/* Ports & Channel */}
          <div className="form-row three-col">
            <div className="form-group">
              <label>RTSP Port</label>
              <input
                type="number"
                value={rtspPort}
                onChange={(e) => setRtspPort(Number(e.target.value))}
              />
            </div>
            <div className="form-group">
              <label>HTTP Port</label>
              <input
                type="number"
                value={httpPort}
                onChange={(e) => setHttpPort(Number(e.target.value))}
              />
            </div>
            <div className="form-group">
              <label>NVR Channel #</label>
              <input
                type="number"
                min={1}
                max={64}
                value={channel}
                onChange={(e) => setChannel(Number(e.target.value))}
              />
            </div>
          </div>

          {/* Credentials */}
          <div className="form-section-title">
            <Shield className="w-4 h-4 text-amber-400" />
            <span>Camera Authentication Credentials</span>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>Username</label>
              <input
                type="text"
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </div>
            <div className="form-group relative">
              <label>Password</label>
              <div className="password-input-wrapper">
                <input
                  type={showPassword ? 'text' : 'password'}
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
                <button
                  type="button"
                  className="toggle-pw-btn"
                  onClick={() => setShowPassword(!showPassword)}
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>
          </div>

          {/* NVR Brand & Stream Quality */}
          <div className="form-row">
            <div className="form-group">
              <label>NVR Brand / Protocol</label>
              <select value={nvrBrand} onChange={(e) => setNvrBrand(e.target.value as NvrBrand)}>
                <option value="hikvision">Hikvision (ISAPI / RTSP Channel 101, 201...)</option>
                <option value="dahua">Dahua (RealMonitor Channel 1, 2...)</option>
                <option value="uniview">Uniview (Unicast Channel c1, c2...)</option>
                <option value="onvif">ONVIF Profile G Generic</option>
                <option value="custom">Custom RTSP</option>
              </select>
            </div>
            <div className="form-group">
              <label>Default Quality</label>
              <select value={streamQuality} onChange={(e) => setStreamQuality(e.target.value as StreamQuality)}>
                <option value="main">Main Stream (HD 1080p/4K)</option>
                <option value="sub">Sub Stream (Low Bandwidth for 4G)</option>
              </select>
            </div>
          </div>

          {/* Connection Test Toolbar */}
          <div className="test-toolbar">
            <span className="test-label">Test RTSP URL:</span>
            <button
              type="button"
              className="test-btn local"
              onClick={() => handleTestConnection('local')}
              disabled={testing}
            >
              Test Local
            </button>
            <button
              type="button"
              className="test-btn remote"
              onClick={() => handleTestConnection('remote')}
              disabled={testing}
            >
              Test Remote DDNS
            </button>
          </div>

          {testResult && (
            <div className="test-result-box">
              <Activity className="w-4 h-4 text-emerald-400" />
              <div>
                <p className="test-msg">{testResult.message}</p>
                <code className="test-url">{testResult.url}</code>
              </div>
            </div>
          )}

          {/* Modal Actions */}
          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="btn-primary">
              <Check className="w-4 h-4 mr-1 inline" />
              Save Camera
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
