import React from 'react';
import { Video, Wifi, Globe, Edit, Trash2, ExternalLink, ShieldCheck } from 'lucide-react';
import type { CameraConfig, StreamMode } from '../types/camera';
import { buildLiveRtspUrl, getVlcDeepLink } from '../services/rtspBuilder';

interface CameraCardProps {
  camera: CameraConfig;
  activeMode: StreamMode;
  onEdit: (camera: CameraConfig) => void;
  onDelete: (id: number) => void;
  onSelectLive: (camera: CameraConfig) => void;
}

export const CameraCard: React.FC<CameraCardProps> = ({
  camera,
  activeMode,
  onEdit,
  onDelete,
  onSelectLive
}) => {
  const rtspUrl = buildLiveRtspUrl(camera, activeMode);
  const vlcLink = getVlcDeepLink(rtspUrl);
  const activeHost = activeMode === 'local' ? camera.localIp : camera.remoteHost;

  return (
    <div className="camera-card">
      <div className="card-top-preview" onClick={() => onSelectLive(camera)}>
        <div className="preview-overlay">
          <div className="live-pill">
            <span className="live-pulse" />
            LIVE
          </div>
          <span className="channel-pill">Ch {camera.channel}</span>
        </div>
        <div className="preview-placeholder">
          <Video className="w-10 h-10 text-slate-500 mb-2" />
          <span className="text-xs text-slate-400">Tap to Play RTSP Stream</span>
        </div>
      </div>

      <div className="card-body">
        <div className="card-header">
          <h3 className="camera-title">{camera.name}</h3>
          <span className="brand-badge">{camera.nvrBrand.toUpperCase()}</span>
        </div>

        <p className="camera-location">{camera.location}</p>

        <div className="card-net-info">
          <div className="net-item">
            {activeMode === 'local' ? (
              <Wifi className="w-3.5 h-3.5 text-blue-400" />
            ) : (
              <Globe className="w-3.5 h-3.5 text-emerald-400" />
            )}
            <span className="net-host">{activeHost}:{camera.rtspPort}</span>
          </div>
          <div className="net-item">
            <ShieldCheck className="w-3.5 h-3.5 text-slate-400" />
            <span className="net-user">{camera.username}</span>
          </div>
        </div>

        <div className="card-actions">
          <button
            type="button"
            className="action-btn play"
            onClick={() => onSelectLive(camera)}
          >
            <Video className="w-3.5 h-3.5 mr-1" />
            Play
          </button>

          <a
            href={vlcLink}
            className="action-btn vlc"
            title="Open directly in VLC Player app"
          >
            <ExternalLink className="w-3.5 h-3.5 mr-1" />
            VLC App
          </a>

          <button
            type="button"
            className="action-btn icon"
            onClick={() => onEdit(camera)}
            title="Edit Settings"
          >
            <Edit className="w-3.5 h-3.5" />
          </button>

          <button
            type="button"
            className="action-btn icon danger"
            onClick={() => camera.id && onDelete(camera.id)}
            title="Delete Camera"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
};
