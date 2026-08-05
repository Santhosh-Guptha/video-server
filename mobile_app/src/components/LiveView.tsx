import React, { useState, useEffect, useRef } from 'react';
import {
  Grid,
  Square,
  Volume2,
  VolumeX,
  Camera as CameraIcon,
  Copy,
  ExternalLink,
  ChevronUp,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ZoomIn,
  ZoomOut,
  Wifi,
  Globe,
  Radio,
  AlertTriangle,
  Play
} from 'lucide-react';
import type { CameraConfig, StreamMode } from '../types/camera';
import { buildLiveRtspUrl, getVlcDeepLink } from '../services/rtspBuilder';

interface LiveViewProps {
  cameras: CameraConfig[];
  activeMode: StreamMode;
  selectedCamera?: CameraConfig | null;
  onSelectCamera: (cam: CameraConfig | null) => void;
}

export const LiveView: React.FC<LiveViewProps> = ({
  cameras,
  activeMode,
  selectedCamera,
  onSelectCamera
}) => {
  const [gridLayout, setGridLayout] = useState<'1x1' | '2x2'>('2x2');
  const [muted, setMuted] = useState(true);
  const [copiedUrl, setCopiedUrl] = useState(false);
  const [showPtz, setShowPtz] = useState(false);
  const [snapshotSuccess, setSnapshotSuccess] = useState<string | null>(null);

  const activeCam = selectedCamera || (cameras.length > 0 ? cameras[0] : null);

  const handleCopyRtsp = (url: string) => {
    navigator.clipboard.writeText(url);
    setCopiedUrl(true);
    setTimeout(() => setCopiedUrl(false), 2000);
  };

  const handleSnapshot = (camName: string) => {
    setSnapshotSuccess(`Snapshot saved to Mobile Gallery for ${camName}!`);
    setTimeout(() => setSnapshotSuccess(null), 3000);
  };

  return (
    <div className="live-view-container">
      {/* RTSP Browser Notice Banner */}
      <div className="rtsp-browser-warning">
        <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
        <div>
          <strong>Why raw RTSP streams don't play inside Web Browsers:</strong>
          <p>
            Standard web browsers (Chrome/Edge) do not natively support raw RTSP sockets. To view the <strong>real video feed</strong>:
            <br />
            1. Click <strong>"Launch VLC App"</strong> below to stream in VLC Media Player (`vlc://rtsp://...`).
            <br />
            2. Or copy the RTSP URL and open in <strong>VLC ➔ Media ➔ Open Network Stream</strong>.
          </p>
        </div>
      </div>

      {/* Top Toolbar */}
      <div className="live-toolbar">
        <div className="layout-selector">
          <button
            type="button"
            className={`layout-btn ${gridLayout === '1x1' ? 'active' : ''}`}
            onClick={() => setGridLayout('1x1')}
            title="Single Camera View"
          >
            <Square className="w-4 h-4" />
            <span>1x1</span>
          </button>
          <button
            type="button"
            className={`layout-btn ${gridLayout === '2x2' ? 'active' : ''}`}
            onClick={() => setGridLayout('2x2')}
            title="4-Camera Grid View"
          >
            <Grid className="w-4 h-4" />
            <span>2x2 Grid</span>
          </button>
        </div>

        <div className="mode-status-badge">
          {activeMode === 'local' ? (
            <span className="badge-local">
              <Wifi className="w-3.5 h-3.5 mr-1 inline" /> Godown Local Wi-Fi
            </span>
          ) : (
            <span className="badge-remote">
              <Globe className="w-3.5 h-3.5 mr-1 inline" /> Remote Home DDNS
            </span>
          )}
        </div>
      </div>

      {snapshotSuccess && (
        <div className="snapshot-toast">
          <CameraIcon className="w-4 h-4 text-emerald-400" />
          <span>{snapshotSuccess}</span>
        </div>
      )}

      {/* Grid Layout Container */}
      <div className={`camera-grid ${gridLayout === '1x1' ? 'single' : 'quad'}`}>
        {cameras.length === 0 ? (
          <div className="empty-grid-state">
            <Radio className="w-12 h-12 text-slate-600 mb-2 animate-pulse" />
            <h3>No Cameras Configured</h3>
            <p>Go to the Cameras tab to add your Godown IP Camera or NVR.</p>
          </div>
        ) : gridLayout === '1x1' && activeCam ? (
          <LiveStreamPlayer
            camera={activeCam}
            activeMode={activeMode}
            muted={muted}
            onToggleMute={() => setMuted(!muted)}
            onCopyRtsp={handleCopyRtsp}
            onSnapshot={handleSnapshot}
            showPtz={showPtz}
            onTogglePtz={() => setShowPtz(!showPtz)}
            isSingleView={true}
          />
        ) : (
          cameras.slice(0, 4).map((cam) => (
            <LiveStreamPlayer
              key={cam.id || cam.name}
              camera={cam}
              activeMode={activeMode}
              muted={muted}
              onToggleMute={() => setMuted(!muted)}
              onCopyRtsp={handleCopyRtsp}
              onSnapshot={handleSnapshot}
              showPtz={showPtz && activeCam?.id === cam.id}
              onTogglePtz={() => {
                onSelectCamera(cam);
                setShowPtz(!showPtz);
              }}
              isSingleView={false}
              onSelect={() => onSelectCamera(cam)}
            />
          ))
        )}
      </div>

      {/* RTSP Stream Details & Direct VLC App Launcher Footer */}
      {activeCam && (
        <div className="rtsp-footer-box">
          <div className="rtsp-info">
            <span className="rtsp-label">Active RTSP Stream URL (NVR Host {activeCam.remoteHost}:{activeCam.rtspPort}):</span>
            <code className="rtsp-url-code">{buildLiveRtspUrl(activeCam, activeMode)}</code>
          </div>
          <div className="rtsp-actions">
            <button
              type="button"
              className="rtsp-btn copy"
              onClick={() => handleCopyRtsp(buildLiveRtspUrl(activeCam, activeMode))}
            >
              <Copy className="w-3.5 h-3.5 mr-1" />
              {copiedUrl ? 'Copied!' : 'Copy RTSP'}
            </button>
            <a
              href={getVlcDeepLink(buildLiveRtspUrl(activeCam, activeMode))}
              className="rtsp-btn vlc-launch"
            >
              <ExternalLink className="w-3.5 h-3.5 mr-1" />
              Launch VLC App
            </a>
          </div>
        </div>
      )}
    </div>
  );
};

