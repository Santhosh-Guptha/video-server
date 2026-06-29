import { useEffect, useState, useMemo, useRef } from 'react'
import type { Camera } from '../types'
import { Player } from '../components/Player'
import { ServerCrash, Users, Play, Square, Maximize2, Minimize2, X } from 'lucide-react'
import { startLive, stopLive } from '../lib/api'
import { usePolicy, resolveLiveStreamId } from '../lib/usePolicy'

type LiveWallProps = {
  statusTextSetter: (txt: string) => void
}

type StreamStatus = {
  stream_id: string
  status: string
  subscribers: number
}

export function LiveWall({ statusTextSetter }: LiveWallProps) {
  const [activeCameras, setActiveCameras] = useState<Camera[]>([])
  const [onlineStreamIds, setOnlineStreamIds] = useState<Set<string>>(new Set())
  const [streamStatuses, setStreamStatuses] = useState<Record<string, string>>({})
  const [streamViewers, setStreamViewers] = useState<Record<string, number>>({})
  const [wsConnected, setWsConnected] = useState(false)
  const [isFullView, setIsFullView] = useState(false)
  const [selectedCameraForModal, setSelectedCameraForModal] = useState<Camera | null>(null)
  const [gridSize, setGridSize] = useState<number>(12) // default 12 (4x3 layout)
  const [currentPage, setCurrentPage] = useState<number>(1)

  // Policy-driven stream resolution for live wall
  const { policy } = usePolicy()

  // Use a ref to track connection state inside the polling interval without causing useEffect retriggers
  const wsConnectedRef = useRef(false)

  // Fetch all active cameras configured in the platform
  const fetchActiveList = async () => {
    try {
      const res = await fetch('/api/cameras')
      if (res.ok) {
        const allCams = await res.json() as Camera[]
        // Filter standard cameras that are active
        const activeCams = allCams.filter(
          c => c.active && c.streams && c.streams.length > 0 && c.streams[0].stream_url.startsWith("rtsp://")
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
      // Use policy to resolve which stream to check for status
      const streamId = resolveLiveStreamId(cam, policy, 4) // wall = grid profile
      const anyStream = cam.streams.find(s => s.stream_id === streamId) || cam.streams[0]
      if (!anyStream) return false
      const status = streamStatuses[anyStream.stream_id] || anyStream.status || 'OFFLINE'
      return onlineStreamIds.has(anyStream.stream_id) || status === 'ONLINE'
    })
  }, [activeCameras, onlineStreamIds, streamStatuses, policy])

  const totalPages = Math.ceil(liveCameras.length / gridSize)

  // Clamp current page to maximum page count
  useEffect(() => {
    if (currentPage > totalPages && totalPages > 0) {
      setCurrentPage(totalPages)
    }
  }, [totalPages, currentPage])

  const paginatedCameras = useMemo(() => {
    const start = (currentPage - 1) * gridSize
    return liveCameras.slice(start, start + gridSize)
  }, [liveCameras, currentPage, gridSize])

  // Start all cameras using policy-resolved stream
  const handleStartAll = async () => {
    statusTextSetter('Warming up all online cameras...')
    let success = 0
    for (const cam of activeCameras) {
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
    statusTextSetter(`Warmed up ${success}/${activeCameras.length} online cameras`)
  }

  // Stop all cameras using policy-resolved stream
  const handleStopAll = async () => {
    statusTextSetter('Stopping all online cameras...')
    let success = 0
    for (const cam of activeCameras) {
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
    statusTextSetter(`Stopped ${success}/${activeCameras.length} online cameras`)
  }

  const renderGrid = () => {
    let cols = 4;
    if (gridSize === 4) cols = 2;
    else if (gridSize === 9) cols = 3;
    else if (gridSize === 12) cols = 4;
    else if (gridSize === 16) cols = 4;
    else if (gridSize === 24) cols = 6;
    else if (gridSize === 36) cols = 6;

    return (
      <div 
        className="liveWallGrid"
        style={{
          display: 'grid',
          gridTemplateColumns: `repeat(${cols}, 1fr)`,
          gap: '12px',
          width: '100%',
          flex: 1
        }}
      >
        {paginatedCameras.map((cam) => {
          const streamId = resolveLiveStreamId(cam, policy, 4) // wall always uses grid profile
          const anyStream = cam.streams.find(s => s.stream_id === streamId) || cam.streams[0]
          if (!anyStream) return null
          const viewers = streamViewers[anyStream.stream_id] || 0

          return (
            <div 
              key={cam.id} 
              className="liveWallCell"
              onDoubleClick={() => setSelectedCameraForModal(cam)}
              style={{ cursor: 'pointer', position: 'relative', width: '100%', aspectRatio: '16/9' }}
              title="Double-click to view details"
            >
              <Player
                src={`/api/streams/${encodeURIComponent(streamId)}/live/index.m3u8`}
                posterLabel=""
                minimal={true}
              />
              <div className="liveWallCellOverlay">
                <span className="liveWallCellName" style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px' }}>
                  <span className="recordingDot" style={{ width: '6px', height: '6px' }} />
                  {cam.name}
                </span>
                <div className="liveWallCellStats">
                  <span className="liveWallCellViewer" title="Active viewers" style={{ display: 'flex', alignItems: 'center', fontSize: '10px' }}>
                    <Users size={10} style={{ marginRight: '2px' }} />
                    {viewers}
                  </span>
                  <button
                    type="button"
                    className="liveWallFullscreenBtn"
                    title="Fullscreen"
                    onClick={(e) => {
                      e.stopPropagation();
                      const cellEl = e.currentTarget.closest('.liveWallCell');
                      const videoEl = cellEl?.querySelector('video');
                      if (videoEl) {
                        videoEl.requestFullscreen?.();
                      }
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
                    <Maximize2 size={10} />
                  </button>
                  <span className="livePulseDot" style={{ width: '6px', height: '6px' }} />
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

  return (
    <div className="liveWallContainer">
      <div className="liveWallHeader">
        <div className="liveWallHeaderInfo">
          <div className="livePulseDot" />
          <span className="liveWallHeaderTitle">
            Live Wall — {liveCameras.length} active camera{liveCameras.length !== 1 ? 's' : ''} online
          </span>
        </div>
        <div className="liveWallActions" style={{ display: 'flex', alignItems: 'center', gap: '14px', flexWrap: 'wrap' }}>
          {/* Grid Layout Selector */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ fontSize: '11px', color: '#94a3b8', fontWeight: 600 }}>Grid size:</span>
            <select
              value={gridSize}
              onChange={(e) => {
                setGridSize(Number(e.target.value))
                setCurrentPage(1)
              }}
              style={{
                background: '#0b0f19',
                border: '1px solid rgba(255, 255, 255, 0.1)',
                color: '#f8fafc',
                borderRadius: '6px',
                padding: '4px 24px 4px 8px',
                fontSize: '11px',
                cursor: 'pointer',
                outline: 'none'
              }}
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
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <button
                className="batchBtn"
                onClick={() => setCurrentPage(p => Math.max(p - 1, 1))}
                disabled={currentPage === 1}
                style={{ padding: '4px 8px', fontSize: '11px', opacity: currentPage === 1 ? 0.4 : 1, cursor: currentPage === 1 ? 'default' : 'pointer' }}
              >
                Prev
              </button>
              <span style={{ fontSize: '11px', color: '#cbd5e1', minWidth: '70px', textAlign: 'center' }}>
                {currentPage} / {totalPages}
              </span>
              <button
                className="batchBtn"
                onClick={() => setCurrentPage(p => Math.min(p + 1, totalPages))}
                disabled={currentPage === totalPages}
                style={{ padding: '4px 8px', fontSize: '11px', opacity: currentPage === totalPages ? 0.4 : 1, cursor: currentPage === totalPages ? 'default' : 'pointer' }}
              >
                Next
              </button>
            </div>
          )}

          {activeCameras.length > 0 && (
            <>
              <button className="batchBtn start" onClick={handleStartAll} style={{ padding: '4px 10px', fontSize: '11px' }}>
                <Play size={12} /> Start All
              </button>
              <button className="batchBtn stop" onClick={handleStopAll} style={{ padding: '4px 10px', fontSize: '11px' }}>
                <Square size={12} /> Stop All
              </button>
              <button 
                className="batchBtn" 
                onClick={() => setIsFullView(true)}
                style={{
                  background: 'rgba(59, 130, 246, 0.15)',
                  color: '#60a5fa',
                  borderColor: 'rgba(59, 130, 246, 0.3)',
                  padding: '4px 10px',
                  fontSize: '11px'
                }}
              >
                <Maximize2 size={12} /> Full Wall
              </button>
            </>
          )}
        </div>
      </div>

      {liveCameras.length > 0 ? (
        renderGrid()
      ) : (
        <div className="liveWallEmpty">
          <ServerCrash className="liveWallEmptyIcon" />
          <div className="liveWallEmptyTitle">No live recording cameras found</div>
          <div className="liveWallEmptySub">
            All cameras are currently offline. Use "Start All" or start individual cameras from the Live View tab.
          </div>
        </div>
      )}

      {isFullView && liveCameras.length > 0 && (
        <div className="fullscreenVideoWall">
          <div style={{ width: '100%', height: '100%', padding: '12px', boxSizing: 'border-box' }}>
            {renderGrid()}
          </div>
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
        <div className="vmsModalBackdrop" onClick={() => setSelectedCameraForModal(null)}>
          <div className="vmsModalContent" onClick={(e) => e.stopPropagation()}>
            <button className="vmsModalCloseBtn" onClick={() => setSelectedCameraForModal(null)} title="Close Details">
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
                    <span className="vmsSpecValue">{modalStream.resolution || '1920x1080'}</span>
                  </div>
                  <div className="vmsSpecItem">
                    <span className="vmsSpecLabel">Codec</span>
                    <span className="vmsSpecValue">{modalStream.codec || 'H264'}</span>
                  </div>
                  <div className="vmsSpecItem">
                    <span className="vmsSpecLabel">FPS</span>
                    <span className="vmsSpecValue">{modalStream.fps || '15'}</span>
                  </div>
                  <div className="vmsSpecItem">
                    <span className="vmsSpecLabel">Bitrate</span>
                    <span className="vmsSpecValue">{modalStream.bitrate ? `${modalStream.bitrate} kbps` : 'Variable'}</span>
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
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
