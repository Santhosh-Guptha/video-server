import { useEffect, useMemo, useState } from 'react'
import type { Camera, RecordingSegment } from './types'
import { Sidebar } from './components/Sidebar'
import { Dashboard } from './pages/Dashboard'
import { Playback } from './pages/Playback'
import { EdgePushPage } from './pages/EdgePush'
import { LiveWall } from './pages/LiveWall'
import { CameraManagement } from './pages/CameraManagement'
import { WebcamStream } from './pages/WebcamStream'
import { GapRecovery } from './pages/GapRecovery'
import TranscoderMonitor from './pages/TranscoderMonitor'
import { fetchCameras, fetchRecordings, syncCameras } from './lib/api'
import { usePolicy, resolvePlaybackStreamId } from './lib/usePolicy'
import { Activity, RefreshCcw } from 'lucide-react'

export default function App() {
  const [cameras, setCameras] = useState<Camera[]>([])
  const [selected, setSelected] = useState<Camera | undefined>()

  // Fetch active VMS policy from backend — ALL stream routing decisions use this
  const { policy } = usePolicy()

  const isEdgeCamera = (cam: Camera) => !cam.rtsp_url || cam.rtsp_url.trim() === "" || !cam.rtsp_url.trim().toLowerCase().startsWith("rtsp://");

  const standardCameras = useMemo(() => {
    return cameras.filter(cam => !isEdgeCamera(cam))
  }, [cameras])

  const edgeCameras = useMemo(() => {
    return cameras.filter(cam => isEdgeCamera(cam))
  }, [cameras])

  const [activeTab, setActiveTabState] = useState<'dashboard' | 'live' | 'live_wall' | 'playback' | 'edgepush' | 'camera_config' | 'webcam_stream' | 'gap_recovery' | 'transcoder_monitor'>(() => {
    const path = window.location.pathname.replace(/^\//, '')
    const validTabs = ['dashboard', 'live', 'live_wall', 'playback', 'edgepush', 'camera_config', 'webcam_stream', 'gap_recovery', 'transcoder_monitor']
    return validTabs.includes(path) ? (path as any) : 'dashboard'
  })

  const setActiveTab = (tab: string) => {
    setActiveTabState(tab as any)
    window.history.pushState(null, '', `/${tab}`)
  }

  const [query, setQuery] = useState('')
  const [recordings, setRecordings] = useState<RecordingSegment[]>([])
  const [statusText, setStatusText] = useState('Ready')
  const [loading, setLoading] = useState(false)
  const [lastSync, setLastSync] = useState('Never')

  // Caching states to localStorage for page-refresh persistence
  useEffect(() => {
    const handlePopState = () => {
      const path = window.location.pathname.replace(/^\//, '')
      const validTabs = ['dashboard', 'live', 'live_wall', 'playback', 'edgepush', 'camera_config', 'webcam_stream', 'gap_recovery', 'transcoder_monitor']
      setActiveTabState(validTabs.includes(path) ? (path as any) : 'dashboard')
    }
    window.addEventListener('popstate', handlePopState)
    
    // Normalize path to /dashboard if empty or invalid
    const path = window.location.pathname.replace(/^\//, '')
    const validTabs = ['dashboard', 'live', 'live_wall', 'playback', 'edgepush', 'camera_config', 'webcam_stream', 'gap_recovery', 'transcoder_monitor']
    if (!validTabs.includes(path)) {
      window.history.replaceState(null, '', '/dashboard')
    }
    return () => window.removeEventListener('popstate', handlePopState)
  }, [])

  useEffect(() => {
    if (selected) {
      localStorage.setItem('vms_focused_stream_id', selected.stream_id)
    } else {
      localStorage.removeItem('vms_focused_stream_id')
    }
  }, [selected])

  async function loadCameras() {
    setLoading(true)
    try {
      const data = await fetchCameras()
      setCameras(data)
      setStatusText(`Loaded ${data.length} streams`)
      setLastSync(new Date().toLocaleString())

      const storedFocusedId = localStorage.getItem('vms_focused_stream_id')
      const restoredFocused = data.find((c) => c.stream_id === storedFocusedId)

      if (restoredFocused) {
        setSelected(restoredFocused)
      } else if (data.length > 0) {
        setSelected(data[0])
      }
    } catch (e) {
      setStatusText(e instanceof Error ? e.message : 'Failed to load cameras')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadCameras().catch(() => {})
  }, [])

  useEffect(() => {
    if (!selected?.stream_id) return
    fetchRecordings(selected.stream_id).then(setRecordings).catch(() => setRecordings([]))
  }, [selected?.stream_id])

  const liveCount = useMemo(() => cameras.filter((c) => c.active).length, [cameras])

  async function handleSync() {
    setStatusText('Syncing with camera API...')
    try {
      await syncCameras()
      await loadCameras()
      setStatusText('Camera sync completed')
    } catch (e) {
      setStatusText(e instanceof Error ? e.message : 'Sync failed')
    }
  }

  return (
    <div className="appShell">
      <Sidebar
        onRefresh={handleSync}
        totalCameras={standardCameras.length}
        liveCameras={liveCount}
        lastSyncText={lastSync}
        activeTab={activeTab}
        setActiveTab={setActiveTab as (tab: string) => void}
      />

      <main className="mainPanel">
        <header className="topBar">
          <div className="topLeft">
            <div className="topBadge"><Activity size={14} /> {statusText}</div>
            <div className="topNote">Connected to backend API and HLS live stream. {loading ? 'Refreshing cameras…' : ''}</div>
          </div>
          <div className="topActions">
            <button className="ghostBtn" onClick={handleSync}><RefreshCcw size={16} /> Refresh</button>
          </div>
        </header>

        <div className="workspace singleTab">
          {activeTab === 'dashboard' && (
            <Dashboard
              cameras={cameras}
              query={query}
              setQuery={setQuery}
              selectedStreamIds={selected ? [selected.stream_id] : []}
              focusedStreamId={selected?.stream_id}
              onSelect={(cam) => {
                setSelected(cam)
                setActiveTab('live')
              }}
            />
          )}

          {activeTab === 'live_wall' && (
            <div className="streamArea">
              <LiveWall
                mode="wall"
                statusTextSetter={setStatusText}
                selectedCamera={selected}
                onClearSelection={() => setSelected(undefined)}
                onNavigateToPlayback={(cam) => {
                  setSelected(cam)
                  setActiveTab('playback')
                }}
              />
            </div>
          )}

          {activeTab === 'live' && (
            <div className="streamArea">
              <LiveWall
                mode="grid"
                statusTextSetter={setStatusText}
                selectedCamera={selected}
                onClearSelection={() => setSelected(undefined)}
                onNavigateToPlayback={(cam) => {
                  setSelected(cam)
                  setActiveTab('playback')
                }}
              />
            </div>
          )}

          {activeTab === 'playback' && (
            <div className="streamArea">
              <Playback
                streamId={selected ? resolvePlaybackStreamId(selected, policy) : undefined}
                cameraName={selected?.name}
                cameras={cameras}
                onSelectCamera={(cam) => setSelected(cam)}
              />
            </div>
          )}

          {activeTab === 'edgepush' && (
            <div className="streamArea">
              <EdgePushPage edgeCameras={edgeCameras} />
            </div>
          )}

          {activeTab === 'camera_config' && (
            <div className="streamArea">
              <CameraManagement cameras={cameras} onRefresh={loadCameras} />
            </div>
          )}

          {activeTab === 'webcam_stream' && (
            <div className="streamArea">
              <WebcamStream edgeCameras={edgeCameras} onRefresh={loadCameras} />
            </div>
          )}

          {activeTab === 'gap_recovery' && (
            <div className="streamArea">
              <GapRecovery cameras={cameras} />
            </div>
          )}

          {activeTab === 'transcoder_monitor' && (
            <div className="streamArea">
              <TranscoderMonitor />
            </div>
          )}
        </div>
      </main>
    </div>
  )
}