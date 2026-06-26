import { useEffect, useState, useMemo, useRef } from 'react'
import type { Camera } from '../types'
import { Player } from '../components/Player'
import { ServerCrash, Users, Play, Square, Maximize2, Minimize2, X, Clock3, ChevronDown, Search, AlertCircle } from 'lucide-react'
import { startLive, stopLive } from '../lib/api'
import { usePolicy, resolveLiveStreamId } from '../lib/usePolicy'

type LiveWallProps = {
  statusTextSetter: (txt: string) => void
  selectedCamera?: Camera | null
  onClearSelection?: () => void
  onNavigateToPlayback?: (cam: Camera) => void
  mode?: 'wall' | 'grid'
}

type StreamStatus = {
  stream_id: string
  status: string
  subscribers: number
}

function getGridDimensions(count: number) {
  if (count <= 1) return { cols: 1, rows: 1 };
  if (count <= 2) return { cols: 2, rows: 1 };
  if (count <= 3) return { cols: 3, rows: 1 };
  if (count <= 4) return { cols: 2, rows: 2 };
  if (count <= 6) return { cols: 3, rows: 2 };
  if (count <= 8) return { cols: 4, rows: 2 };
  if (count <= 9) return { cols: 3, rows: 3 };
  if (count <= 12) return { cols: 4, rows: 3 };
  if (count <= 16) return { cols: 4, rows: 4 };
  if (count <= 20) return { cols: 5, rows: 4 };
  if (count <= 24) return { cols: 6, rows: 4 };
  if (count <= 25) return { cols: 5, rows: 5 };
  if (count <= 30) return { cols: 6, rows: 5 };
  if (count <= 36) return { cols: 6, rows: 6 };
  
  const cols = Math.ceil(Math.sqrt(count * 16 / 9));
  const rows = Math.ceil(count / cols);
  return { cols, rows };
}