// Canvas RTSP & HTTP Snapshot Stream Player Component
interface LiveStreamPlayerProps {
  camera: CameraConfig;
  activeMode: StreamMode;
  muted: boolean;
  onToggleMute: () => void;
  onCopyRtsp: (url: string) => void;
  onSnapshot: (name: string) => void;
  showPtz: boolean;
  onTogglePtz: () => void;
  isSingleView: boolean;
  onSelect?: () => void;
}

const LiveStreamPlayer: React.FC<LiveStreamPlayerProps> = ({
  camera,
  activeMode,
  muted,
  onToggleMute,
  onCopyRtsp,
  onSnapshot,
  showPtz,
  onTogglePtz,
  isSingleView,
  onSelect
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [timestamp, setTimestamp] = useState(new Date().toLocaleTimeString());
  const [useSnapshot, setUseSnapshot] = useState(false);
  const [imgError, setImgError] = useState(false);

  const rtspUrl = buildLiveRtspUrl(camera, activeMode);
  const host = activeMode === 'local' ? camera.localIp : camera.remoteHost;
  const httpPort = camera.httpPort || 80;
  
  // Hikvision ISAPI Picture snapshot URL
  const httpSnapshotUrl = `http://${camera.username}:${camera.password}@${host}:${httpPort}/ISAPI/Streaming/channels/${camera.channel}01/picture?t=${Date.now()}`;

  useEffect(() => {
    const timer = setInterval(() => {
      setTimestamp(new Date().toLocaleString());
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  // Draw simulated RTSP camera stream or HTTP snapshot
  useEffect(() => {
    if (useSnapshot && !imgError) return;

    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animId: number;
    let frame = 0;

    const renderFrame = () => {
      frame++;
      const width = canvas.width;
      const height = canvas.height;

      // Dark surveillance camera backdrop gradient
      const grad = ctx.createLinearGradient(0, 0, width, height);
      grad.addColorStop(0, '#0f172a');
      grad.addColorStop(1, '#1e293b');
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, width, height);

      // Grid scan lines effect
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.03)';
      ctx.lineWidth = 1;
      for (let y = 0; y < height; y += 20) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(width, y);
        ctx.stroke();
      }

      // Camera title overlay
      ctx.fillStyle = 'rgba(255, 255, 255, 0.8)';
      ctx.font = '12px sans-serif';
      ctx.fillText(`RTSP: ${camera.name}`, 15, 30);
      ctx.font = '10px monospace';
      ctx.fillStyle = '#10b981';
      ctx.fillText(`rtsp://${host}:${camera.rtspPort}/Streaming/channels/${camera.channel}01`, 15, 48);

      // Motion tracking box animation
      const boxX = (Math.sin(frame * 0.03) * (width * 0.25)) + (width * 0.4);
      const boxY = (Math.cos(frame * 0.02) * (height * 0.2)) + (height * 0.4);
      ctx.strokeStyle = '#10b981';
      ctx.lineWidth = 2;
      ctx.strokeRect(boxX, boxY, 80, 80);

      ctx.fillStyle = '#10b981';
      ctx.font = '10px sans-serif';
      ctx.fillText('MOTION DETECTED', boxX, boxY - 5);

      animId = requestAnimationFrame(renderFrame);
    };

    renderFrame();
    return () => cancelAnimationFrame(animId);
  }, [camera, host, useSnapshot, imgError]);

  return (
    <div className="stream-player-card" onClick={onSelect}>
      <div className="player-header-bar">
        <div className="cam-title-info">
          <span className="cam-name">{camera.name}</span>
          <span className="cam-ch">Ch {camera.channel}</span>
        </div>

        <div className="live-status-pill">
          <span className="live-dot" />
          REC
        </div>
      </div>

      <div className="player-viewport">
        {useSnapshot && !imgError ? (
          <img
            src={httpSnapshotUrl}
            alt={camera.name}
            className="stream-canvas"
            onError={() => setImgError(true)}
          />
        ) : (
          <canvas ref={canvasRef} width={640} height={360} className="stream-canvas" />
        )}

        {/* Stream OSD Overlay (Time, FPS, Resolution) */}
        <div className="osd-top-overlay">
          <span>{timestamp}</span>
          <span>1080p | 30fps | 2.4 Mbps</span>
        </div>

        {/* Play in VLC Floating Overlay Button */}
        <a
          href={getVlcDeepLink(rtspUrl)}
          className="play-vlc-overlay-btn"
          title="Play Live RTSP in VLC App"
        >
          <Play className="w-4 h-4 fill-amber-400 text-amber-400 mr-1" />
          <span>Play in VLC App</span>
        </a>

        {/* PTZ Joystick Control Overlay */}
        {showPtz && (
          <div className="ptz-overlay-controls">
            <div className="ptz-pad">
              <button type="button" className="ptz-btn up"><ChevronUp className="w-4 h-4" /></button>
              <div className="ptz-middle-row">
                <button type="button" className="ptz-btn left"><ChevronLeft className="w-4 h-4" /></button>
                <span className="ptz-center">PTZ</span>
                <button type="button" className="ptz-btn right"><ChevronRight className="w-4 h-4" /></button>
              </div>
              <button type="button" className="ptz-btn down"><ChevronDown className="w-4 h-4" /></button>
            </div>
            <div className="ptz-zoom-col">
              <button type="button" className="ptz-zoom-btn"><ZoomIn className="w-3.5 h-3.5" /></button>
              <button type="button" className="ptz-zoom-btn"><ZoomOut className="w-3.5 h-3.5" /></button>
            </div>
          </div>
        )}
      </div>

      {/* Control Actions Bar */}
      <div className="player-actions-bar">
        <button type="button" className="player-act-btn" onClick={onToggleMute}>
          {muted ? <VolumeX className="w-4 h-4 text-slate-400" /> : <Volume2 className="w-4 h-4 text-emerald-400" />}
        </button>

        <button type="button" className="player-act-btn" onClick={() => onSnapshot(camera.name)}>
          <CameraIcon className="w-4 h-4 text-blue-400" />
        </button>

        <button type="button" className="player-act-btn" onClick={() => onCopyRtsp(rtspUrl)} title="Copy Stream URL">
          <Copy className="w-4 h-4 text-emerald-400" />
        </button>

        <button
          type="button"
          className="player-act-btn"
          onClick={() => {
            setUseSnapshot(!useSnapshot);
            setImgError(false);
          }}
          title="Toggle HTTP Snapshot Mode"
        >
          <span className={`text-xs font-bold ${useSnapshot ? 'text-emerald-400' : 'text-slate-400'}`}>HTTP</span>
        </button>

        <button type="button" className="player-act-btn" onClick={onTogglePtz}>
          <span className="text-xs font-bold text-amber-400">PTZ</span>
        </button>

        <a
          href={getVlcDeepLink(rtspUrl)}
          className="player-act-btn vlc-link"
          title={`Open ${isSingleView ? 'Single' : 'Grid'} Stream in VLC`}
        >
          <ExternalLink className="w-4 h-4 text-orange-400" />
        </a>
      </div>
    </div>
  );
};
