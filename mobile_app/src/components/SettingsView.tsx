import React, { useState } from 'react';
import {
  Settings,
  Shield,
  Download,
  Upload,
  Activity,
  CheckCircle,
  AlertCircle,
  Database
} from 'lucide-react';
import { updateUserPin, exportCameraConfigJson, importCameraConfigJson } from '../services/authService';

export const SettingsView: React.FC = () => {
  const [newPin, setNewPin] = useState('');
  const [pinSuccess, setPinSuccess] = useState('');
  const [pinError, setPinError] = useState('');
  const [importStatus, setImportStatus] = useState<{ success?: boolean; message?: string } | null>(null);

  const handleSavePin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (newPin.length !== 4) {
      setPinError('Security PIN must be exactly 4 digits');
      return;
    }
    await updateUserPin(newPin);
    setPinSuccess('Security PIN updated successfully!');
    setPinError('');
    setNewPin('');
    setTimeout(() => setPinSuccess(''), 3000);
  };

  const handleExport = async () => {
    const jsonStr = await exportCameraConfigJson();
    const blob = new Blob([jsonStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `Godown_Camera_Backup_${new Date().toISOString().split('T')[0]}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = async (event) => {
      try {
        const content = event.target?.result as string;
        const count = await importCameraConfigJson(content);
        setImportStatus({ success: true, message: `Successfully imported ${count} camera configurations!` });
        setTimeout(() => window.location.reload(), 1500);
      } catch (err) {
        setImportStatus({ success: false, message: 'Failed to import configuration JSON.' });
      }
    };
    reader.readAsText(file);
  };

  return (
    <div className="settings-container">
      <div className="settings-header">
        <Settings className="w-5 h-5 text-emerald-400" />
        <h2 className="section-title">App Settings & Security</h2>
      </div>

      {/* App Security & PIN Setup Card */}
      <div className="settings-card">
        <div className="card-title-bar">
          <Shield className="w-4 h-4 text-emerald-400" />
          <h3>App Security & Lock PIN</h3>
        </div>

        <form onSubmit={handleSavePin} className="pin-form">
          <div className="form-group">
            <label>Change App 4-Digit PIN</label>
            <div className="pin-input-group">
              <input
                type="password"
                maxLength={4}
                placeholder="Enter new 4-digit PIN"
                value={newPin}
                onChange={(e) => setNewPin(e.target.value)}
              />
              <button type="submit" className="btn-save-pin">
                Update PIN
              </button>
            </div>
          </div>

          {pinSuccess && (
            <div className="status-banner success">
              <CheckCircle className="w-4 h-4 text-emerald-400" />
              <span>{pinSuccess}</span>
            </div>
          )}

          {pinError && (
            <div className="status-banner error">
              <AlertCircle className="w-4 h-4 text-red-400" />
              <span>{pinError}</span>
            </div>
          )}
        </form>
      </div>

      {/* Local Database Backup & Restore */}
      <div className="settings-card">
        <div className="card-title-bar">
          <Database className="w-4 h-4 text-blue-400" />
          <h3>Local Database Backup & Restore</h3>
        </div>

        <p className="card-desc">
          Export all your saved camera IP addresses, DDNS credentials, and NVR channels to a JSON file, or restore from a previous backup.
        </p>

        <div className="backup-actions">
          <button type="button" className="btn-backup export" onClick={handleExport}>
            <Download className="w-4 h-4 mr-1 inline" />
            Export Backup JSON
          </button>

          <label className="btn-backup import">
            <Upload className="w-4 h-4 mr-1 inline" />
            Import Backup JSON
            <input type="file" accept=".json" onChange={handleImport} hidden />
          </label>
        </div>

        {importStatus && (
          <div className={`status-banner ${importStatus.success ? 'success' : 'error'} mt-3`}>
            {importStatus.success ? (
              <CheckCircle className="w-4 h-4 text-emerald-400" />
            ) : (
              <AlertCircle className="w-4 h-4 text-red-400" />
            )}
            <span>{importStatus.message}</span>
          </div>
        )}
      </div>

      {/* Network Architecture Quick Reference */}
      <div className="settings-card">
        <div className="card-title-bar">
          <Activity className="w-4 h-4 text-amber-400" />
          <h3>Zero-Backend Direct RTSP Architecture</h3>
        </div>

        <div className="arch-summary">
          <div className="arch-step">
            <span className="step-num">1</span>
            <div>
              <strong>Godown Wi-Fi (Local Mode)</strong>
              <p>Direct RTSP socket over `rtsp://192.168.1.X:554` when on the same Wi-Fi network.</p>
            </div>
          </div>

          <div className="arch-step">
            <span className="step-num">2</span>
            <div>
              <strong>Home 4G/DDNS (Remote Mode)</strong>
              <p>Streams over Port Forwarding DDNS `rtsp://godown.ddns.net:554` from anywhere.</p>
            </div>
          </div>

          <div className="arch-step">
            <span className="step-num">3</span>
            <div>
              <strong>Hikvision & Dahua Playback</strong>
              <p>Requests `rtsp://.../Streaming/tracks/...` with start and end timestamps directly from NVR.</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
