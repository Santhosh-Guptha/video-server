import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
  ShieldAlert, UserCheck, Smile, Car, Bell, Sliders,
  Eye, Cpu, Radio, Plus, Trash2, Zap, Search, Grid, LayoutGrid,
  Video, Users, Maximize2, RotateCw, ChevronLeft, ChevronRight, X
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

// WebRTC Player Component with AI Markings Overlay
function WebRTCStreamPlayer({ camera, aiServiceHost, vmsBackendHost, onFocusCamera }) {
  const videoRef = useRef(null);
  const pcRef = useRef(null);
  const [webrtcConnected, setWebrtcConnected] = useState(false);
  const [detections, setDetections] = useState([]);
  const [zones, setZones] = useState([]);

  // Resolve stream ID for WebRTC
  const streamId = useMemo(() => {
    if (camera.streams && camera.streams.length > 0) {
      // Prefer grid or main stream
      const gridStream = camera.streams.find(s => s.stream_id.includes('_grid')) || camera.streams[0];
      return gridStream.stream_id;
    }
    return camera.id;
  }, [camera]);

  // Start WebRTC WHEP Stream
  useEffect(() => {
    let isMounted = true;

    async function startWebRTC() {
      try {
        if (pcRef.current) {
          pcRef.current.close();
          pcRef.current = null;
        }

        const pc = new RTCPeerConnection({
          iceServers: [{ urls: 'stun:stun.l.google.com:19302' }]
        });
        pcRef.current = pc;

        pc.addTransceiver('video', { direction: 'recvonly' });

        pc.ontrack = (event) => {
          if (!isMounted) return;
          if (videoRef.current && event.streams && event.streams[0]) {
            videoRef.current.srcObject = event.streams[0];
            videoRef.current.play().catch(() => {});
            setWebrtcConnected(true);
          }
        };

        const offer = await pc.createOffer();
        if (!isMounted) return;
        await pc.setLocalDescription(offer);
        if (!isMounted) return;

        // WHEP Signaling POST request to VMS Backend
        const user_id = `user_${Math.random().toString(36).substring(2, 9)}`;
        const tab_id = `tab_${Math.random().toString(36).substring(2, 9)}`;
        const whepUrl = `${vmsBackendHost}/api/streams/${encodeURIComponent(streamId)}/live/whep?user_id=${user_id}&browser_tab_id=${tab_id}`;

        const resp = await fetch(whepUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/sdp' },
          body: offer.sdp
        });

        if (resp.ok && isMounted) {
          const answerSdp = await resp.text();
          await pc.setRemoteDescription(new RTCSessionDescription({
            type: 'answer',
            sdp: answerSdp
          }));
        }
      } catch (err) {
        console.warn(`WebRTC stream negotiation failed for ${streamId}, falling back to AI MJPEG stream:`, err);
        setWebrtcConnected(false);
      }
    }

    startWebRTC();

    return () => {
      isMounted = false;
      if (pcRef.current) {
        pcRef.current.close();
        pcRef.current = null;
      }
    };
  }, [streamId, vmsBackendHost]);

  // Telemetry polling for real-time AI detections & polygon intrusion zones
  useEffect(() => {
    let intervalId = setInterval(async () => {
      try {
        const res = await fetch(`${aiServiceHost}/api/ai/streams/${camera.id}/detections`);
        if (res.ok) {
          const data = await res.json();
          setDetections(data.detections || []);
          setZones(data.zones || []);
        }
      } catch (e) {}
    }, 400);

    return () => clearInterval(intervalId);
  }, [camera.id, aiServiceHost]);

  return (
    <div
      className="glass-card"
      onDoubleClick={() => onFocusCamera && onFocusCamera(camera)}
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
      title="Double-click to focus camera"
    >
      {/* Video Element (WebRTC / MJPEG Fallback) */}
      {webrtcConnected ? (
        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted
          style={{ width: '100%', height: '100%', objectFit: 'contain' }}
        />
      ) : (
        <img
          src={`${aiServiceHost}/api/ai/streams/${camera.id}/live`}
          alt={camera.name}
          style={{ width: '100%', height: '100%', objectFit: 'contain' }}
          onError={(e) => {
            e.target.src = `${aiServiceHost}/api/ai/streams/${camera.id}/frame?t=${Date.now()}`;
          }}
        />
      )}

      {/* AI Visual Markings Overlay Layer (Bounding Boxes & Zones) */}
      <svg style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', pointerEvents: 'none' }}>
        {/* Intrusion Polygon Zones */}
        {zones.map((z) => (
          <polygon
            key={z.zone_id}
            points={z.polygon.map((p) => `${p.x * 100}%,${p.y * 100}%`).join(' ')}
            fill="rgba(244, 63, 94, 0.25)"
            stroke="#f43f5e"
            strokeWidth="2"
          />
        ))}

        {/* Real-time AI Bounding Boxes */}
        {detections.map((det, idx) => {
          const [x1, y1, x2, y2] = det.bbox; // Normalized [0, 1]
          const color = det.class_name === 'person' ? '#10b981' :
                        det.class_name === 'face' ? '#38bdf8' :
                        det.class_name === 'vehicle' ? '#fbbf24' : '#f43f5e';
          return (
            <g key={idx}>
              <rect
                x={`${x1 * 100}%`}
                y={`${y1 * 100}%`}
                width={`${(x2 - x1) * 100}%`}
                height={`${(y2 - y1) * 100}%`}
                fill="none"
                stroke={color}
                strokeWidth="2"
                strokeDasharray={det.class_name === 'intrusion' ? '4' : '0'}
              />
              <rect
                x={`${x1 * 100}%`}
                y={`${Math.max(0, y1 * 100 - 4)}%`}
                width="60"
                height="14"
                fill={color}
                opacity="0.85"
                rx="2"
              />
              <text
                x={`${x1 * 100 + 1}%`}
                y={`${Math.max(0, y1 * 100 - 1)}%`}
                fill="#ffffff"
                fontSize="9"
                fontWeight="bold"
              >
                {det.class_name.toUpperCase()} {(det.confidence * 100).toFixed(0)}%
              </text>
            </g>
          );
        })}
      </svg>

      {/* Stream Label Header Overlay */}
      <div
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          padding: '4px 8px',
          background: 'linear-gradient(to bottom, rgba(0,0,0,0.85), transparent)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          pointerEvents: 'none'
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
          <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#10b981' }} className="pulse-badge" />
          <span style={{ fontSize: '10px', fontWeight: '700', color: '#f8fafc', textShadow: '0 1px 2px rgba(0,0,0,0.8)' }}>
            {camera.name}
          </span>
        </div>
        <span style={{ fontSize: '9px', background: webrtcConnected ? 'rgba(16,185,129,0.3)' : 'rgba(6,182,212,0.3)', color: webrtcConnected ? '#34d399' : '#38bdf8', padding: '1px 5px', borderRadius: '3px', fontWeight: '600' }}>
          {webrtcConnected ? 'WEBRTC LIVE' : 'AI LIVE'}
        </span>
      </div>
    </div>
  );
}

