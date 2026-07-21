import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import Hls from 'hls.js';
import {
  ShieldAlert, UserCheck, Smile, Car, Bell, Sliders,
  Eye, Cpu, Plus, Trash2, Zap, Search, LayoutGrid,
  Maximize2, RotateCw, ChevronLeft, ChevronRight, X,
  Power, Activity, PlayCircle, StopCircle, Settings2, Video
} from 'lucide-react';

const getAiServiceHost = () => {
  if (typeof window !== 'undefined') {
    const hostname = window.location.hostname || 'localhost';
    return `http://${hostname}:8001`;
  }
  return 'http://localhost:8001';
};

const getVmsBackendHost = () => {
  if (typeof window !== 'undefined') {
    const hostname = window.location.hostname || 'localhost';
    return `http://${hostname}:8005`;
  }
  return 'http://localhost:8005';
};

const getAiWsHost = () => {
  if (typeof window !== 'undefined') {
    const hostname = window.location.hostname || 'localhost';
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${hostname}:8001/ws/ai-events`;
  }
  return 'ws://localhost:8001/ws/ai-events';
};

// Safe helper for bbox coordinate parsing
const getBboxCoords = (bbox) => {
  if (Array.isArray(bbox) && bbox.length >= 4) {
    return [Number(bbox[0]) || 0, Number(bbox[1]) || 0, Number(bbox[2]) || 0, Number(bbox[3]) || 0];
  }
  if (bbox && typeof bbox === 'object') {
    const x1 = Number(bbox.xmin ?? bbox.x1 ?? bbox.x ?? 0);
    const y1 = Number(bbox.ymin ?? bbox.y1 ?? bbox.y ?? 0);
    const x2 = Number(bbox.xmax ?? bbox.x2 ?? (x1 + (bbox.width ?? 0.2)));
    const y2 = Number(bbox.ymax ?? bbox.y2 ?? (y1 + (bbox.height ?? 0.2)));
    return [x1, y1, x2, y2];
  }
  return [0, 0, 0, 0];
};

const getPolygonPointsStr = (polygon) => {
  if (!Array.isArray(polygon)) return '';
  return polygon
    .filter(p => p && typeof p === 'object')
    .map(p => `${(Number(p.x) || 0) * 100}%,${(Number(p.y) || 0) * 100}%`)
    .join(' ');
};

// ─── HLS Live Video Player Component ─────────────────────────────
function HLSVideoPlayer({ src, style, onCanPlay, onError, videoRef: externalRef }) {
  const internalRef = useRef(null);
  const hlsRef = useRef(null);
  const videoRef = externalRef || internalRef;
  const retryCountRef = useRef(0);
  const retryTimerRef = useRef(null);
  const isMountedRef = useRef(true);

  const startHls = useCallback((video, hlsSrc) => {
    if (!isMountedRef.current || !video) return;

    if (hlsRef.current) {
      hlsRef.current.destroy();
      hlsRef.current = null;
    }

    // Safari native HLS
    if (video.canPlayType('application/vnd.apple.mpegurl')) {
      video.src = hlsSrc;
      video.play().catch(() => {});
      return;
    }

    if (!Hls.isSupported()) return;

    const hls = new Hls({
      lowLatencyMode: true,
      backBufferLength: 30,
      liveDurationInfinity: true,
      liveSyncDuration: 3.0,
      liveMaxLatencyDuration: 6.0,
      maxBufferLength: 10,
      maxMaxBufferLength: 20,
      manifestLoadingTimeOut: 8000,
      manifestLoadingMaxRetry: 1,
      levelLoadingTimeOut: 8000,
      levelLoadingMaxRetry: 2,
    });

    hlsRef.current = hls;
    hls.loadSource(hlsSrc);
    hls.attachMedia(video);

    hls.on(Hls.Events.MANIFEST_PARSED, () => {
      if (!isMountedRef.current) return;
      retryCountRef.current = 0;
      video.play().catch(() => {});
      onCanPlay && onCanPlay();
    });

    hls.on(Hls.Events.ERROR, (_event, data) => {
      if (!isMountedRef.current) return;
      if (data.fatal) {
        if (data.type === Hls.ErrorTypes.NETWORK_ERROR && retryCountRef.current < 5) {
          retryCountRef.current++;
          hls.destroy();
          hlsRef.current = null;
          retryTimerRef.current = window.setTimeout(() => {
            if (isMountedRef.current && videoRef.current) {
              startHls(videoRef.current, hlsSrc);
            }
          }, 2000);
        } else if (data.type === Hls.ErrorTypes.MEDIA_ERROR) {
          hls.recoverMediaError();
        } else {
          hls.destroy();
          hlsRef.current = null;
          onError && onError();
        }
      }
    });
  }, [onCanPlay, onError, videoRef]);

  useEffect(() => {
    isMountedRef.current = true;
    retryCountRef.current = 0;
    const video = videoRef.current;
    if (!video || !src) return;

    startHls(video, src);

    return () => {
      isMountedRef.current = false;
      if (retryTimerRef.current) {
        clearTimeout(retryTimerRef.current);
        retryTimerRef.current = null;
      }
      if (hlsRef.current) {
        hlsRef.current.destroy();
        hlsRef.current = null;
      }
      if (video) {
        video.src = '';
        video.removeAttribute('src');
        try { video.load(); } catch (e) {}
      }
    };
  }, [src, startHls, videoRef]);

  return (
    <video
      ref={videoRef}
      autoPlay
      playsInline
      muted
      style={{ width: '100%', height: '100%', objectFit: 'contain', background: '#000', ...style }}
    />
  );
}

// ─── Live Camera Cell for the Wall (Pure HLS, No AI) ────────────
function LiveWallCell({ camera, vmsBackendHost, onFocusCamera }) {
  if (!camera || !camera.id) {
    return (
      <div className="glass-card" style={{ width: '100%', aspectRatio: '16/9', background: '#020617', borderRadius: '6px', border: '1px solid #1e293b' }} />
    );
  }

  const camId = camera.id;
  const camName = camera.name || `Camera ${camId}`;
  const hlsSrc = `${vmsBackendHost}/api/streams/${encodeURIComponent(camId)}/live/index.m3u8`;

  const [status, setStatus] = useState('connecting');

  return (
    <div
      className="glass-card"
      onClick={() => onFocusCamera && onFocusCamera(camera)}
      style={{
        position: 'relative',
        width: '100%',
        aspectRatio: '16/9',
        borderRadius: '6px',
        overflow: 'hidden',
        background: '#020617',
        border: '1px solid #1e293b',
        cursor: 'pointer'
      }}
      title={`Click to focus: ${camName}`}
    >
      <HLSVideoPlayer
        src={hlsSrc}
        onCanPlay={() => setStatus('live')}
        onError={() => setStatus('offline')}
      />

      {/* Status overlay while connecting */}
      {status === 'connecting' && (
        <div style={{
          position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: 'rgba(0,0,0,0.7)', zIndex: 5
        }}>
          <div style={{ textAlign: 'center' }}>
            <div style={{ width: '20px', height: '20px', border: '2px solid #06b6d4', borderTop: '2px solid transparent', borderRadius: '50%', animation: 'spin 1s linear infinite', margin: '0 auto 6px' }} />
            <span style={{ fontSize: '10px', color: '#94a3b8' }}>Connecting...</span>
          </div>
        </div>
      )}

      {/* Camera name overlay */}
      <div style={{
        position: 'absolute', top: 0, left: 0, right: 0,
        padding: '4px 8px',
        background: 'linear-gradient(to bottom, rgba(0,0,0,0.8), transparent)',
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        pointerEvents: 'none', zIndex: 11
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
          <span style={{
            width: '6px', height: '6px', borderRadius: '50%',
            background: status === 'live' ? '#10b981' : status === 'offline' ? '#f43f5e' : '#f59e0b'
          }} className={status === 'live' ? 'pulse-badge' : ''} />
          <span style={{ fontSize: '10px', fontWeight: '700', color: '#f8fafc', textShadow: '0 1px 2px rgba(0,0,0,0.8)' }}>
            {camName}
          </span>
        </div>
        <span style={{
          fontSize: '8px', padding: '1px 5px', borderRadius: '3px', fontWeight: '600',
          background: status === 'live' ? 'rgba(16,185,129,0.3)' : 'rgba(100,116,139,0.3)',
          color: status === 'live' ? '#34d399' : '#94a3b8'
        }}>
          {status === 'live' ? 'LIVE' : status === 'offline' ? 'OFFLINE' : '...'}
        </span>
      </div>
    </div>
  );
}

// ─── Main App ────────────────────────────────────────────────────
export default function App() {
  const [aiServiceHost] = useState(getAiServiceHost());
  const [vmsBackendHost] = useState(getVmsBackendHost());
  const [aiWsHost] = useState(getAiWsHost());

  const [activeTab, setActiveTab] = useState('livewall');
  const [events, setEvents] = useState([]);
  const [wsConnected, setWsConnected] = useState(false);
  const [selectedCamera, setSelectedCamera] = useState(null);

  const [gridSize, setGridSize] = useState(12);
  const [currentPage, setCurrentPage] = useState(1);
  const [isFullWall, setIsFullWall] = useState(false);

  const [activeCameras, setActiveCameras] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');

  // ─── On-Demand AI State ──────────────────────────────────────
  const [aiEnabled, setAiEnabled] = useState(false);
  const [aiDetections, setAiDetections] = useState([]);
  const [aiZones, setAiZones] = useState([]);
  const [aiModels, setAiModels] = useState({
    person: true, face: false, vehicle: false, intrusion: false
  });
  const [aiStatus, setAiStatus] = useState('idle'); // idle | starting | active | stopping

  // Intrusion zone drawing
  const [isDrawingZone, setIsDrawingZone] = useState(false);
  const [newZonePoints, setNewZonePoints] = useState([]);
  const [newZoneName, setNewZoneName] = useState('');
  const focusVideoRef = useRef(null);
  const focusContainerRef = useRef(null);

  // ─── Fetch Active Cameras ──────────────────────────────────────
  useEffect(() => {
    fetchActiveCameras();
  }, [vmsBackendHost, aiServiceHost]);

  const fetchActiveCameras = async () => {
    try {
      const res = await fetch(`${vmsBackendHost}/api/cameras/active`);
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data)) {
          const activeList = data
            .filter(c => c && (c.active !== false))
            .map((c, idx) => {
              // Extract the actual stream_id from the streams array — this is what HLS needs
              const streams = Array.isArray(c.streams) ? c.streams : [];
              const mainStream = streams.find(s => s && (String(s.profile_type || '').toUpperCase().includes('MAIN') || String(s.profile_type || '').toUpperCase().includes('HD')));
              const firstStream = mainStream || streams[0];
              const streamId = firstStream?.stream_id || c.server_camera_id || String(c.id || `cam_${idx}`);
              const camName = c.name || `Camera ${c.id || idx}`;

              return {
                id: streamId,
                name: `${camName} (${streamId})`,
                streams: streams
              };
            });
          if (activeList.length > 0) {
            setActiveCameras(activeList);
            return;
          }
        }
      }
    } catch (e) {}

    try {
      const res = await fetch(`${aiServiceHost}/api/ai/cameras`);
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data)) {
          setActiveCameras(data.map((c, idx) => ({
            id: c.id || `cam_${idx}`,
            name: `${c.name || 'Camera'} (${c.id || idx})`,
            streams: []
          })));
        }
      }
    } catch (e) {}
  };

  // ─── WebSocket Events ──────────────────────────────────────────
  useEffect(() => {
    let ws;
    const connectWS = () => {
      try {
        ws = new WebSocket(aiWsHost);
        ws.onopen = () => setWsConnected(true);
        ws.onmessage = (event) => {
          try {
            const payload = JSON.parse(event.data);
            if (payload.type === 'ai_event' && payload.data) {
              setEvents((prev) => [payload.data, ...(Array.isArray(prev) ? prev.slice(0, 99) : [])]);
            }
          } catch (e) {}
        };
        ws.onclose = () => { setWsConnected(false); setTimeout(connectWS, 3000); };
        ws.onerror = () => setWsConnected(false);
      } catch (err) { setWsConnected(false); }
    };
    connectWS();
    return () => { if (ws) ws.close(); };
  }, [aiWsHost]);

  // ─── Fetch Events on mount ────────────────────────────────────
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${aiServiceHost}/api/ai/events?limit=50`);
        if (res.ok) {
          const data = await res.json();
          if (Array.isArray(data)) setEvents(data);
        }
      } catch (e) {}
    })();
  }, [aiServiceHost]);

  // ─── On-Demand AI Control ──────────────────────────────────────
  const startAI = useCallback(async (camId) => {
    if (!camId) return;
    setAiStatus('starting');
    const enabledModels = Object.keys(aiModels).filter(k => aiModels[k]);
    try {
      await fetch(`${aiServiceHost}/api/ai/cameras/${camId}/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ active_models: enabledModels })
      });
      setAiStatus('active');
      setAiEnabled(true);
    } catch (e) {
      setAiStatus('idle');
    }
  }, [aiServiceHost, aiModels]);

  const stopAI = useCallback(async (camId) => {
    if (!camId) return;
    setAiStatus('stopping');
    try {
      await fetch(`${aiServiceHost}/api/ai/cameras/${camId}/stop`, { method: 'POST' });
    } catch (e) {}
    setAiEnabled(false);
    setAiDetections([]);
    setAiZones([]);
    setAiStatus('idle');
  }, [aiServiceHost]);

  // Poll detections when AI is active
  useEffect(() => {
    if (!aiEnabled || !selectedCamera) return;
    let active = true;

    const poll = async () => {
      while (active && aiEnabled) {
        try {
          const res = await fetch(`${aiServiceHost}/api/ai/streams/${selectedCamera.id}/detections`);
          if (res.ok) {
            const data = await res.json();
            if (active) {
              setAiDetections(Array.isArray(data.detections) ? data.detections : []);
              setAiZones(Array.isArray(data.zones) ? data.zones : []);
            }
          }
        } catch (e) {}
        await new Promise(r => setTimeout(r, 500));
      }
    };
    poll();
    return () => { active = false; };
  }, [aiEnabled, selectedCamera, aiServiceHost]);

  // Update models on the backend when toggled
  const toggleModel = useCallback(async (key) => {
    setAiModels(prev => {
      const updated = { ...prev, [key]: !prev[key] };
      if (selectedCamera && aiEnabled) {
        const enabledList = Object.keys(updated).filter(k => updated[k]);
        fetch(`${aiServiceHost}/api/ai/cameras/${selectedCamera.id}/models`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ active_models: enabledList })
        }).catch(() => {});
      }
      return updated;
    });
  }, [selectedCamera, aiEnabled, aiServiceHost]);

  // When selecting a different camera, stop AI on the previous one
  const handleFocusCamera = useCallback((cam) => {
    if (selectedCamera && aiEnabled && selectedCamera.id !== cam.id) {
      stopAI(selectedCamera.id);
    }
    setSelectedCamera(cam);
    setActiveTab('single');
  }, [selectedCamera, aiEnabled, stopAI]);

  // ─── Zone Drawing ─────────────────────────────────────────────
  const handleCanvasClick = (e) => {
    if (!isDrawingZone || !focusContainerRef.current) return;
    const rect = focusContainerRef.current.getBoundingClientRect();
    const x = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const y = Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height));
    setNewZonePoints(prev => [...(Array.isArray(prev) ? prev : []), { x: parseFloat(x.toFixed(3)), y: parseFloat(y.toFixed(3)) }]);
  };

  const saveZone = async () => {
    if (!Array.isArray(newZonePoints) || newZonePoints.length < 3 || !selectedCamera) {
      alert('A polygon zone must have at least 3 points.');
      return;
    }
    const zoneName = newZoneName.trim() || `Zone ${Date.now()}`;
    try {
      await fetch(`${aiServiceHost}/api/ai/zones`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          zone_id: `zone-${Date.now()}`,
          camera_id: selectedCamera.id,
          name: zoneName,
          polygon: newZonePoints,
          enabled: true
        })
      });
      setNewZonePoints([]);
      setNewZoneName('');
      setIsDrawingZone(false);
    } catch (e) { alert('Failed to save zone'); }
  };

  const deleteZone = async (zoneId) => {
    try {
      await fetch(`${aiServiceHost}/api/ai/zones/${zoneId}`, { method: 'DELETE' });
    } catch (e) {}
  };

  // ─── Filtering & Pagination ────────────────────────────────────
  const filteredCameras = useMemo(() => {
    if (!Array.isArray(activeCameras)) return [];
    return activeCameras.filter((cam) => {
      if (!cam || !cam.id) return false;
      const q = searchQuery.toLowerCase();
      return String(cam.id).toLowerCase().includes(q) || String(cam.name || '').toLowerCase().includes(q);
    });
  }, [activeCameras, searchQuery]);

  const totalPages = Math.ceil(filteredCameras.length / gridSize) || 1;

  useEffect(() => {
    if (currentPage > totalPages) setCurrentPage(1);
  }, [totalPages, currentPage]);

  const paginatedCameras = useMemo(() => {
    const start = (currentPage - 1) * gridSize;
    return filteredCameras.slice(start, start + gridSize);
  }, [filteredCameras, currentPage, gridSize]);

  const getGridColumns = () => {
    if (gridSize <= 4) return 2;
    if (gridSize <= 9) return 3;
    if (gridSize <= 16) return 4;
    return 6;
  };

  const safeEvents = Array.isArray(events) ? events : [];
  const safeDetections = Array.isArray(aiDetections) ? aiDetections : [];
  const safeZones = Array.isArray(aiZones) ? aiZones : [];

  // ─── Model Toggle UI Helper ────────────────────────────────────
  const ModelToggle = ({ icon: Icon, label, color, modelKey }) => (
    <div
      onClick={() => toggleModel(modelKey)}
      style={{
        display: 'flex', alignItems: 'center', gap: '8px',
        padding: '8px 12px', borderRadius: '8px', cursor: 'pointer',
        background: aiModels[modelKey] ? `${color}15` : 'rgba(15,23,42,0.6)',
        border: `1px solid ${aiModels[modelKey] ? `${color}40` : 'rgba(255,255,255,0.06)'}`,
        transition: 'all 0.2s'
      }}
    >
      <Icon size={16} color={aiModels[modelKey] ? color : '#64748b'} />
      <span style={{ fontSize: '12px', fontWeight: '600', color: aiModels[modelKey] ? color : '#64748b', flex: 1 }}>
        {label}
      </span>
      <div style={{
        width: '32px', height: '18px', borderRadius: '9px',
        background: aiModels[modelKey] ? color : '#334155',
        position: 'relative', transition: 'background 0.2s'
      }}>
        <div style={{
          width: '14px', height: '14px', borderRadius: '50%', background: '#fff',
          position: 'absolute', top: '2px',
          left: aiModels[modelKey] ? '16px' : '2px',
          transition: 'left 0.2s'
        }} />
      </div>
    </div>
  );

  return (
    <div style={{ minHeight: '100vh', backgroundColor: '#060913', color: '#f8fafc', padding: '16px' }}>
      {/* ─── Top Header ─────────────────────────────────────────── */}
      <header className="glass-panel" style={{ padding: '14px 24px', marginBottom: '16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div style={{ width: '40px', height: '40px', borderRadius: '10px', background: 'linear-gradient(135deg, #06b6d4, #6366f1)', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 0 20px rgba(6,182,212,0.4)' }}>
            <Cpu size={22} color="#ffffff" />
          </div>
          <div>
            <h1 style={{ fontSize: '18px', fontWeight: '700', letterSpacing: '-0.5px', background: 'linear-gradient(to right, #ffffff, #94a3b8)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
              AI Analytics Center
            </h1>
            <p style={{ fontSize: '11px', color: '#64748b' }}>
              On-Demand AI Detection • {activeCameras.length} Cameras • {aiEnabled ? 'AI Active' : 'AI Idle'}
            </p>
          </div>
        </div>

        {/* Tab Navigation */}
        <div style={{ display: 'flex', gap: '4px', background: 'rgba(15,23,42,0.8)', padding: '4px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.08)' }}>
          {[
            { key: 'livewall', icon: LayoutGrid, label: 'Live Wall' },
            { key: 'single', icon: Eye, label: 'Focus + AI' },
            { key: 'events', icon: Bell, label: `Events (${safeEvents.length})` },
          ].map(tab => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              style={{
                padding: '6px 14px', borderRadius: '6px', border: 'none', cursor: 'pointer', fontSize: '13px', fontWeight: '600',
                background: activeTab === tab.key ? 'linear-gradient(135deg, #06b6d4, #0284c7)' : 'transparent',
                color: activeTab === tab.key ? '#ffffff' : '#94a3b8', display: 'flex', alignItems: 'center', gap: '6px'
              }}
            >
              <tab.icon size={15} />{tab.label}
            </button>
          ))}
        </div>

        {/* Status */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div style={{
            display: 'flex', alignItems: 'center', gap: '6px', padding: '6px 12px', borderRadius: '20px',
            background: wsConnected ? 'rgba(16,185,129,0.15)' : 'rgba(244,63,94,0.15)',
            border: wsConnected ? '1px solid rgba(16,185,129,0.3)' : '1px solid rgba(244,63,94,0.3)'
          }}>
            <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: wsConnected ? '#10b981' : '#f43f5e' }} className={wsConnected ? 'pulse-badge' : ''} />
            <span style={{ fontSize: '12px', fontWeight: '600', color: wsConnected ? '#34d399' : '#fb7185' }}>
              {wsConnected ? 'Connected' : 'Offline'}
            </span>
          </div>
        </div>
      </header>

      {/* ─── Main Content ─────────────────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: activeTab === 'single' ? '1fr 320px' : '1fr 320px', gap: '16px' }}>
        <main>
          {/* ─── LIVE WALL TAB ─────────────────────────────── */}
          {activeTab === 'livewall' && (
            <div className="glass-panel" style={{ padding: '16px' }}>
              {/* Control Bar */}
              <div style={{
                display: 'flex', flexWrap: 'wrap', gap: '12px', justifyContent: 'space-between', alignItems: 'center',
                marginBottom: '14px', background: 'rgba(15,23,42,0.6)', padding: '10px 14px', borderRadius: '8px',
                border: '1px solid rgba(255,255,255,0.06)'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <Video size={16} color="#10b981" />
                  <span style={{ fontSize: '13px', fontWeight: '700', color: '#f8fafc' }}>
                    Live Wall — {filteredCameras.length} cameras
                  </span>
                  <span style={{ fontSize: '10px', color: '#64748b', fontStyle: 'italic' }}>
                    Click any camera to focus + enable AI
                  </span>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', background: '#090d16', border: '1px solid #334155', borderRadius: '6px', padding: '4px 10px', width: '200px' }}>
                    <Search size={14} color="#64748b" />
                    <input
                      type="text"
                      placeholder="Search cameras..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      style={{ background: 'transparent', border: 'none', color: '#f8fafc', outline: 'none', fontSize: '12px', width: '100%' }}
                    />
                  </div>

                  <button onClick={fetchActiveCameras} style={{ padding: '5px 10px', background: '#1e293b', border: '1px solid #334155', color: '#fff', borderRadius: '6px', fontSize: '11px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <RotateCw size={12} /> Refresh
                  </button>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <span style={{ fontSize: '11px', color: '#94a3b8' }}>Grid:</span>
                    <select value={gridSize} onChange={(e) => { setGridSize(Number(e.target.value)); setCurrentPage(1); }}
                      style={{ background: '#090d16', color: '#38bdf8', border: '1px solid #06b6d4', padding: '4px 8px', borderRadius: '6px', fontSize: '11px', fontWeight: '600', outline: 'none' }}
                    >
                      <option value={4}>2×2</option>
                      <option value={9}>3×3</option>
                      <option value={12}>4×3</option>
                      <option value={16}>4×4</option>
                      <option value={24}>6×4</option>
                      <option value={36}>6×6</option>
                    </select>
                  </div>

                  {totalPages > 1 && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <button onClick={() => setCurrentPage(p => Math.max(1, p - 1))} disabled={currentPage === 1}
                        style={{ padding: '4px 8px', background: '#1e293b', border: '1px solid #334155', color: '#fff', borderRadius: '4px', fontSize: '11px', cursor: 'pointer', opacity: currentPage === 1 ? 0.4 : 1 }}>
                        <ChevronLeft size={12} />
                      </button>
                      <span style={{ fontSize: '11px', color: '#cbd5e1', minWidth: '50px', textAlign: 'center' }}>{currentPage}/{totalPages}</span>
                      <button onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))} disabled={currentPage === totalPages}
                        style={{ padding: '4px 8px', background: '#1e293b', border: '1px solid #334155', color: '#fff', borderRadius: '4px', fontSize: '11px', cursor: 'pointer', opacity: currentPage === totalPages ? 0.4 : 1 }}>
                        <ChevronRight size={12} />
                      </button>
                    </div>
                  )}

                  <button onClick={() => setIsFullWall(true)}
                    style={{ padding: '5px 10px', background: 'rgba(6,182,212,0.2)', border: '1px solid #06b6d4', color: '#38bdf8', borderRadius: '6px', fontSize: '11px', fontWeight: '600', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <Maximize2 size={12} /> Full Wall
                  </button>
                </div>
              </div>

              {/* Camera Grid */}
              <div style={{ display: 'grid', gridTemplateColumns: `repeat(${getGridColumns()}, 1fr)`, gap: '10px', width: '100%' }}>
                {paginatedCameras.map((cam, idx) => (
                  <LiveWallCell
                    key={cam?.id ? `${cam.id}_${idx}` : `cam_${idx}`}
                    camera={cam}
                    vmsBackendHost={vmsBackendHost}
                    onFocusCamera={handleFocusCamera}
                  />
                ))}
              </div>
            </div>
          )}

          {/* ─── FOCUS STREAM + AI TAB ─────────────────────── */}
          {activeTab === 'single' && (
            <div className="glass-panel" style={{ padding: '16px' }}>
              {/* Camera Selector */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <select
                    value={selectedCamera?.id || ''}
                    onChange={(e) => {
                      const cam = activeCameras.find(c => c.id === e.target.value);
                      if (cam) handleFocusCamera(cam);
                    }}
                    style={{ background: '#090d16', color: '#38bdf8', border: '1px solid #06b6d4', padding: '8px 14px', borderRadius: '6px', fontSize: '13px', fontWeight: '600', outline: 'none', maxWidth: '320px' }}
                  >
                    <option value="">Select a camera...</option>
                    {filteredCameras.map((cam) => (
                      <option key={cam.id} value={cam.id}>{cam.name}</option>
                    ))}
                  </select>
                </div>

                {/* AI Control Toggle */}
                {selectedCamera && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <button
                      onClick={() => aiEnabled ? stopAI(selectedCamera.id) : startAI(selectedCamera.id)}
                      style={{
                        padding: '8px 16px', borderRadius: '8px', border: 'none', cursor: 'pointer',
                        fontSize: '13px', fontWeight: '700', display: 'flex', alignItems: 'center', gap: '6px',
                        background: aiEnabled
                          ? 'linear-gradient(135deg, #ef4444, #dc2626)'
                          : 'linear-gradient(135deg, #10b981, #059669)',
                        color: '#fff',
                        boxShadow: aiEnabled
                          ? '0 0 15px rgba(239,68,68,0.4)'
                          : '0 0 15px rgba(16,185,129,0.4)',
                        transition: 'all 0.3s'
                      }}
                    >
                      {aiEnabled ? <><StopCircle size={16} /> Stop AI</> : <><PlayCircle size={16} /> Enable AI Detection</>}
                    </button>
                    {aiStatus === 'active' && (
                      <span style={{ fontSize: '11px', color: '#34d399', display: 'flex', alignItems: 'center', gap: '4px' }}>
                        <Activity size={12} /> Processing
                      </span>
                    )}
                  </div>
                )}
              </div>

              {/* Video Player + AI Overlay */}
              {selectedCamera ? (
                <div
                  ref={focusContainerRef}
                  onClick={handleCanvasClick}
                  style={{
                    position: 'relative', width: '100%', aspectRatio: '16/9',
                    borderRadius: '10px', overflow: 'hidden', background: '#020617',
                    border: isDrawingZone ? '2px dashed #06b6d4' : '1px solid #1e293b',
                    cursor: isDrawingZone ? 'crosshair' : 'default'
                  }}
                >
                  <HLSVideoPlayer
                    src={`${vmsBackendHost}/api/streams/${encodeURIComponent(selectedCamera.id)}/live/index.m3u8`}
                    videoRef={focusVideoRef}
                  />

                  {/* AI Detection Overlay (only when AI is enabled) */}
                  {aiEnabled && (
                    <svg style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', pointerEvents: 'none', zIndex: 10 }}>
                      {/* Intrusion Zones */}
                      {safeZones.map((z) => (
                        <polygon
                          key={z.zone_id}
                          points={getPolygonPointsStr(z.polygon)}
                          fill="rgba(244, 63, 94, 0.2)"
                          stroke="#f43f5e"
                          strokeWidth="2"
                        />
                      ))}

                      {/* Detection Bounding Boxes */}
                      {safeDetections.map((det, idx) => {
                        const [x1, y1, x2, y2] = getBboxCoords(det.bbox);
                        const cn = String(det.class_name || 'person').toLowerCase();
                        const color = cn === 'person' ? '#10b981' : cn === 'face' ? '#38bdf8' : cn === 'vehicle' ? '#fbbf24' : '#f43f5e';
                        const conf = Number(det.confidence || 0.85);
                        return (
                          <g key={idx}>
                            <rect
                              x={`${x1 * 100}%`} y={`${y1 * 100}%`}
                              width={`${(x2 - x1) * 100}%`} height={`${(y2 - y1) * 100}%`}
                              fill="none" stroke={color} strokeWidth="2.5"
                              filter="drop-shadow(0px 0px 4px rgba(0,0,0,0.8))"
                            />
                            <rect
                              x={`${x1 * 100}%`} y={`${Math.max(0, y1 * 100 - 4)}%`}
                              width="80" height="16" fill={color} opacity="0.9" rx="3"
                            />
                            <text
                              x={`${x1 * 100 + 1}%`} y={`${Math.max(0, y1 * 100 - 0.5)}%`}
                              fill="#ffffff" fontSize="11" fontWeight="bold"
                            >
                              {cn.toUpperCase()} {(conf * 100).toFixed(0)}%
                            </text>
                          </g>
                        );
                      })}

                      {/* Drawing zone points */}
                      {isDrawingZone && Array.isArray(newZonePoints) && newZonePoints.length > 0 && (
                        <g>
                          <polygon points={getPolygonPointsStr(newZonePoints)} fill="rgba(6,182,212,0.25)" stroke="#06b6d4" strokeWidth="2" strokeDasharray="4" />
                          {newZonePoints.map((p, idx) => (
                            <circle key={idx} cx={`${(Number(p?.x) || 0) * 100}%`} cy={`${(Number(p?.y) || 0) * 100}%`} r="5" fill="#06b6d4" />
                          ))}
                        </g>
                      )}
                    </svg>
                  )}

                  {/* Camera label */}
                  <div style={{
                    position: 'absolute', top: 0, left: 0, right: 0, padding: '6px 12px',
                    background: 'linear-gradient(to bottom, rgba(0,0,0,0.8), transparent)',
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center', pointerEvents: 'none', zIndex: 11
                  }}>
                    <span style={{ fontSize: '12px', fontWeight: '700', color: '#f8fafc' }}>
                      {selectedCamera.name}
                    </span>
                    {aiEnabled && (
                      <span style={{
                        fontSize: '9px', background: 'rgba(16,185,129,0.3)', color: '#34d399',
                        padding: '2px 8px', borderRadius: '4px', fontWeight: '700'
                      }}>
                        AI ACTIVE
                      </span>
                    )}
                  </div>
                </div>
              ) : (
                <div style={{
                  width: '100%', aspectRatio: '16/9', background: '#020617', borderRadius: '10px',
                  border: '1px solid #1e293b', display: 'flex', alignItems: 'center', justifyContent: 'center'
                }}>
                  <div style={{ textAlign: 'center', color: '#64748b' }}>
                    <Eye size={32} style={{ marginBottom: '8px', opacity: 0.5 }} />
                    <p style={{ fontSize: '14px' }}>Select a camera from the dropdown or click one on the Live Wall</p>
                  </div>
                </div>
              )}

              {/* Detection Results Table (when AI active) */}
              {aiEnabled && safeDetections.length > 0 && (
                <div style={{ marginTop: '12px', background: 'rgba(15,23,42,0.6)', borderRadius: '8px', padding: '12px', border: '1px solid rgba(255,255,255,0.06)' }}>
                  <h4 style={{ fontSize: '12px', fontWeight: '700', color: '#38bdf8', marginBottom: '8px' }}>
                    Live Detections ({safeDetections.length})
                  </h4>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                    {safeDetections.map((det, idx) => {
                      const cn = String(det.class_name || 'object').toLowerCase();
                      const color = cn === 'person' ? '#10b981' : cn === 'face' ? '#38bdf8' : cn === 'vehicle' ? '#fbbf24' : '#f43f5e';
                      return (
                        <span key={idx} style={{
                          padding: '4px 10px', borderRadius: '6px', fontSize: '11px', fontWeight: '600',
                          background: `${color}20`, color: color, border: `1px solid ${color}40`
                        }}>
                          {cn.toUpperCase()} {((Number(det.confidence) || 0.85) * 100).toFixed(0)}%
                          {det.attributes?.mode && <span style={{ opacity: 0.6, marginLeft: '4px' }}>({det.attributes.mode})</span>}
                        </span>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ─── EVENTS TAB ────────────────────────────────── */}
          {activeTab === 'events' && (
            <div className="glass-panel" style={{ padding: '20px' }}>
              <h2 style={{ fontSize: '16px', fontWeight: '700', marginBottom: '16px' }}>AI Event History</h2>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid #1e293b', color: '#64748b', textAlign: 'left' }}>
                      <th style={{ padding: '10px' }}>Time</th>
                      <th style={{ padding: '10px' }}>Event</th>
                      <th style={{ padding: '10px' }}>Camera</th>
                      <th style={{ padding: '10px' }}>Confidence</th>
                    </tr>
                  </thead>
                  <tbody>
                    {safeEvents.map((evt, idx) => (
                      <tr key={evt.event_id || idx} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                        <td style={{ padding: '10px', color: '#94a3b8' }}>{evt.formatted_time || '-'}</td>
                        <td style={{ padding: '10px' }}>
                          <span style={{
                            padding: '4px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: '600',
                            background: String(evt.event_type || '').includes('intrusion') ? 'rgba(244,63,94,0.2)' : 'rgba(16,185,129,0.2)',
                            color: String(evt.event_type || '').includes('intrusion') ? '#fb7185' : '#34d399'
                          }}>
                            {evt.label || 'Event'}
                          </span>
                        </td>
                        <td style={{ padding: '10px' }}>{evt.camera_name || evt.camera_id}</td>
                        <td style={{ padding: '10px', fontWeight: '600' }}>{((Number(evt.confidence) || 0.8) * 100).toFixed(0)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </main>

        {/* ─── Right Sidebar ────────────────────────────────────── */}
        <aside>
          {/* AI Model Controls (visible in Focus tab) */}
          {activeTab === 'single' && selectedCamera && (
            <div className="glass-panel" style={{ padding: '16px', marginBottom: '12px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
                <Settings2 size={16} color="#06b6d4" />
                <h3 style={{ fontSize: '13px', fontWeight: '700' }}>AI Model Controls</h3>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                <ModelToggle icon={UserCheck} label="Person Detection" color="#10b981" modelKey="person" />
                <ModelToggle icon={Smile} label="Face Recognition" color="#38bdf8" modelKey="face" />
                <ModelToggle icon={Car} label="Vehicle Detection" color="#fbbf24" modelKey="vehicle" />
                <ModelToggle icon={ShieldAlert} label="Intrusion Detection" color="#f43f5e" modelKey="intrusion" />
              </div>

              {/* Zone Drawing Controls */}
              {aiModels.intrusion && aiEnabled && (
                <div style={{ marginTop: '12px', paddingTop: '12px', borderTop: '1px solid rgba(255,255,255,0.06)' }}>
                  {isDrawingZone ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                      <input
                        type="text" placeholder="Zone name..."
                        value={newZoneName} onChange={(e) => setNewZoneName(e.target.value)}
                        style={{ background: '#0f172a', border: '1px solid #334155', color: '#fff', padding: '6px 10px', borderRadius: '6px', fontSize: '12px' }}
                      />
                      <div style={{ display: 'flex', gap: '6px' }}>
                        <button onClick={saveZone} style={{ flex: 1, padding: '6px', background: '#10b981', color: '#fff', border: 'none', borderRadius: '6px', cursor: 'pointer', fontSize: '11px', fontWeight: '600' }}>
                          Save ({Array.isArray(newZonePoints) ? newZonePoints.length : 0} pts)
                        </button>
                        <button onClick={() => { setIsDrawingZone(false); setNewZonePoints([]); }} style={{ padding: '6px 10px', background: '#334155', color: '#fff', border: 'none', borderRadius: '6px', cursor: 'pointer', fontSize: '11px' }}>
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <button onClick={() => setIsDrawingZone(true)} style={{ width: '100%', padding: '8px', background: 'rgba(6,182,212,0.15)', border: '1px solid rgba(6,182,212,0.3)', color: '#38bdf8', borderRadius: '6px', cursor: 'pointer', fontSize: '12px', fontWeight: '600', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px' }}>
                      <Plus size={14} /> Draw Intrusion Zone
                    </button>
                  )}

                  {/* Existing Zones */}
                  {safeZones.length > 0 && (
                    <div style={{ marginTop: '8px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      {safeZones.map(z => (
                        <div key={z.zone_id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '4px 8px', background: 'rgba(244,63,94,0.1)', borderRadius: '4px', fontSize: '11px' }}>
                          <span style={{ color: '#fb7185' }}>{z.name}</span>
                          <button onClick={() => deleteZone(z.zone_id)} style={{ background: 'none', border: 'none', color: '#f43f5e', cursor: 'pointer', padding: '2px' }}>
                            <Trash2 size={12} />
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Event Stream */}
          <div className="glass-panel" style={{ padding: '16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Zap size={16} color="#06b6d4" />
                <h3 style={{ fontSize: '13px', fontWeight: '700' }}>Event Stream</h3>
              </div>
              <span style={{ fontSize: '10px', background: 'rgba(6,182,212,0.15)', color: '#38bdf8', padding: '2px 8px', borderRadius: '10px' }}>
                WebSocket
              </span>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '420px', overflowY: 'auto' }}>
              {safeEvents.length === 0 ? (
                <p style={{ fontSize: '12px', color: '#64748b', textAlign: 'center', padding: '20px 0' }}>
                  Enable AI on a camera to see events...
                </p>
              ) : (
                safeEvents.slice(0, 30).map((evt, idx) => {
                  const isIntrusion = String(evt.event_type || '').includes('intrusion');
                  return (
                    <div
                      key={evt.event_id || idx}
                      className="glass-card"
                      style={{
                        padding: '10px',
                        borderLeft: isIntrusion ? '3px solid #f43f5e' : '3px solid #06b6d4',
                        background: isIntrusion ? 'rgba(244,63,94,0.06)' : 'rgba(30,41,59,0.4)'
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <span style={{ fontSize: '11px', fontWeight: '700', color: isIntrusion ? '#fb7185' : '#38bdf8' }}>
                          {evt.label || 'AI Event'}
                        </span>
                        <span style={{ fontSize: '9px', color: '#64748b' }}>{String(evt.formatted_time || '').split(' ')[1] || '-'}</span>
                      </div>
                      <p style={{ fontSize: '10px', color: '#94a3b8', marginTop: '3px' }}>
                        {evt.camera_name || evt.camera_id} • {((Number(evt.confidence) || 0.8) * 100).toFixed(0)}%
                      </p>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </aside>
      </div>

      {/* ─── Full Wall Modal ────────────────────────────────────── */}
      {isFullWall && (
        <div style={{ position: 'fixed', top: 0, left: 0, width: '100vw', height: '100vh', zIndex: 9999, background: '#060913', padding: '16px', overflowY: 'auto' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <h2 style={{ fontSize: '18px', fontWeight: '700', color: '#06b6d4' }}>Full Live Camera Wall</h2>
            <button onClick={() => setIsFullWall(false)} style={{ padding: '6px 14px', background: '#f43f5e', color: '#fff', border: 'none', borderRadius: '6px', cursor: 'pointer', fontSize: '12px', fontWeight: '600' }}>
              Exit Full Wall
            </button>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: `repeat(${getGridColumns()}, 1fr)`, gap: '10px' }}>
            {paginatedCameras.map((cam, idx) => (
              <LiveWallCell
                key={cam?.id ? `fw_${cam.id}_${idx}` : `fw_${idx}`}
                camera={cam}
                vmsBackendHost={vmsBackendHost}
                onFocusCamera={(c) => { setIsFullWall(false); handleFocusCamera(c); }}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