export function LiveWall({ 
  statusTextSetter, 
  selectedCamera, 
  onClearSelection, 
  onNavigateToPlayback,
  mode = 'wall'
}: LiveWallProps) {
  const [activeCameras, setActiveCameras] = useState<Camera[]>([])
  const [onlineStreamIds, setOnlineStreamIds] = useState<Set<string>>(new Set())
  const [streamStatuses, setStreamStatuses] = useState<Record<string, string>>({})
  const [streamViewers, setStreamViewers] = useState<Record<string, number>>({})
  const [wsConnected, setWsConnected] = useState(false)
  const [isFullView, setIsFullView] = useState(false)
  const [selectedCameraForModal, setSelectedCameraForModal] = useState<Camera | null>(null)

  // Camera selector states
  const [selectedCameraIds, setSelectedCameraIds] = useState<Set<string>>(new Set())
  const [showSelector, setShowSelector] = useState(false)
  const [selectorSearchQuery, setSelectorSearchQuery] = useState('')
  const [warningMessage, setWarningMessage] = useState<string | null>(null)
  const [maximizedCamera, setMaximizedCamera] = useState<Camera | null>(null)

  useEffect(() => {
    if (warningMessage) {
      const timer = setTimeout(() => {
        setWarningMessage(null)
      }, 4000)
      return () => clearTimeout(timer)
    }
  }, [warningMessage])

  const dropdownRef = useRef<HTMLDivElement | null>(null)

  // Pagination states (only relevant for mode === 'wall')
  const [currentPage, setCurrentPage] = useState(1)
  const [pageSize, setPageSize] = useState(12)

  // Handle click outside to close dropdown
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setShowSelector(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [])

  const filteredSelectorCameras = useMemo(() => {
    return activeCameras.filter(c => 
      c.name.toLowerCase().includes(selectorSearchQuery.toLowerCase()) ||
      c.stream_id.toLowerCase().includes(selectorSearchQuery.toLowerCase())
    )
  }, [activeCameras, selectorSearchQuery])

  // Listen to selectedCamera prop from parent to automatically open details modal
  useEffect(() => {
    if (selectedCamera) {
      setSelectedCameraForModal(selectedCamera)
    }
  }, [selectedCamera])

  const handleCloseModal = () => {
    setSelectedCameraForModal(null)
    if (onClearSelection) {
      onClearSelection()
    }
  }

  // Policy-driven stream resolution for live wall
  const { policy } = usePolicy()

  // Use a ref to track connection state inside the polling interval without causing useEffect retriggers
  const wsConnectedRef = useRef(false)

  const [streamDynamicStats, setStreamDynamicStats] = useState<Record<string, { fps?: number; resolution?: string; bitrate?: number }>>({})

  // Poll stats for the selected camera in the modal
  useEffect(() => {
    if (!selectedCameraForModal) return;
    
    // Resolve stream ID inside the effect
    const modalStreamId = resolveLiveStreamId(selectedCameraForModal, policy, 4) || selectedCameraForModal?.streams[0]?.stream_id;
    if (!modalStreamId) return;

    let active = true;
    const fetchStats = async () => {
      try {
        const res = await fetch(`/api/webrtc/streams/${encodeURIComponent(modalStreamId)}/stats`);
        if (res.ok && active) {
          const statsData = await res.json();
          if (statsData && statsData.source === 'realtime') {
            setStreamDynamicStats(prev => ({
              ...prev,
              [modalStreamId]: {
                fps: statsData.avg_fps,
                resolution: statsData.resolution,
                bitrate: statsData.avg_bitrate_kbps
              }
            }));
          }
        }
      } catch (err) {
        console.error('Error fetching dynamic stream stats for modal:', err);
      }
    };

    fetchStats();
    const interval = setInterval(fetchStats, 3000);

    return () => {
      active = false;
      clearInterval(interval);
    };
  }, [selectedCameraForModal, policy]);

  // Fetch all active cameras configured in the platform
  const fetchActiveList = async () => {
    try {
      const res = await fetch('/api/cameras')
      if (res.ok) {
        const allCams = await res.json() as Camera[]
        // Filter active cameras that have streams configured
        const activeCams = allCams.filter(
          c => c.active && c.streams && c.streams.length > 0
        )
        setActiveCameras(activeCams)
        
        // Populate initial statuses and online set from DB values
        const activeIds = new Set<string>()
        const statuses: Record<string, string> = {}
        activeCams.forEach(cam => {
          cam.streams.forEach(s => {
            statuses[s.stream_id] = s.status
            if (s.status === 'ONLINE') {
              activeIds.add(s.stream_id)
            }
          })
        })
        setOnlineStreamIds(activeIds)
        setStreamStatuses(statuses)

        // Restore selected streams from localStorage
        const stored = localStorage.getItem('vms_live_wall_selected_camera_ids')
        if (stored) {
          try {
            const parsed = JSON.parse(stored)
            if (Array.isArray(parsed)) {
              const limited = parsed.slice(0, 12).map(String)
              setSelectedCameraIds(new Set(limited))
              if (parsed.length > 12) {
                localStorage.setItem('vms_live_wall_selected_camera_ids', JSON.stringify(limited))
              }
            }
          } catch (e) {
            console.error('Failed to parse stored camera IDs', e)
          }
        } else {
          // Default to empty selection (do not select all directly)
          setSelectedCameraIds(new Set())
        }
      }
    } catch (e) {
      console.error('[LiveWall] Failed to fetch active list', e)
    }
  }

  // Set up WebSocket status listener
  useEffect(() => {
    fetchActiveList()

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/ws/status`
    let ws: WebSocket | null = null
    let reconnectTimeout: number

    function connect() {
      console.log('[LiveWall] Connecting to status WebSocket...')
      ws = new WebSocket(wsUrl)

      ws.onopen = () => {
        console.log('[LiveWall] Status WebSocket connected')
        wsConnectedRef.current = true
        setWsConnected(true)
      }

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          if (data.streams) {
            const activeIds = new Set<string>()
            const viewers: Record<string, number> = {}
            const statuses: Record<string, string> = {}

            data.streams.forEach((s: StreamStatus) => {
              statuses[s.stream_id] = s.status
              if (s.status === 'ONLINE') {
                activeIds.add(s.stream_id)
              }
              viewers[s.stream_id] = s.subscribers
            })

            setOnlineStreamIds(activeIds)
            setStreamStatuses(statuses)
            setStreamViewers(viewers)
          }
        } catch (err) {
          console.error('[LiveWall] Error parsing socket status payload', err)
        }
      }

      ws.onclose = () => {
        console.log('[LiveWall] Status WebSocket disconnected. Retrying...')
        wsConnectedRef.current = false
        setWsConnected(false)
        reconnectTimeout = window.setTimeout(connect, 3000)
      }

      ws.onerror = (e) => {
        console.error('[LiveWall] Status WebSocket error', e)
        ws?.close()
      }
    }

    connect()

    // Fallback polling loop in case WS fails
    const pollInterval = setInterval(() => {
      if (!wsConnectedRef.current) {
        fetchActiveList()
      }
    }, 10000)

    return () => {
      if (ws) ws.close()
      clearTimeout(reconnectTimeout)
      clearInterval(pollInterval)
    }
  }, [])

  // Filter to show ONLY live recording cameras (check sub-stream status via policy)
  const liveCameras = useMemo(() => {
    return activeCameras.filter(cam => {
      // In grid mode, restrict to selected cameras (include offline ones)
      if (mode === 'grid') {
        return selectedCameraIds.has(String(cam.id))
      }
      // Use policy to resolve which stream to check for status
      const streamId = resolveLiveStreamId(cam, policy, 4) // wall = grid profile
      const anyStream = cam.streams.find(s => s.stream_id === streamId) || cam.streams[0]
      if (!anyStream) return false
      const status = streamStatuses[anyStream.stream_id] || anyStream.status || 'OFFLINE'
      return onlineStreamIds.has(anyStream.stream_id) || status === 'ONLINE'
    })
  }, [activeCameras, onlineStreamIds, streamStatuses, policy, selectedCameraIds, mode])

  const totalPages = useMemo(() => {
    return Math.ceil(liveCameras.length / pageSize)
  }, [liveCameras, pageSize])

  // Reset page to 1 if it exceeds total pages
  useEffect(() => {
    if (currentPage > totalPages && totalPages > 0) {
      setCurrentPage(totalPages)
    }
  }, [totalPages, currentPage])

  const displayedCameras = useMemo(() => {
    if (mode === 'grid') {
      return liveCameras
    }
    const start = (currentPage - 1) * pageSize
    return liveCameras.slice(start, start + pageSize)
  }, [liveCameras, currentPage, pageSize, mode])

  // Start targeted cameras using policy-resolved stream
  const handleStartAll = async () => {
    // In grid mode: start all selected. In wall mode: start current page
    const targets = mode === 'grid' 
      ? activeCameras.filter(c => selectedCameraIds.has(String(c.id)))
      : displayedCameras

    statusTextSetter(`Warming up ${targets.length} cameras...`)
    let success = 0
    for (const cam of targets) {
      const streamId = resolveLiveStreamId(cam, policy, 4)
      if (streamId) {
        try {
          await startLive(streamId)
          setStreamStatuses(prev => ({ ...prev, [streamId]: 'CONNECTING' }))
          success++
        } catch (e) {
          console.error(`Failed to start ${streamId}`, e)
        }
      }
    }
    statusTextSetter(`Warmed up ${success}/${targets.length} cameras`)
  }

  // Stop targeted cameras using policy-resolved stream
  const handleStopAll = async () => {
    // In grid mode: stop all selected. In wall mode: stop current page
    const targets = mode === 'grid'
      ? activeCameras.filter(c => selectedCameraIds.has(String(c.id)))
      : displayedCameras

    statusTextSetter(`Stopping ${targets.length} cameras...`)
    let success = 0
    for (const cam of targets) {
      const streamId = resolveLiveStreamId(cam, policy, 4)
      if (streamId) {
        try {
          await stopLive(streamId)
          setStreamStatuses(prev => ({ ...prev, [streamId]: 'OFFLINE' }))
          success++
        } catch (e) {
          console.error(`Failed to stop ${streamId}`, e)
        }
      }
    }
    statusTextSetter(`Stopped ${success}/${targets.length} cameras`)
  }

  const renderGrid = () => {
    const count = displayedCameras.length;
    const { cols, rows } = getGridDimensions(count);

    const gridStyle = {
      gridTemplateColumns: `repeat(${cols}, 1fr)`,
      gridTemplateRows: `repeat(${rows}, 1fr)`,
      height: '100%',
      minHeight: '0',
      gap: isFullView ? '4px' : '16px',
      padding: isFullView ? '4px' : '0',
      boxSizing: 'border-box' as const
    };

    return (
      <div className="liveWallGrid" style={gridStyle}>
        {displayedCameras.map((cam) => {
          const streamId = resolveLiveStreamId(cam, policy, 4) // wall always uses grid profile
          const anyStream = cam.streams.find(s => s.stream_id === streamId) || cam.streams[0]
          if (!anyStream) return null
          const viewers = streamViewers[anyStream.stream_id] || 0

          const cellStyle = {
            aspectRatio: 'auto',
            height: '100%',
            minHeight: '0',
            width: '100%',
            cursor: 'pointer'
          };

          const isOnline = onlineStreamIds.has(anyStream.stream_id) || 
            (streamStatuses[anyStream.stream_id] || anyStream.status) === 'ONLINE';

          return (
            <div 
              key={cam.id} 
              className="liveWallCell"
              onDoubleClick={() => setSelectedCameraForModal(cam)}
              style={cellStyle}
              title="Double-click to view details"
            >
              {isOnline ? (
                <Player
                  src={`/api/streams/${encodeURIComponent(streamId)}/live/index.m3u8`}
                  posterLabel=""
                  minimal={true}
                />
              ) : (
                <div 
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    justifyContent: 'center',
                    background: '#070a13',
                    width: '100%',
                    height: '100%',
                    gap: '8px',
                    color: '#64748b'
                  }}
                >
                  <ServerCrash size={28} style={{ color: '#475569' }} />
                  <span style={{ fontSize: '0.78rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: '#475569' }}>
                    Offline
                  </span>
                </div>
              )}
              <div className="liveWallCellOverlay">
                <span className="liveWallCellName" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span className="recordingDot" style={{ width: '6px', height: '6px', backgroundColor: isOnline ? undefined : '#475569', boxShadow: isOnline ? undefined : 'none', animation: isOnline ? undefined : 'none' }} />
                  {cam.name}
                </span>
                <div className="liveWallCellStats">
                  <span className="liveWallCellViewer" title="Active viewers" style={{ display: 'flex', alignItems: 'center' }}>
                    <Users size={12} style={{ marginRight: '2px' }} />
                    {viewers}
                  </span>
                  <button
                    type="button"
                    className="liveWallFullscreenBtn"
                    title="Maximize Camera"
                    onClick={(e) => {
                      e.stopPropagation();
                      setMaximizedCamera(cam);
                    }}
                    style={{
                      background: 'none',
                      border: 'none',
                      color: '#94a3b8',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      padding: '2px',
                      pointerEvents: 'auto',
                      marginLeft: '4px'
                    }}
                  >
                    <Maximize2 size={12} />
                  </button>
                  <span className="livePulseDot" style={{ width: '6px', height: '6px', backgroundColor: isOnline ? undefined : '#475569', boxShadow: isOnline ? undefined : 'none', animation: isOnline ? undefined : 'none' }} />
                </div>
              </div>
            </div>
          )
        })}
      </div>
    )
  }

  // Resolve modal parameters
  const modalStreamId = selectedCameraForModal ? resolveLiveStreamId(selectedCameraForModal, policy, 4) : '';
  const modalStream = selectedCameraForModal?.streams.find(s => s.stream_id === modalStreamId) || selectedCameraForModal?.streams[0];
  const modalViewers = selectedCameraForModal && modalStream ? (streamViewers[modalStream.stream_id] || 0) : 0;
  const modalStatus = selectedCameraForModal && modalStream ? (streamStatuses[modalStream.stream_id] || modalStream.status || 'OFFLINE') : 'OFFLINE';
  const dynamicSpecs = streamDynamicStats[modalStreamId] || {};

  return (
    <div className="liveWallContainer">
      <div className="liveWallHeader">
        <div className="liveWallHeaderInfo">
          <div className="livePulseDot" />
          <span className="liveWallHeaderTitle">
            {mode === 'wall' 
              ? `Live Wall — ${liveCameras.length} active camera${liveCameras.length !== 1 ? 's' : ''} online`
              : `Live Grid — ${liveCameras.length} selected camera${liveCameras.length !== 1 ? 's' : ''} online`
            }
          </span>
        </div>
        <div className="liveWallActions" style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          {activeCameras.length > 0 && (
            <>
              {/* Camera Selector Dropdown (only for grid mode) */}
              {mode === 'grid' && (
                <div ref={dropdownRef} className="vmsDropdownContainer" style={{ position: 'relative' }}>
                  <button 
                    className="batchBtn" 
                    onClick={() => setShowSelector(!showSelector)}
                    style={{
                      background: 'rgba(255, 255, 255, 0.05)',
                      color: '#e2e8f0',
                      borderColor: 'rgba(255, 255, 255, 0.1)',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px'
                    }}
                  >
                    Select Cameras ({selectedCameraIds.size}/{activeCameras.length})
                    <ChevronDown size={14} style={{ transform: showSelector ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 0.2s' }} />
                  </button>

                  {showSelector && (
                    <div 
                      className="vmsDropdownMenu" 
                      style={{
                        position: 'absolute',
                        top: '100%',
                        right: 0,
                        marginTop: '8px',
                        width: '320px',
                        maxHeight: '400px',
                        background: '#0f172a',
                        border: '1px solid rgba(255, 255, 255, 0.1)',
                        borderRadius: '12px',
                        boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.3), 0 8px 10px -6px rgba(0, 0, 0, 0.3)',
                        zIndex: 100,
                        display: 'flex',
                        flexDirection: 'column',
                        padding: '12px',
                        gap: '8px'
                      }}
                    >
                      {/* Search input */}
                      <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
                        <Search size={14} style={{ position: 'absolute', left: '10px', color: '#94a3b8' }} />
                        <input
                          type="text"
                          placeholder="Search cameras..."
                          value={selectorSearchQuery}
                          onChange={(e) => setSelectorSearchQuery(e.target.value)}
                          style={{
                            width: '100%',
                            padding: '8px 12px 8px 30px',
                            background: 'rgba(2, 6, 23, 0.4)',
                            border: '1px solid rgba(255, 255, 255, 0.08)',
                            borderRadius: '8px',
                            color: '#fff',
                            fontSize: '0.82rem',
                            outline: 'none'
                          }}
                        />
                      </div>

                      {/* Bulk Actions */}
                      <div style={{ display: 'flex', gap: '8px', borderBottom: '1px solid rgba(255, 255, 255, 0.05)', paddingBottom: '8px' }}>
                        <button
                          type="button"
                          onClick={() => {
                            const first12 = activeCameras.slice(0, 12).map(c => String(c.id));
                            setSelectedCameraIds(new Set(first12));
                            localStorage.setItem('vms_live_wall_selected_camera_ids', JSON.stringify(first12));
                          }}
                          style={{
                            flex: 1,
                            background: 'rgba(255, 255, 255, 0.04)',
                            border: 'none',
                            borderRadius: '6px',
                            color: '#cbd5e1',
                            padding: '6px',
                            fontSize: '0.75rem',
                            cursor: 'pointer',
                            fontWeight: 600
                          }}
                        >
                          Select First 12
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setSelectedCameraIds(new Set());
                            localStorage.removeItem('vms_live_wall_selected_camera_ids');
                          }}
                          style={{
                            flex: 1,
                            background: 'rgba(255, 255, 255, 0.04)',
                            border: 'none',
                            borderRadius: '6px',
                            color: '#cbd5e1',
                            padding: '6px',
                            fontSize: '0.75rem',
                            cursor: 'pointer',
                            fontWeight: 600
                          }}
                        >
                          Clear All
                        </button>
                      </div>

                      {/* Camera List */}
                      <div style={{ overflowY: 'auto', flex: 1, display: 'flex', flexDirection: 'column', gap: '4px', paddingRight: '4px', maxHeight: '250px' }}>
                        {filteredSelectorCameras.map(cam => {
                          const isChecked = selectedCameraIds.has(String(cam.id));
                          return (
                            <div
                              key={cam.id}
                              onClick={() => {
                                const newSelection = new Set(selectedCameraIds);
                                const idStr = String(cam.id);
                                if (newSelection.has(idStr)) {
                                  newSelection.delete(idStr);
                                } else {
                                  if (newSelection.size >= 12) {
                                    setWarningMessage("Grid limit reached: Maximum 12 cameras allowed");
                                    return;
                                  }
                                  newSelection.add(idStr);
                                }
                                setSelectedCameraIds(newSelection);
                                localStorage.setItem('vms_live_wall_selected_camera_ids', JSON.stringify(Array.from(newSelection)));
                              }}
                              style={{
                                display: 'flex',
                                  alignItems: 'center',
                                  gap: '10px',
                                  padding: '8px 10px',
                                  borderRadius: '8px',
                                  background: isChecked ? 'rgba(59, 130, 246, 0.1)' : 'transparent',
                                  cursor: 'pointer',
                                  transition: 'background 0.2s',
                                  border: '1px solid transparent'
                              }}
                              className="vmsSelectorItem"
                            >
                              <input
                                type="checkbox"
                                checked={isChecked}
                                onChange={() => {}} // Handled by outer click
                                style={{ cursor: 'pointer' }}
                              />
                              <div style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
                                <span style={{ fontSize: '0.82rem', fontWeight: 600, color: isChecked ? '#60a5fa' : '#f1f5f9', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                  {cam.name}
                                </span>
                                <span style={{ fontSize: '0.68rem', color: '#94a3b8', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                  {cam.stream_id}
                                </span>
                              </div>
                            </div>
                          );
                        })}
                        {filteredSelectorCameras.length === 0 && (
                          <div style={{ padding: '20px 0', textAlign: 'center', fontSize: '0.8rem', color: '#64748b' }}>
                            No matching cameras
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )}

              <button className="batchBtn start" onClick={handleStartAll}>
                <Play size={14} /> {mode === 'wall' ? 'Start Page' : 'Start Grid'}
              </button>
              <button className="batchBtn stop" onClick={handleStopAll}>
                <Square size={14} /> {mode === 'wall' ? 'Stop Page' : 'Stop Grid'}
              </button>
              <button 
                className="batchBtn" 
                onClick={() => setIsFullView(true)}
                style={{
                  background: 'rgba(59, 130, 246, 0.15)',
                  color: '#60a5fa',
                  borderColor: 'rgba(59, 130, 246, 0.3)'
                }}
              >
                <Maximize2 size={14} /> Full Wall
              </button>
            </>
          )}
        </div>
      </div>

      {liveCameras.length > 0 ? (
        <>
          {renderGrid()}
          
          {/* Pagination Controls */}
          {mode === 'wall' && totalPages > 1 && (
            <div 
              className="liveWallPagination" 
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '12px 18px',
                background: 'rgba(30, 41, 59, 0.25)',
                border: '1px solid rgba(255, 255, 255, 0.05)',
                borderRadius: '12px',
                marginTop: '16px'
              }}
            >
              <div style={{ fontSize: '0.8rem', color: '#94a3b8' }}>
                Showing <strong>{Math.min((currentPage - 1) * pageSize + 1, liveCameras.length)}</strong>–
                <strong>{Math.min(currentPage * pageSize, liveCameras.length)}</strong> of <strong>{liveCameras.length}</strong> online cameras
              </div>
              
              <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                {/* Page Size Selector */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ fontSize: '0.78rem', color: '#64748b' }}>Per Page:</span>
                  <select
                    value={pageSize}
                    onChange={(e) => {
                      setPageSize(parseInt(e.target.value, 10))
                      setCurrentPage(1)
                    }}
                    style={{
                      background: 'rgba(15, 23, 42, 0.6)',
                      border: '1px solid rgba(255, 255, 255, 0.1)',
                      borderRadius: '6px',
                      color: '#fff',
                      padding: '4px 8px',
                      fontSize: '0.78rem',
                      outline: 'none',
                      cursor: 'pointer'
                    }}
                  >
                    {[4, 8, 12, 16, 24, 32].map(size => (
                      <option key={size} value={size}>{size}</option>
                    ))}
                  </select>
                </div>

                {/* Nav buttons */}
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button
                    onClick={() => setCurrentPage(prev => Math.max(prev - 1, 1))}
                    disabled={currentPage === 1}
                    style={{
                      background: currentPage === 1 ? 'rgba(255,255,255,0.02)' : 'rgba(255,255,255,0.06)',
                      color: currentPage === 1 ? '#475569' : '#cbd5e1',
                      border: '1px solid rgba(255, 255, 255, 0.05)',
                      borderRadius: '6px',
                      padding: '6px 12px',
                      fontSize: '0.78rem',
                      cursor: currentPage === 1 ? 'not-allowed' : 'pointer',
                      fontWeight: 600
                    }}
                  >
                    Previous
                  </button>
                  <span style={{ fontSize: '0.78rem', color: '#cbd5e1', alignSelf: 'center', minWidth: '80px', textAlign: 'center' }}>
                    Page {currentPage} of {totalPages}
                  </span>
                  <button
                    onClick={() => setCurrentPage(prev => Math.min(prev + 1, totalPages))}
                    disabled={currentPage === totalPages}
                    style={{
                      background: currentPage === totalPages ? 'rgba(255,255,255,0.02)' : 'rgba(255,255,255,0.06)',
                      color: currentPage === totalPages ? '#475569' : '#cbd5e1',
                      border: '1px solid rgba(255, 255, 255, 0.05)',
                      borderRadius: '6px',
                      padding: '6px 12px',
                      fontSize: '0.78rem',
                      cursor: currentPage === totalPages ? 'not-allowed' : 'pointer',
                      fontWeight: 600
                    }}
                  >
                    Next
                  </button>
                </div>
              </div>
            </div>
          )}
        </>
      ) : (
        <div className="liveWallEmpty">
          <ServerCrash className="liveWallEmptyIcon" />
          <div className="liveWallEmptyTitle">
            {mode === 'grid' ? 'No cameras selected' : 'No live recording cameras found'}
          </div>
          <div className="liveWallEmptySub">
            {mode === 'grid' 
              ? 'Open the "Select Cameras" dropdown in the header to select and add camera feeds to your grid.' 
              : 'All cameras are currently offline. Use "Start Page" or start individual cameras from the Dashboard tab.'}
          </div>
        </div>
      )}

      {isFullView && liveCameras.length > 0 && (
        <div className="fullscreenVideoWall">
          <div style={{ width: '100%', height: '100%', padding: '12px', boxSizing: 'border-box' }}>
            {renderGrid()}
          </div>
          
          {/* Pagination Controls inside Fullscreen View */}
          {mode === 'wall' && totalPages > 1 && (
            <div 
              className="liveWallPagination"
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '12px 18px',
                background: 'rgba(30, 41, 59, 0.85)',
                border: '1px solid rgba(255, 255, 255, 0.08)',
                borderRadius: '12px',
                boxShadow: '0 8px 32px rgba(0, 0, 0, 0.5)'
              }}
            >
              <div style={{ fontSize: '0.8rem', color: '#94a3b8' }}>
                Showing <strong>{Math.min((currentPage - 1) * pageSize + 1, liveCameras.length)}</strong>–
                <strong>{Math.min(currentPage * pageSize, liveCameras.length)}</strong> of <strong>{liveCameras.length}</strong> online cameras
              </div>
              
              <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ fontSize: '0.78rem', color: '#64748b' }}>Per Page:</span>
                  <select
                    value={pageSize}
                    onChange={(e) => {
                      setPageSize(parseInt(e.target.value, 10))
                      setCurrentPage(1)
                    }}
                    style={{
                      background: 'rgba(15, 23, 42, 0.6)',
                      border: '1px solid rgba(255, 255, 255, 0.1)',
                      borderRadius: '6px',
                      color: '#fff',
                      padding: '4px 8px',
                      fontSize: '0.78rem',
                      outline: 'none',
                      cursor: 'pointer'
                    }}
                  >
                    {[4, 8, 12, 16, 24, 32].map(size => (
                      <option key={size} value={size}>{size}</option>
                    ))}
                  </select>
                </div>

                <div style={{ display: 'flex', gap: '8px' }}>
                  <button
                    onClick={() => setCurrentPage(prev => Math.max(prev - 1, 1))}
                    disabled={currentPage === 1}
                    style={{
                      background: currentPage === 1 ? 'rgba(255,255,255,0.02)' : 'rgba(255,255,255,0.06)',
                      color: currentPage === 1 ? '#475569' : '#cbd5e1',
                      border: '1px solid rgba(255, 255, 255, 0.05)',
                      borderRadius: '6px',
                      padding: '6px 12px',
                      fontSize: '0.78rem',
                      cursor: currentPage === 1 ? 'not-allowed' : 'pointer',
                      fontWeight: 600
                    }}
                  >
                    Previous
                  </button>
                  <span style={{ fontSize: '0.78rem', color: '#cbd5e1', alignSelf: 'center', minWidth: '80px', textAlign: 'center' }}>
                    Page {currentPage} of {totalPages}
                  </span>
                  <button
                    onClick={() => setCurrentPage(prev => Math.min(prev + 1, totalPages))}
                    disabled={currentPage === totalPages}
                    style={{
                      background: currentPage === totalPages ? 'rgba(255,255,255,0.02)' : 'rgba(255,255,255,0.06)',
                      color: currentPage === totalPages ? '#475569' : '#cbd5e1',
                      border: '1px solid rgba(255, 255, 255, 0.05)',
                      borderRadius: '6px',
                      padding: '6px 12px',
                      fontSize: '0.78rem',
                      cursor: currentPage === totalPages ? 'not-allowed' : 'pointer',
                      fontWeight: 600
                    }}
                  >
                    Next
                  </button>
                </div>
              </div>
            </div>
          )}

          <button
            className="exitFullViewBtn"
            type="button"
            onClick={() => setIsFullView(false)}
            title="Exit Full Wall"
          >
            <Minimize2 size={18} /> Exit Full Wall
          </button>
        </div>
      )}

      {selectedCameraForModal && modalStream && (
        <div className="vmsModalBackdrop" onClick={handleCloseModal}>
          <div className="vmsModalContent" onClick={(e) => e.stopPropagation()}>
            <button className="vmsModalCloseBtn" onClick={handleCloseModal} title="Close Details">
              <X size={20} />
            </button>
            <div className="vmsModalBody">
              <div className="vmsModalVideoCol">
                <Player
                  src={`/api/streams/${encodeURIComponent(modalStreamId)}/live/index.m3u8`}
                  posterLabel={`${selectedCameraForModal.name}`}
                  minimal={false}
                />
              </div>
              <div className="vmsModalInfoCol">
                <h3 className="vmsModalTitle">{selectedCameraForModal.name}</h3>
                <span className="vmsModalSubtitle">Camera details & stream metadata</span>
                
                <div className="vmsModalSpecs">
                  <div className="vmsSpecItem">
                    <span className="vmsSpecLabel">Stream ID</span>
                    <span className="vmsSpecValue monospace">{modalStreamId}</span>
                  </div>
                  <div className="vmsSpecItem">
                    <span className="vmsSpecLabel">Status</span>
                    <span className={`vmsSpecValue badge ${modalStatus === 'ONLINE' ? 'online' : 'offline'}`}>
                      {modalStatus}
                    </span>
                  </div>
                  <div className="vmsSpecItem">
                    <span className="vmsSpecLabel">Resolution</span>
                    <span className="vmsSpecValue">{dynamicSpecs.resolution || modalStream.resolution || '1920x1080'}</span>
                  </div>
                  <div className="vmsSpecItem">
                    <span className="vmsSpecLabel">Codec</span>
                    <span className="vmsSpecValue">{modalStream.codec || 'H264'}</span>
                  </div>
                  <div className="vmsSpecItem">
                    <span className="vmsSpecLabel">FPS</span>
                    <span className="vmsSpecValue">
                      {dynamicSpecs.fps !== undefined ? `${Math.round(dynamicSpecs.fps)} (Live)` : (modalStream.fps || '15')}
                    </span>
                  </div>
                  <div className="vmsSpecItem">
                    <span className="vmsSpecLabel">Bitrate</span>
                    <span className="vmsSpecValue">
                      {dynamicSpecs.bitrate !== undefined ? `${Math.round(dynamicSpecs.bitrate)} kbps (Live)` : (modalStream.bitrate ? `${modalStream.bitrate} kbps` : 'Variable')}
                    </span>
                  </div>
                  <div className="vmsSpecItem">
                    <span className="vmsSpecLabel">Active Viewers</span>
                    <span className="vmsSpecValue">{modalViewers}</span>
                  </div>
                  <div className="vmsSpecItem fullWidth">
                    <span className="vmsSpecLabel">Source RTSP URL</span>
                    <span className="vmsSpecValue monospace breakAll" title={modalStream.stream_url}>
                      {modalStream.stream_url}
                    </span>
                  </div>
                </div>

                <button
                  type="button"
                  className="batchBtn"
                  style={{
                    marginTop: '20px',
                    width: '100%',
                    background: 'linear-gradient(135deg, #6366f1, #4f46e5)',
                    color: '#fff',
                    border: 'none',
                    padding: '10px 16px',
                    borderRadius: '8px',
                    fontWeight: 600,
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '8px'
                  }}
                  onClick={() => {
                    if (onNavigateToPlayback) {
                      onNavigateToPlayback(selectedCameraForModal)
                    }
                    handleCloseModal()
                  }}
                >
                  <Clock3 size={16} /> Go to Playback
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
      {maximizedCamera && (
        <div 
          className="maximizedCameraContainer"
          style={{
            position: 'fixed',
            inset: 0,
            background: '#020617',
            zIndex: 11000,
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'center',
            alignItems: 'center'
          }}
        >
          <div style={{ width: '100%', height: '100%', position: 'relative' }}>
            <Player
              src={`/api/streams/${encodeURIComponent(resolveLiveStreamId(maximizedCamera, policy, 4))}/live/index.m3u8`}
              posterLabel=""
              minimal={false}
            />
            
            {/* Top Bar Overlay */}
            <div 
              style={{
                position: 'absolute',
                top: '20px',
                left: '20px',
                display: 'flex',
                alignItems: 'center',
                gap: '12px',
                zIndex: 100,
                background: 'rgba(15, 23, 42, 0.85)',
                backdropFilter: 'blur(10px)',
                padding: '8px 16px',
                borderRadius: '12px',
                border: '1px solid rgba(255, 255, 255, 0.08)',
                boxShadow: '0 8px 32px rgba(0, 0, 0, 0.5)'
              }}
            >
              <button
                type="button"
                onClick={() => setMaximizedCamera(null)}
                style={{
                  background: '#2563eb',
                  border: 'none',
                  color: '#fff',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '8px 16px',
                  borderRadius: '8px',
                  fontSize: '0.85rem',
                  fontWeight: 700,
                  boxShadow: '0 2px 8px rgba(37, 99, 235, 0.4)',
                  transition: 'background 0.2s'
                }}
                className="vmsBackToGridBtn"
              >
                ← Back to Grid
              </button>
              <span style={{ color: '#f8fafc', fontWeight: 600, fontSize: '0.92rem' }}>
                {maximizedCamera.name}
              </span>
            </div>
          </div>
        </div>
      )}
      {warningMessage && (
        <div className="vmsToast">
          <AlertCircle size={16} />
          <span>{warningMessage}</span>
        </div>
      )}
    </div>
  )
}