export default function App() {
  const [aiServiceHost] = useState(getAiServiceHost());
  const [vmsBackendHost] = useState(getVmsBackendHost());
  const [aiWsHost] = useState(getAiWsHost());

  const [activeTab, setActiveTab] = useState('livewall'); // 'livewall', 'single', 'zones', 'events', 'models'
  const [events, setEvents] = useState([]);
  const [zones, setZones] = useState([]);
  const [wsConnected, setWsConnected] = useState(false);
  const [selectedCamera, setSelectedCamera] = useState('VMSTEST1002C5_HD');
  const [selectedModalCamera, setSelectedModalCamera] = useState(null);

  // Live Wall Grid & Pagination state
  const [gridSize, setGridSize] = useState(12); // default 12 (4x3 layout)
  const [currentPage, setCurrentPage] = useState(1);
  const [isFullWall, setIsFullWall] = useState(false);

  // Active Streaming Camera Catalog
  const [activeCameras, setActiveCameras] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');

  // Model toggles
  const [activeModels, setActiveModels] = useState({
    person: true,
    face: true,
    vehicle: true,
    intrusion: true
  });
  const [confidenceThreshold, setConfidenceThreshold] = useState(0.5);

  // Polygon Zone Drawing state
  const [isDrawingZone, setIsDrawingZone] = useState(false);
  const [newZonePoints, setNewZonePoints] = useState([]);
  const [newZoneName, setNewZoneName] = useState('');
  const videoCanvasRef = useRef(null);

  // Event log filter state
  const [eventFilter, setEventFilter] = useState('all');

  // Fetch ONLY active streaming cameras from VMS backend API /api/cameras/active
  useEffect(() => {
    fetchActiveCameras();
  }, [vmsBackendHost, aiServiceHost]);

  // Load initial events and zones
  useEffect(() => {
    fetchEvents();
    fetchZones();
  }, [selectedCamera, aiServiceHost]);

  // Setup WebSocket connection to AI microservice
  useEffect(() => {
    let ws;
    const connectWS = () => {
      try {
        ws = new WebSocket(aiWsHost);
        ws.onopen = () => setWsConnected(true);
        ws.onmessage = (event) => {
          try {
            const payload = JSON.parse(event.data);
            if (payload.type === 'ai_event') {
              setEvents((prev) => [payload.data, ...prev.slice(0, 99)]);
            }
          } catch (e) {
            console.error('Failed parsing WS message:', e);
          }
        };
        ws.onclose = () => {
          setWsConnected(false);
          setTimeout(connectWS, 3000);
        };
        ws.onerror = () => setWsConnected(false);
      } catch (err) {
        setWsConnected(false);
      }
    };

    connectWS();
    return () => {
      if (ws) ws.close();
    };
  }, [aiWsHost]);

  const fetchActiveCameras = async () => {
    try {
      // Query VMS backend /api/cameras/active to get ONLY live streaming cameras
      const res = await fetch(`${vmsBackendHost}/api/cameras/active`);
      if (res.ok) {
        const data = await res.json();
        // Filter standard cameras that are active & online
        const activeList = data.filter(c => c.active && c.streams && c.streams.length > 0).map(c => ({
          id: c.server_camera_id || c.id,
          name: c.name || `Camera ${c.id}`,
          streams: c.streams
        }));
        if (activeList.length > 0) {
          setActiveCameras(activeList);
          if (!selectedCamera || !activeList.some(c => c.id === selectedCamera)) {
            setSelectedCamera(activeList[0].id);
          }
          return;
        }
      }
    } catch (e) {
      console.warn('Failed fetching active cameras from VMS backend:', e);
    }

    // Fallback to AI service camera endpoint
    try {
      const res = await fetch(`${aiServiceHost}/api/ai/cameras`);
      if (res.ok) {
        const data = await res.json();
        setActiveCameras(data.map(c => ({ id: c.id, name: c.name, streams: [] })));
      }
    } catch (e) {}
  };

  const fetchEvents = async () => {
    try {
      const res = await fetch(`${aiServiceHost}/api/ai/events?limit=50`);
      if (res.ok) {
        const data = await res.json();
        setEvents(data);
      }
    } catch (e) {}
  };

  const fetchZones = async () => {
    try {
      const res = await fetch(`${aiServiceHost}/api/ai/zones?camera_id=${selectedCamera}`);
      if (res.ok) {
        const data = await res.json();
        setZones(data);
      }
    } catch (e) {}
  };

  const toggleModel = async (modelKey) => {
    const updated = { ...activeModels, [modelKey]: !activeModels[modelKey] };
    setActiveModels(updated);
    const enabledList = Object.keys(updated).filter((k) => updated[k]);

    try {
      await fetch(`${aiServiceHost}/api/ai/cameras/${selectedCamera}/models`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ active_models: enabledList })
      });
    } catch (e) {
      console.error('Failed to update models:', e);
    }
  };

  const handleCanvasClick = (e) => {
    if (!isDrawingZone || !videoCanvasRef.current) return;

    const rect = videoCanvasRef.current.getBoundingClientRect();
    const x = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const y = Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height));

    setNewZonePoints([...newZonePoints, { x: parseFloat(x.toFixed(3)), y: parseFloat(y.toFixed(3)) }]);
  };

  const saveZone = async () => {
    if (newZonePoints.length < 3) {
      alert('A polygon zone must have at least 3 points.');
      return;
    }
    const zoneName = newZoneName.trim() || `Intrusion Zone ${zones.length + 1}`;
    const zonePayload = {
      zone_id: `zone-${Date.now()}`,
      camera_id: selectedCamera,
      name: zoneName,
      polygon: newZonePoints,
      enabled: true
    };

    try {
      const res = await fetch(`${aiServiceHost}/api/ai/zones`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(zonePayload)
      });
      if (res.ok) {
        setNewZonePoints([]);
        setNewZoneName('');
        setIsDrawingZone(false);
        fetchZones();
      }
    } catch (e) {
      alert('Failed to save zone');
    }
  };

  const deleteZone = async (zoneId) => {
    try {
      const res = await fetch(`${aiServiceHost}/api/ai/zones/${zoneId}`, {
        method: 'DELETE'
      });
      if (res.ok) {
        fetchZones();
      }
    } catch (e) {}
  };

  // Filter ONLY active cameras by search query
  const filteredCameras = useMemo(() => {
    return activeCameras.filter((cam) => {
      return cam.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
             cam.name.toLowerCase().includes(searchQuery.toLowerCase());
    });
  }, [activeCameras, searchQuery]);

  const totalPages = Math.ceil(filteredCameras.length / gridSize) || 1;

  useEffect(() => {
    if (currentPage > totalPages) {
      setCurrentPage(1);
    }
  }, [totalPages, currentPage]);

  const paginatedCameras = useMemo(() => {
    const start = (currentPage - 1) * gridSize;
    return filteredCameras.slice(start, start + gridSize);
  }, [filteredCameras, currentPage, gridSize]);

  const filteredEvents = events.filter((evt) => {
    if (eventFilter === 'all') return true;
    return evt.event_type.includes(eventFilter);
  });

  const getGridColumns = () => {
    if (gridSize === 4) return 2;
    if (gridSize === 9) return 3;
    if (gridSize === 12) return 4;
    if (gridSize === 16) return 4;
    if (gridSize === 24) return 6;
    if (gridSize === 36) return 6;
    return 4;
  };

  const renderCameraWallGrid = () => (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: `repeat(${getGridColumns()}, 1fr)`,
        gap: '10px',
        width: '100%'
      }}
    >
      {paginatedCameras.map((cam) => (
        <WebRTCStreamPlayer
          key={cam.id}
          camera={cam}
          aiServiceHost={aiServiceHost}
          vmsBackendHost={vmsBackendHost}
          onFocusCamera={(c) => setSelectedModalCamera(c)}
        />
      ))}
    </div>
  );

  return (
    <div style={{ minHeight: '100vh', backgroundColor: '#060913', color: '#f8fafc', padding: '16px' }}>
      {/* Top Header */}
      <header className="glass-panel" style={{ padding: '14px 24px', marginBottom: '16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div style={{ width: '40px', height: '40px', borderRadius: '10px', background: 'linear-gradient(135deg, #06b6d4, #6366f1)', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 0 20px rgba(6,182,212,0.4)' }}>
            <Cpu size={22} color="#ffffff" />
          </div>
          <div>
            <h1 style={{ fontSize: '18px', fontWeight: '700', letterSpacing: '-0.5px', background: 'linear-gradient(to right, #ffffff, #94a3b8)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
              AI Live Camera Wall Center
            </h1>
            <p style={{ fontSize: '11px', color: '#64748b' }}>
              Real-Time WebRTC Video Stream & AI Detection Overlay | {activeCameras.length} Active Live Cameras
            </p>
          </div>
        </div>

        {/* Tab Navigation */}
        <div style={{ display: 'flex', gap: '6px', background: 'rgba(15,23,42,0.8)', padding: '4px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.08)' }}>
          <button
            onClick={() => setActiveTab('livewall')}
            style={{
              padding: '6px 14px', borderRadius: '6px', border: 'none', cursor: 'pointer', fontSize: '13px', fontWeight: '600',
              background: activeTab === 'livewall' ? 'linear-gradient(135deg, #06b6d4, #0284c7)' : 'transparent',
              color: activeTab === 'livewall' ? '#ffffff' : '#94a3b8', display: 'flex', alignItems: 'center', gap: '6px'
            }}
          >
            <LayoutGrid size={15} /> Live Camera Wall
          </button>
          <button
            onClick={() => setActiveTab('single')}
            style={{
              padding: '6px 14px', borderRadius: '6px', border: 'none', cursor: 'pointer', fontSize: '13px', fontWeight: '600',
              background: activeTab === 'single' ? 'linear-gradient(135deg, #06b6d4, #0284c7)' : 'transparent',
              color: activeTab === 'single' ? '#ffffff' : '#94a3b8', display: 'flex', alignItems: 'center', gap: '6px'
            }}
          >
            <Eye size={15} /> Focus Stream
          </button>
          <button
            onClick={() => setActiveTab('zones')}
            style={{
              padding: '6px 14px', borderRadius: '6px', border: 'none', cursor: 'pointer', fontSize: '13px', fontWeight: '600',
              background: activeTab === 'zones' ? 'linear-gradient(135deg, #06b6d4, #0284c7)' : 'transparent',
              color: activeTab === 'zones' ? '#ffffff' : '#94a3b8', display: 'flex', alignItems: 'center', gap: '6px'
            }}
          >
            <ShieldAlert size={15} /> Intrusion Zones ({zones.length})
          </button>
          <button
            onClick={() => setActiveTab('events')}
            style={{
              padding: '6px 14px', borderRadius: '6px', border: 'none', cursor: 'pointer', fontSize: '13px', fontWeight: '600',
              background: activeTab === 'events' ? 'linear-gradient(135deg, #06b6d4, #0284c7)' : 'transparent',
              color: activeTab === 'events' ? '#ffffff' : '#94a3b8', display: 'flex', alignItems: 'center', gap: '6px'
            }}
          >
            <Bell size={15} /> AI Events ({events.length})
          </button>
          <button
            onClick={() => setActiveTab('models')}
            style={{
              padding: '6px 14px', borderRadius: '6px', border: 'none', cursor: 'pointer', fontSize: '13px', fontWeight: '600',
              background: activeTab === 'models' ? 'linear-gradient(135deg, #06b6d4, #0284c7)' : 'transparent',
              color: activeTab === 'models' ? '#ffffff' : '#94a3b8', display: 'flex', alignItems: 'center', gap: '6px'
            }}
          >
            <Sliders size={15} /> Model Controls
          </button>
        </div>

        {/* Live Service Status Indicator */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', background: wsConnected ? 'rgba(16,185,129,0.15)' : 'rgba(244,63,94,0.15)', padding: '6px 12px', borderRadius: '20px', border: wsConnected ? '1px solid rgba(16,185,129,0.3)' : '1px solid rgba(244,63,94,0.3)' }}>
            <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: wsConnected ? '#10b981' : '#f43f5e' }} className={wsConnected ? 'pulse-badge' : ''} />
            <span style={{ fontSize: '12px', fontWeight: '600', color: wsConnected ? '#34d399' : '#fb7185' }}>
              {wsConnected ? 'AI Engine Live' : 'AI Offline'}
            </span>
          </div>
        </div>
      </header>

      {/* Main Content Layout */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: '16px' }}>
        
        {/* Left Main View */}
        <main>
          {activeTab === 'livewall' && (
            <div className="glass-panel" style={{ padding: '16px' }}>
              
              {/* Live Wall Control Header Bar */}
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px', background: 'rgba(15,23,42,0.6)', padding: '10px 14px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.06)' }}>
                
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#10b981' }} className="pulse-badge" />
                  <span style={{ fontSize: '13px', fontWeight: '700', color: '#f8fafc' }}>
                    Live Wall — {filteredCameras.length} active live cameras online
                  </span>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                  {/* Search Input */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', background: '#090d16', border: '1px solid #334155', borderRadius: '6px', padding: '4px 10px', width: '220px' }}>
                    <Search size={14} color="#64748b" />
                    <input
                      type="text"
                      placeholder="Search active live cameras..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      style={{ background: 'transparent', border: 'none', color: '#f8fafc', outline: 'none', fontSize: '12px', width: '100%' }}
                    />
                  </div>

                  {/* Refresh Button */}
                  <button onClick={fetchActiveCameras} style={{ padding: '5px 10px', background: '#1e293b', border: '1px solid #334155', color: '#fff', borderRadius: '6px', fontSize: '11px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <RotateCw size={12} /> Refresh
                  </button>

                  {/* Grid Size Picker */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <span style={{ fontSize: '11px', color: '#94a3b8' }}>Grid size:</span>
                    <select
                      value={gridSize}
                      onChange={(e) => {
                        setGridSize(Number(e.target.value));
                        setCurrentPage(1);
                      }}
                      style={{ background: '#090d16', color: '#38bdf8', border: '1px solid #06b6d4', padding: '4px 8px', borderRadius: '6px', fontSize: '11px', fontWeight: '600', outline: 'none' }}
                    >
                      <option value={4}>4 (2x2)</option>
                      <option value={9}>9 (3x3)</option>
                      <option value={12}>12 (4x3)</option>
                      <option value={16}>16 (4x4)</option>
                      <option value={24}>24 (6x4)</option>
                      <option value={36}>36 (6x6)</option>
                    </select>
                  </div>

                  {/* Pagination Controls */}
                  {totalPages > 1 && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <button
                        onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                        disabled={currentPage === 1}
                        style={{ padding: '4px 8px', background: '#1e293b', border: '1px solid #334155', color: '#fff', borderRadius: '4px', fontSize: '11px', cursor: 'pointer', opacity: currentPage === 1 ? 0.4 : 1 }}
                      >
                        <ChevronLeft size={12} />
                      </button>
                      <span style={{ fontSize: '11px', color: '#cbd5e1', minWidth: '60px', textAlign: 'center' }}>
                        {currentPage} / {totalPages}
                      </span>
                      <button
                        onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                        disabled={currentPage === totalPages}
                        style={{ padding: '4px 8px', background: '#1e293b', border: '1px solid #334155', color: '#fff', borderRadius: '4px', fontSize: '11px', cursor: 'pointer', opacity: currentPage === totalPages ? 0.4 : 1 }}
                      >
                        <ChevronRight size={12} />
                      </button>
                    </div>
                  )}

                  {/* Full Wall Toggle */}
                  <button
                    onClick={() => setIsFullWall(true)}
                    style={{ padding: '5px 10px', background: 'rgba(6,182,212,0.2)', border: '1px solid #06b6d4', color: '#38bdf8', borderRadius: '6px', fontSize: '11px', fontWeight: '600', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px' }}
                  >
                    <Maximize2 size={12} /> Full Wall
                  </button>
                </div>
              </div>

              {/* Render Camera Wall Grid */}
              {renderCameraWallGrid()}
            </div>
          )}

          {activeTab === 'single' && (
            <div className="glass-panel" style={{ padding: '20px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                <select
                  value={selectedCamera}
                  onChange={(e) => setSelectedCamera(e.target.value)}
                  style={{ background: '#090d16', color: '#38bdf8', border: '1px solid #06b6d4', padding: '8px 14px', borderRadius: '6px', fontSize: '14px', fontWeight: '600', outline: 'none' }}
                >
                  {filteredCameras.map((cam) => (
                    <option key={cam.id} value={cam.id}>{cam.name}</option>
                  ))}
                </select>
              </div>

              <div style={{ position: 'relative', width: '100%', borderRadius: '8px', overflow: 'hidden', background: '#020617', border: '1px solid #1e293b', aspectRatio: '16/9' }}>
                <WebRTCStreamPlayer
                  camera={activeCameras.find(c => c.id === selectedCamera) || { id: selectedCamera, name: selectedCamera }}
                  aiServiceHost={aiServiceHost}
                  vmsBackendHost={vmsBackendHost}
                />
              </div>
            </div>
          )}

          {activeTab === 'zones' && (
            <div className="glass-panel" style={{ padding: '20px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                <div>
                  <h2 style={{ fontSize: '16px', fontWeight: '700' }}>Polygonal Intrusion Zone Configurator</h2>
                  <p style={{ fontSize: '12px', color: '#64748b' }}>Click on the live video canvas to set polygon boundary points</p>
                </div>
                <div style={{ display: 'flex', gap: '10px' }}>
                  {isDrawingZone ? (
                    <>
                      <button onClick={saveZone} style={{ padding: '8px 14px', background: '#10b981', color: '#fff', border: 'none', borderRadius: '6px', cursor: 'pointer', fontSize: '13px', fontWeight: '600' }}>
                        Save Zone ({newZonePoints.length} points)
                      </button>
                      <button onClick={() => { setIsDrawingZone(false); setNewZonePoints([]); }} style={{ padding: '8px 14px', background: '#334155', color: '#fff', border: 'none', borderRadius: '6px', cursor: 'pointer', fontSize: '13px' }}>
                        Cancel
                      </button>
                    </>
                  ) : (
                    <button onClick={() => setIsDrawingZone(true)} style={{ padding: '8px 14px', background: '#06b6d4', color: '#fff', border: 'none', borderRadius: '6px', cursor: 'pointer', fontSize: '13px', fontWeight: '600', display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <Plus size={16} /> Draw New Intrusion Zone
                    </button>
                  )}
                </div>
              </div>

              {isDrawingZone && (
                <div style={{ marginBottom: '12px', display: 'flex', gap: '10px' }}>
                  <input
                    type="text"
                    placeholder="Enter Zone Name (e.g. Perimeter Gate A)"
                    value={newZoneName}
                    onChange={(e) => setNewZoneName(e.target.value)}
                    style={{ flex: 1, background: '#0f172a', border: '1px solid #334155', color: '#fff', padding: '8px 12px', borderRadius: '6px', fontSize: '13px' }}
                  />
                </div>
              )}

              <div
                ref={videoCanvasRef}
                onClick={handleCanvasClick}
                style={{
                  position: 'relative', width: '100%', aspectRatio: '16/9', background: '#020617',
                  borderRadius: '8px', border: isDrawingZone ? '2px dashed #06b6d4' : '1px solid #1e293b',
                  cursor: isDrawingZone ? 'crosshair' : 'default', overflow: 'hidden'
                }}
              >
                <img
                  src={`${aiServiceHost}/api/ai/streams/${selectedCamera}/frame?t=${Date.now()}`}
                  alt="Zone Canvas"
                  style={{ width: '100%', height: '100%', objectFit: 'contain', pointerEvents: 'none' }}
                />
                
                <svg style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', pointerEvents: 'none' }}>
                  {zones.map((z) => (
                    <g key={z.zone_id}>
                      <polygon
                        points={z.polygon.map((p) => `${p.x * 100}%,${p.y * 100}%`).join(' ')}
                        fill="rgba(244, 63, 94, 0.25)"
                        stroke="#f43f5e"
                        strokeWidth="2"
                      />
                    </g>
                  ))}
                  {newZonePoints.length > 0 && (
                    <g>
                      <polygon
                        points={newZonePoints.map((p) => `${p.x * 100}%,${p.y * 100}%`).join(' ')}
                        fill="rgba(6, 182, 212, 0.3)"
                        stroke="#06b6d4"
                        strokeWidth="2"
                        strokeDasharray="4"
                      />
                      {newZonePoints.map((p, idx) => (
                        <circle key={idx} cx={`${p.x * 100}%`} cy={`${p.y * 100}%`} r="5" fill="#06b6d4" />
                      ))}
                    </g>
                  )}
                </svg>
              </div>
            </div>
          )}

          {activeTab === 'events' && (
            <div className="glass-panel" style={{ padding: '20px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                <h2 style={{ fontSize: '16px', fontWeight: '700' }}>Historical AI Analytics Logs</h2>
              </div>

              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid #1e293b', color: '#64748b', textAlign: 'left' }}>
                      <th style={{ padding: '10px' }}>Time</th>
                      <th style={{ padding: '10px' }}>Event Type</th>
                      <th style={{ padding: '10px' }}>Camera</th>
                      <th style={{ padding: '10px' }}>Confidence</th>
                      <th style={{ padding: '10px' }}>Details</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredEvents.map((evt) => (
                      <tr key={evt.event_id} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                        <td style={{ padding: '10px', color: '#94a3b8' }}>{evt.formatted_time}</td>
                        <td style={{ padding: '10px' }}>
                          <span style={{
                            padding: '4px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: '600',
                            background: evt.event_type.includes('intrusion') ? 'rgba(244,63,94,0.2)' : evt.event_type.includes('person') ? 'rgba(16,185,129,0.2)' : 'rgba(6,182,212,0.2)',
                            color: evt.event_type.includes('intrusion') ? '#fb7185' : evt.event_type.includes('person') ? '#34d399' : '#38bdf8'
                          }}>
                            {evt.label}
                          </span>
                        </td>
                        <td style={{ padding: '10px' }}>{evt.camera_name}</td>
                        <td style={{ padding: '10px', fontWeight: '600' }}>{(evt.confidence * 100).toFixed(0)}%</td>
                        <td style={{ padding: '10px', color: '#94a3b8' }}>{evt.details ? JSON.stringify(evt.details) : '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {activeTab === 'models' && (
            <div className="glass-panel" style={{ padding: '20px' }}>
              <h2 style={{ fontSize: '16px', fontWeight: '700', marginBottom: '16px' }}>Production AI Model Zoo Controls</h2>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                <div className="glass-card" style={{ padding: '16px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <UserCheck color="#10b981" />
                      <div>
                        <h3 style={{ fontSize: '14px', fontWeight: '600' }}>Person Detection Engine</h3>
                      </div>
                    </div>
                    <input type="checkbox" checked={activeModels.person} onChange={() => toggleModel('person')} style={{ width: '18px', height: '18px', cursor: 'pointer' }} />
                  </div>
                </div>

                <div className="glass-card" style={{ padding: '16px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <Smile color="#38bdf8" />
                      <div>
                        <h3 style={{ fontSize: '14px', fontWeight: '600' }}>Face Recognition Engine</h3>
                      </div>
                    </div>
                    <input type="checkbox" checked={activeModels.face} onChange={() => toggleModel('face')} style={{ width: '18px', height: '18px', cursor: 'pointer' }} />
                  </div>
                </div>
              </div>
            </div>
          )}
        </main>

        {/* Right Sidebar */}
        <aside className="glass-panel" style={{ padding: '16px', height: 'fit-content' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Zap size={18} color="#06b6d4" />
              <h3 style={{ fontSize: '14px', fontWeight: '700' }}>Real-Time Event Stream</h3>
            </div>
            <span style={{ fontSize: '11px', background: 'rgba(6,182,212,0.15)', color: '#38bdf8', padding: '2px 8px', borderRadius: '10px' }}>
              Live WebSocket
            </span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', maxHeight: '580px', overflowY: 'auto' }}>
            {events.length === 0 ? (
              <p style={{ fontSize: '12px', color: '#64748b', textAlign: 'center', padding: '20px 0' }}>
                Listening for real-time AI events...
              </p>
            ) : (
              events.map((evt) => {
                const isIntrusion = evt.event_type.includes('intrusion');
                return (
                  <div
                    key={evt.event_id}
                    className="glass-card"
                    style={{
                      padding: '12px',
                      borderLeft: isIntrusion ? '3px solid #f43f5e' : '3px solid #06b6d4',
                      background: isIntrusion ? 'rgba(244,63,94,0.08)' : 'rgba(30,41,59,0.5)'
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                      <span style={{ fontSize: '12px', fontWeight: '700', color: isIntrusion ? '#fb7185' : '#38bdf8' }}>
                        {evt.label}
                      </span>
                      <span style={{ fontSize: '10px', color: '#64748b' }}>{evt.formatted_time.split(' ')[1]}</span>
                    </div>
                    <p style={{ fontSize: '11px', color: '#94a3b8', marginTop: '4px' }}>
                      {evt.camera_name} | Confidence: {(evt.confidence * 100).toFixed(0)}%
                    </p>
                  </div>
                );
              })
            )}
          </div>
        </aside>
      </div>

      {/* Full Wall Modal */}
      {isFullWall && (
        <div style={{ position: 'fixed', top: 0, left: 0, width: '100vw', height: '100vh', zIndex: 9999, background: '#060913', padding: '16px', overflowY: 'auto' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <h2 style={{ fontSize: '18px', fontWeight: '700', color: '#06b6d4' }}>Full Live Camera Wall</h2>
            <button onClick={() => setIsFullWall(false)} style={{ padding: '6px 14px', background: '#f43f5e', color: '#fff', border: 'none', borderRadius: '6px', cursor: 'pointer', fontSize: '12px', fontWeight: '600' }}>
              Exit Full Wall
            </button>
          </div>
          {renderCameraWallGrid()}
        </div>
      )}

      {/* Selected Camera Details Modal */}
      {selectedModalCamera && (
        <div style={{ position: 'fixed', top: 0, left: 0, width: '100vw', height: '100vh', zIndex: 9999, background: 'rgba(0,0,0,0.85)', backdropFilter: 'blur(8px)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '20px' }}>
          <div className="glass-panel" style={{ width: '90%', maxWidth: '900px', padding: '20px', position: 'relative' }}>
            <button onClick={() => setSelectedModalCamera(null)} style={{ position: 'absolute', top: '16px', right: '16px', background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer' }}>
              <X size={20} />
            </button>
            <h3 style={{ fontSize: '16px', fontWeight: '700', marginBottom: '12px', color: '#38bdf8' }}>
              {selectedModalCamera.name} ({selectedModalCamera.id})
            </h3>
            <div style={{ position: 'relative', width: '100%', aspectRatio: '16/9', borderRadius: '8px', overflow: 'hidden', background: '#020617' }}>
              <WebRTCStreamPlayer
                camera={selectedModalCamera}
                aiServiceHost={aiServiceHost}
                vmsBackendHost={vmsBackendHost}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
