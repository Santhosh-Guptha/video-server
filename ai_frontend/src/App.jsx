import React, { useState, useEffect, useRef } from 'react';
import {
  ShieldAlert, UserCheck, Smile, Car, Bell, Sliders,
  Eye, Cpu, Radio, Plus, Trash2, Zap, Search, Grid, LayoutGrid,
  Video
} from 'lucide-react';

const getAiServiceHost = () => {
  if (typeof window !== 'undefined') {
    const hostname = window.location.hostname || 'localhost';
    return `http://${hostname}:8001`;
  }
  return 'http://localhost:8001';
};

const getAiWsHost = () => {
  if (typeof window !== 'undefined') {
    const hostname = window.location.hostname || 'localhost';
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${hostname}:8001/ws/ai-events`;
  }
  return 'ws://localhost:8001/ws/ai-events';
};

export default function App() {
  const [aiServiceHost] = useState(getAiServiceHost());
  const [aiWsHost] = useState(getAiWsHost());

  const [activeTab, setActiveTab] = useState('live'); // 'live', 'zones', 'events', 'models'
  const [events, setEvents] = useState([]);
  const [zones, setZones] = useState([]);
  const [wsConnected, setWsConnected] = useState(false);
  const [selectedCamera, setSelectedCamera] = useState('VMSTEST1002C5_HD');
  const [gridMode, setGridMode] = useState('1x1'); // '1x1' or '2x2'

  // Stream rendering mode fallback state
  const [streamFallbackMode, setStreamFallbackMode] = useState(false);
  const [currentFrameUrl, setCurrentFrameUrl] = useState('');

  // Camera List & Search/Filter state
  const [cameraList, setCameraList] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [profileFilter, setProfileFilter] = useState('ALL'); // 'ALL', 'HD', 'NORMAL'

  // Model toggles per camera
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

  // Fetch camera catalog
  useEffect(() => {
    fetchCameras();
  }, [aiServiceHost]);

  // Load initial events and zones
  useEffect(() => {
    fetchEvents();
    fetchZones();
    setStreamFallbackMode(false);
  }, [selectedCamera, aiServiceHost]);

  // Fallback 10 FPS JPEG Frame polling loop if MJPEG stream triggers error
  useEffect(() => {
    let intervalId;
    if (streamFallbackMode) {
      intervalId = setInterval(() => {
        setCurrentFrameUrl(`${aiServiceHost}/api/ai/streams/${selectedCamera}/frame?t=${Date.now()}`);
      }, 100);
    }
    return () => {
      if (intervalId) clearInterval(intervalId);
    };
  }, [streamFallbackMode, selectedCamera, aiServiceHost]);

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

  const fetchCameras = async () => {
    try {
      const res = await fetch(`${aiServiceHost}/api/ai/cameras`);
      if (res.ok) {
        const data = await res.json();
        if (data && data.length > 0) {
          setCameraList(data);
          if (!selectedCamera || !data.some(c => c.id === selectedCamera)) {
            setSelectedCamera(data[0].id);
          }
        }
      }
    } catch (e) {
      console.warn('Failed loading cameras:', e);
    }
  };

  const fetchEvents = async () => {
    try {
      const res = await fetch(`${aiServiceHost}/api/ai/events?limit=50`);
      if (res.ok) {
        const data = await res.json();
        setEvents(data);
      }
    } catch (e) {
      console.warn('ai_service offline or loading:', e);
    }
  };

  const fetchZones = async () => {
    try {
      const res = await fetch(`${aiServiceHost}/api/ai/zones?camera_id=${selectedCamera}`);
      if (res.ok) {
        const data = await res.json();
        setZones(data);
      }
    } catch (e) {
      console.warn('ai_service offline or loading:', e);
    }
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
    } catch (e) {
      console.error('Failed to delete zone:', e);
    }
  };

  const filteredCameras = cameraList.filter((cam) => {
    const matchesSearch = cam.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
                          cam.name.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesProfile = profileFilter === 'ALL' ||
                           (profileFilter === 'HD' && cam.id.includes('HD')) ||
                           (profileFilter === 'NORMAL' && (cam.id.includes('NORMAL') || cam.id.includes('SUB')));
    return matchesSearch && matchesProfile;
  });

  const filteredEvents = events.filter((evt) => {
    if (eventFilter === 'all') return true;
    return evt.event_type.includes(eventFilter);
  });

  return (
    <div style={{ minHeight: '100vh', backgroundColor: '#060913', color: '#f8fafc', padding: '16px' }}>
      {/* Header Bar */}
      <header className="glass-panel" style={{ padding: '14px 24px', marginBottom: '16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div style={{ width: '40px', height: '40px', borderRadius: '10px', background: 'linear-gradient(135deg, #06b6d4, #6366f1)', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 0 20px rgba(6,182,212,0.4)' }}>
            <Cpu size={22} color="#ffffff" />
          </div>
          <div>
            <h1 style={{ fontSize: '18px', fontWeight: '700', letterSpacing: '-0.5px', background: 'linear-gradient(to right, #ffffff, #94a3b8)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
              Production AI Vision Analytics Center
            </h1>
            <p style={{ fontSize: '11px', color: '#64748b' }}>
              Real-World CCTV Computer Vision | {cameraList.length} Active Platform Cameras
            </p>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div style={{ display: 'flex', gap: '6px', background: 'rgba(15,23,42,0.8)', padding: '4px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.08)' }}>
          <button
            onClick={() => setActiveTab('live')}
            style={{
              padding: '6px 14px', borderRadius: '6px', border: 'none', cursor: 'pointer', fontSize: '13px', fontWeight: '600',
              background: activeTab === 'live' ? 'linear-gradient(135deg, #06b6d4, #0284c7)' : 'transparent',
              color: activeTab === 'live' ? '#ffffff' : '#94a3b8', display: 'flex', alignItems: 'center', gap: '6px'
            }}
          >
            <Eye size={15} /> Live AI View
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

      {/* Main Dashboard Layout */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: '16px' }}>
        
        {/* Main Content Area */}
        <main>
          {activeTab === 'live' && (
            <div className="glass-panel" style={{ padding: '16px' }}>
              
              {/* Production Camera Search Bar & Layout Controls */}
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px', background: 'rgba(15,23,42,0.6)', padding: '10px 14px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.06)' }}>
                
                {/* Search Input Box */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flex: 1, maxWidth: '380px', background: '#090d16', border: '1px solid #334155', borderRadius: '6px', padding: '6px 12px' }}>
                  <Search size={15} color="#64748b" />
                  <input
                    type="text"
                    placeholder={`Search ${cameraList.length} cameras by ID or name...`}
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    style={{ background: 'transparent', border: 'none', color: '#f8fafc', outline: 'none', fontSize: '13px', width: '100%' }}
                  />
                  {searchQuery && (
                    <button onClick={() => setSearchQuery('')} style={{ background: 'none', border: 'none', color: '#64748b', cursor: 'pointer', fontSize: '12px' }}>✕</button>
                  )}
                </div>

                {/* Profile Filter & Camera Dropdown */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <select
                    value={profileFilter}
                    onChange={(e) => setProfileFilter(e.target.value)}
                    style={{ background: '#090d16', color: '#94a3b8', border: '1px solid #334155', padding: '6px 10px', borderRadius: '6px', fontSize: '12px', outline: 'none' }}
                  >
                    <option value="ALL">All Streams ({cameraList.length})</option>
                    <option value="HD">HD Streams Only</option>
                    <option value="NORMAL">Sub-Streams Only</option>
                  </select>

                  <select
                    value={selectedCamera}
                    onChange={(e) => {
                      setSelectedCamera(e.target.value);
                      setStreamFallbackMode(false);
                    }}
                    style={{ background: '#090d16', color: '#38bdf8', border: '1px solid #06b6d4', padding: '6px 12px', borderRadius: '6px', fontSize: '13px', fontWeight: '600', outline: 'none', maxWidth: '240px' }}
                  >
                    {filteredCameras.length === 0 ? (
                      <option value="">No cameras match search</option>
                    ) : (
                      filteredCameras.map((cam) => (
                        <option key={cam.id} value={cam.id}>{cam.name}</option>
                      ))
                    )}
                  </select>
                </div>

                {/* Grid Mode View Toggles */}
                <div style={{ display: 'flex', gap: '4px', background: '#090d16', padding: '2px', borderRadius: '6px', border: '1px solid #334155' }}>
                  <button
                    onClick={() => setGridMode('1x1')}
                    style={{ padding: '6px 10px', background: gridMode === '1x1' ? '#06b6d4' : 'transparent', border: 'none', borderRadius: '4px', color: '#fff', cursor: 'pointer' }}
                    title="1x1 Single Focus Stream View"
                  >
                    <Grid size={15} />
                  </button>
                  <button
                    onClick={() => setGridMode('2x2')}
                    style={{ padding: '6px 10px', background: gridMode === '2x2' ? '#06b6d4' : 'transparent', border: 'none', borderRadius: '4px', color: '#fff', cursor: 'pointer' }}
                    title="2x2 Multi-Camera Matrix View"
                  >
                    <LayoutGrid size={15} />
                  </button>
                </div>
              </div>

              {/* Active AI Model Indicators */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Video size={16} color="#06b6d4" />
                  <span style={{ fontSize: '13px', fontWeight: '600', color: '#cbd5e1' }}>
                    Active Feed: {selectedCamera}
                  </span>
                </div>
                <div style={{ display: 'flex', gap: '6px' }}>
                  <span style={{ fontSize: '11px', background: activeModels.person ? 'rgba(16,185,129,0.2)' : 'rgba(51,65,85,0.4)', color: activeModels.person ? '#34d399' : '#64748b', padding: '3px 8px', borderRadius: '4px' }}>Person</span>
                  <span style={{ fontSize: '11px', background: activeModels.face ? 'rgba(6,182,212,0.2)' : 'rgba(51,65,85,0.4)', color: activeModels.face ? '#38bdf8' : '#64748b', padding: '3px 8px', borderRadius: '4px' }}>Face</span>
                  <span style={{ fontSize: '11px', background: activeModels.vehicle ? 'rgba(245,158,11,0.2)' : 'rgba(51,65,85,0.4)', color: activeModels.vehicle ? '#fbbf24' : '#64748b', padding: '3px 8px', borderRadius: '4px' }}>Vehicle/ANPR</span>
                  <span style={{ fontSize: '11px', background: activeModels.intrusion ? 'rgba(244,63,94,0.2)' : 'rgba(51,65,85,0.4)', color: activeModels.intrusion ? '#fb7185' : '#64748b', padding: '3px 8px', borderRadius: '4px' }}>Intrusion</span>
                </div>
              </div>

              {/* Real Video Stream Viewport */}
              {gridMode === '1x1' ? (
                <div style={{ position: 'relative', width: '100%', borderRadius: '8px', overflow: 'hidden', background: '#020617', border: '1px solid #1e293b', aspectRatio: '16/9' }}>
                  <img
                    key={selectedCamera}
                    src={streamFallbackMode ? currentFrameUrl : `${aiServiceHost}/api/ai/streams/${selectedCamera}/live`}
                    alt="Real AI Camera Feed"
                    style={{ width: '100%', height: '100%', objectFit: 'contain' }}
                    onError={() => {
                      if (!streamFallbackMode) {
                        console.warn('MJPEG stream failed, switching to high-speed frame polling mode');
                        setStreamFallbackMode(true);
                      }
                    }}
                  />
                  <div style={{ position: 'absolute', top: '12px', left: '12px', display: 'flex', alignItems: 'center', gap: '8px', background: 'rgba(0,0,0,0.65)', backdropFilter: 'blur(8px)', padding: '4px 10px', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.1)' }}>
                    <Radio size={13} color="#10b981" />
                    <span style={{ fontSize: '11px', fontWeight: '600', letterSpacing: '0.5px' }}>
                      {streamFallbackMode ? 'REAL LIVE CCTV FEED (POLLING MODE)' : 'REAL LIVE CCTV FEED (MJPEG)'}
                    </span>
                  </div>
                </div>
              ) : (
                /* 2x2 Multi-Camera Grid View */
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                  {filteredCameras.slice(0, 4).map((cam) => (
                    <div key={cam.id} style={{ position: 'relative', width: '100%', aspectRatio: '16/9', borderRadius: '6px', overflow: 'hidden', background: '#020617', border: '1px solid #1e293b' }}>
                      <img
                        src={`${aiServiceHost}/api/ai/streams/${cam.id}/live`}
                        alt={cam.name}
                        style={{ width: '100%', height: '100%', objectFit: 'contain' }}
                        onError={(e) => {
                          e.target.src = `${aiServiceHost}/api/ai/streams/${cam.id}/frame?t=${Date.now()}`;
                        }}
                      />
                      <div style={{ position: 'absolute', bottom: '8px', left: '8px', background: 'rgba(0,0,0,0.7)', padding: '2px 8px', borderRadius: '4px', fontSize: '10px', fontWeight: '600', color: '#38bdf8' }}>
                        {cam.id}
                      </div>
                    </div>
                  ))}
                </div>
              )}
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

              <div style={{ marginTop: '20px' }}>
                <h3 style={{ fontSize: '14px', fontWeight: '600', marginBottom: '10px' }}>Active Intrusion Zones</h3>
                {zones.length === 0 ? (
                  <p style={{ fontSize: '13px', color: '#64748b' }}>No intrusion zones configured for this camera yet.</p>
                ) : (
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: '12px' }}>
                    {zones.map((z) => (
                      <div key={z.zone_id} className="glass-card" style={{ padding: '12px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div>
                          <p style={{ fontSize: '13px', fontWeight: '600' }}>{z.name}</p>
                          <p style={{ fontSize: '11px', color: '#64748b' }}>{z.polygon.length} Vertices Polygon</p>
                        </div>
                        <button onClick={() => deleteZone(z.zone_id)} style={{ background: 'rgba(244,63,94,0.15)', color: '#fb7185', border: '1px solid rgba(244,63,94,0.3)', padding: '6px', borderRadius: '6px', cursor: 'pointer' }}>
                          <Trash2 size={14} />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {activeTab === 'events' && (
            <div className="glass-panel" style={{ padding: '20px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                <h2 style={{ fontSize: '16px', fontWeight: '700' }}>Historical AI Analytics Logs</h2>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button onClick={() => setEventFilter('all')} style={{ padding: '6px 12px', borderRadius: '6px', fontSize: '12px', background: eventFilter === 'all' ? '#06b6d4' : '#1e293b', color: '#fff', border: 'none', cursor: 'pointer' }}>All</button>
                  <button onClick={() => setEventFilter('person')} style={{ padding: '6px 12px', borderRadius: '6px', fontSize: '12px', background: eventFilter === 'person' ? '#06b6d4' : '#1e293b', color: '#fff', border: 'none', cursor: 'pointer' }}>Person</button>
                  <button onClick={() => setEventFilter('face')} style={{ padding: '6px 12px', borderRadius: '6px', fontSize: '12px', background: eventFilter === 'face' ? '#06b6d4' : '#1e293b', color: '#fff', border: 'none', cursor: 'pointer' }}>Face</button>
                  <button onClick={() => setEventFilter('intrusion')} style={{ padding: '6px 12px', borderRadius: '6px', fontSize: '12px', background: eventFilter === 'intrusion' ? '#06b6d4' : '#1e293b', color: '#fff', border: 'none', cursor: 'pointer' }}>Intrusions</button>
                </div>
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
              <h2 style={{ fontSize: '16px', fontWeight: '700', marginBottom: '16px' }}>Production AI Model Zoo & Sensitivity Controls</h2>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                <div className="glass-card" style={{ padding: '16px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <UserCheck color="#10b981" />
                      <div>
                        <h3 style={{ fontSize: '14px', fontWeight: '600' }}>Person Detection Engine</h3>
                        <p style={{ fontSize: '12px', color: '#64748b' }}>Real Human Body & Centroid Tracker</p>
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
                        <p style={{ fontSize: '12px', color: '#64748b' }}>Facial Bounding Box & Landmark Estimator</p>
                      </div>
                    </div>
                    <input type="checkbox" checked={activeModels.face} onChange={() => toggleModel('face')} style={{ width: '18px', height: '18px', cursor: 'pointer' }} />
                  </div>
                </div>

                <div className="glass-card" style={{ padding: '16px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <Car color="#fbbf24" />
                      <div>
                        <h3 style={{ fontSize: '14px', fontWeight: '600' }}>Vehicle & ANPR Detector</h3>
                        <p style={{ fontSize: '12px', color: '#64748b' }}>Vehicle & License Plate Region Extractor</p>
                      </div>
                    </div>
                    <input type="checkbox" checked={activeModels.vehicle} onChange={() => toggleModel('vehicle')} style={{ width: '18px', height: '18px', cursor: 'pointer' }} />
                  </div>
                </div>

                <div className="glass-card" style={{ padding: '16px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <ShieldAlert color="#fb7185" />
                      <div>
                        <h3 style={{ fontSize: '14px', fontWeight: '600' }}>Intrusion & Tripwire Engine</h3>
                        <p style={{ fontSize: '12px', color: '#64748b' }}>Geometric Polygon Breach Alarm</p>
                      </div>
                    </div>
                    <input type="checkbox" checked={activeModels.intrusion} onChange={() => toggleModel('intrusion')} style={{ width: '18px', height: '18px', cursor: 'pointer' }} />
                  </div>
                </div>
              </div>

              <div className="glass-card" style={{ marginTop: '20px', padding: '16px' }}>
                <h3 style={{ fontSize: '14px', fontWeight: '600', marginBottom: '8px' }}>Global Confidence Threshold: {(confidenceThreshold * 100).toFixed(0)}%</h3>
                <input
                  type="range"
                  min="0.1"
                  max="0.9"
                  step="0.05"
                  value={confidenceThreshold}
                  onChange={(e) => setConfidenceThreshold(parseFloat(e.target.value))}
                  style={{ width: '100%', cursor: 'pointer' }}
                />
              </div>
            </div>
          )}
        </main>

        {/* Right Sidebar: Real-Time Event Feed Ticker */}
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
    </div>
  );
}
