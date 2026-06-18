import { useEffect, useState, useMemo } from 'react'
import type { Camera } from '../types'
import { Player } from '../components/Player'
import { ServerCrash, Users, Play, Square, Maximize2, Minimize2, VideoOff, AlertCircle, Loader2 } from 'lucide-react'
import { startLive, stopLive } from '../lib/api'

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
      if (!wsConnected) {
        fetchActiveList()
      }
    }, 10000)

    return () => {
      if (ws) ws.close()
      clearTimeout(reconnectTimeout)
      clearInterval(pollInterval)
    }
  }, [wsConnected])

  // Get optimal grid columns count for high-density wall
  const gridCols = useMemo(() => {
    const count = activeCameras.length
    if (count <= 1) return 1
    if (count <= 4) return 2
    if (count <= 9) return 3
    if (count <= 16) return 4
    if (count <= 25) return 5
    if (count <= 36) return 6
    if (count <= 49) return 7
    return 8 // 50+ cameras -> 8 columns
  }, [activeCameras.length])

  // Start all cameras
  const handleStartAll = async () => {
    statusTextSetter('Warming up all online cameras...')
    let success = 0
    for (const cam of activeCameras) {
      const activeStream = cam.streams[0]
      if (activeStream) {
        try {
          await startLive(activeStream.stream_id)
          // Optimistically update local status to CONNECTING
          setStreamStatuses(prev => ({ ...prev, [activeStream.stream_id]: 'CONNECTING' }))
          success++
        } catch (e) {
          console.error(`Failed to start ${activeStream.stream_id}`, e)
        }
      }
    }
    statusTextSetter(`Warmed up ${success}/${activeCameras.length} online cameras`)
  }

  // Stop all cameras
  const handleStopAll = async () => {
    statusTextSetter('Stopping all online cameras...')
    let success = 0
    for (const cam of activeCameras) {
      const activeStream = cam.streams[0]
      if (activeStream) {
        try {
          await stopLive(activeStream.stream_id)
          setStreamStatuses(prev => ({ ...prev, [activeStream.stream_id]: 'OFFLINE' }))
          success++
        } catch (e) {
          console.error(`Failed to stop ${activeStream.stream_id}`, e)
        }
      }
    }
    statusTextSetter(`Stopped ${success}/${activeCameras.length} online cameras`)
  }

  const renderGrid = () => (
    <div className={`liveWallGrid grid-${gridCols}`}>
      {activeCameras.map((cam) => {
        const activeStream = cam.streams[0]
        if (!activeStream) return null

        const status = streamStatuses[activeStream.stream_id] || activeStream.status || 'OFFLINE'
        const viewers = streamViewers[activeStream.stream_id] || 0
        const isOnline = onlineStreamIds.has(activeStream.stream_id) || status === 'ONLINE'

        if (!isOnline) {
          const isConnecting = status === 'CONNECTING'
          const isFailed = status === 'FAILED'

          return (
            <div key={cam.id} className="liveWallCell" style={{ padding: 0, overflow: 'hidden' }}>
              <div className={`liveWallOfflineCard ${isConnecting ? 'connecting' : isFailed ? 'failed' : 'offline'}`}>
                {isConnecting ? (
                  <Loader2 className="offlineCardIcon" size={24} />
                ) : isFailed ? (
                  <AlertCircle className="offlineCardIcon" size={24} />
                ) : (
                  <VideoOff className="offlineCardIcon" size={24} />
                )}
                
                <div className="offlineCardStatus">
                  {isConnecting ? 'Connecting' : isFailed ? 'Failed' : 'Offline'}
                </div>
                
                <div className="offlineCardName">{cam.name}</div>
                
                {!isConnecting && (
                  <button 
                    className="offlineCardActionBtn" 
                    type="button"
                    onClick={async (e) => {
                      e.stopPropagation()
                      try {
                        statusTextSetter(`Starting stream for ${cam.name}...`)
                        await startLive(activeStream.stream_id)
                        setStreamStatuses(prev => ({ ...prev, [activeStream.stream_id]: 'CONNECTING' }))
                      } catch (err) {
                        statusTextSetter(`Failed to start ${cam.name}: ${err}`)
                      }
                    }}
                  >
                    Start
                  </button>
                )}
              </div>
            </div>
          )
        }

        return (
          <div key={cam.id} className="liveWallCell">
            <Player
              src={`/api/streams/${encodeURIComponent(activeStream.stream_id)}/live/index.m3u8`}
              posterLabel={cam.name}
              minimal={true}
            />
            <div className="liveWallCellOverlay">
              <span className="liveWallCellName" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span className="recordingDot" style={{ width: '6px', height: '6px' }} />
                {cam.name}
              </span>
              <div className="liveWallCellStats">
                <span className="liveWallCellViewer" title="Active viewers">
                  <Users size={12} style={{ marginRight: '2px' }} />
                  {viewers}
                </span>
                <span className="livePulseDot" style={{ width: '6px', height: '6px' }} />
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )

  return (
    <div className="liveWallContainer">
      <div className="liveWallHeader">
        <div className="liveWallHeaderInfo">
          <div className="livePulseDot" />
          <span className="liveWallHeaderTitle">
            Live Wall — {activeCameras.length} active camera{activeCameras.length !== 1 ? 's' : ''} online
          </span>
        </div>
        <div className="liveWallActions">
          {activeCameras.length > 0 && (
            <>
              <button className="batchBtn start" onClick={handleStartAll}>
                <Play size={14} /> Start All Live
              </button>
              <button className="batchBtn stop" onClick={handleStopAll}>
                <Square size={14} /> Stop All Live
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

      {activeCameras.length > 0 ? (
        renderGrid()
      ) : (
        <div className="liveWallEmpty">
          <ServerCrash className="liveWallEmptyIcon" />
          <div className="liveWallEmptyTitle">No live cameras found</div>
          <div className="liveWallEmptySub">
            All cameras are currently offline. Cameras will dynamically appear here as soon as they connect and start streaming.
          </div>
        </div>
      )}

      {isFullView && activeCameras.length > 0 && (
        <div className="fullscreenVideoWall">
          <div style={{ width: '100%', height: '100%', padding: '24px', boxSizing: 'border-box' }}>
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
    </div>
  )
}
