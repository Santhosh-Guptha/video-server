import { useEffect, useMemo, useState } from 'react'
import type { Camera, RecordingSegment } from './types'
import { Sidebar } from './components/Sidebar'
import { Player } from './components/Player'
import { Dashboard } from './pages/Dashboard'
import { CameraDetails } from './pages/CameraDetails'
import { Playback } from './pages/Playback'
import { fetchCameras, fetchPlayback, fetchRecordings, startLive, stopLive, syncCameras } from './lib/api'
import { Activity, RefreshCcw, ServerCrash } from 'lucide-react'
import { VideoWall } from './components/VideoWall'

export default function App() {
  const [cameras, setCameras] = useState<Camera[]>([])
 const [selected, setSelected] = useState<Camera | undefined>()

const [selectedStreams, setSelectedStreams] = useState<Camera[]>([])

const [layout, setLayout] = useState(4) 
  const [query, setQuery] = useState('')
  const [recordings, setRecordings] = useState<RecordingSegment[]>([])
  const [playbackSegments, setPlaybackSegments] = useState<RecordingSegment[]>([])
  const [liveUrl, setLiveUrl] = useState<string>('')
  const [statusText, setStatusText] = useState('Ready')
  const [loading, setLoading] = useState(false)
  const [liveLoading, setLiveLoading] = useState(false)
  const [lastSync, setLastSync] = useState('Never')

  async function loadCameras() {
    setLoading(true)
    try {
      const data = await fetchCameras()
      setCameras(data)
      setStatusText(`Loaded ${data.length} streams`)
      setLastSync(new Date().toLocaleString())
      if (!selected && data.length > 0) setSelected(data[0])
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
  const selectedStreamId = selected?.stream_id

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

  async function handleStartLive() {
    if (!selected) return
    setLiveLoading(true)
    setStatusText(`Starting live: ${selected.name}`)
    try {
      const out = await startLive(selected.stream_id)
      setLiveUrl(out.hls.startsWith("http") ? out.hls : out.hls);
      const recs = await fetchRecordings(selected.stream_id)
      setRecordings(recs)
      setStatusText(`Live started: ${selected.name}`)
    } catch (e) {
      setStatusText(e instanceof Error ? e.message : 'Live start failed')
    } finally {
      setLiveLoading(false)
    }
  }

  async function handleStopLive() {
    if (!selected) return
    setStatusText(`Stopping live: ${selected.name}`)
    try {
      await stopLive(selected.stream_id)
      setStatusText(`Live stopped: ${selected.name}`)
    } catch (e) {
      setStatusText(e instanceof Error ? e.message : 'Stop failed')
    }
  }

 async function startAll() {
  setStatusText(`Starting ${selectedStreams.length} streams...`)

  for (const cam of selectedStreams) {
    try {
      await startLive(cam.stream_id)
    } catch (e) {
      console.error(e)
    }
  }

  setStatusText(
    `${selectedStreams.length} streams started`
  )
}

async function stopAll() {
  setStatusText(`Stopping streams...`)

  for (const cam of selectedStreams) {
    try {
      await stopLive(cam.stream_id)
    } catch (e) {
      console.error(e)
    }
  }

  setStatusText("All streams stopped")
}

  async function handlePlayback() {
    if (!selected) return
    const end = Math.floor(Date.now() / 1000)
    const start = end - 24 * 3600
    setStatusText(`Loading playback for ${selected.name}`)
    try {
      const segs = await fetchPlayback(selected.stream_id, start, end)
      setPlaybackSegments(segs)
      setStatusText(`Playback loaded: ${segs.length} segments`)
    } catch (e) {
      setStatusText(e instanceof Error ? e.message : 'Playback load failed')
    }
  }

  return (
    <div className="appShell">
      <Sidebar onRefresh={handleSync} totalCameras={cameras.length} liveCameras={liveCount} lastSyncText={lastSync} />

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

        <div className="workspace">
<Dashboard
  cameras={cameras}
  query={query}
  setQuery={setQuery}
  selectedStreamId={selectedStreamId}
  onSelect={(cam) => {

    setSelected(cam)

    setSelectedStreams(prev => {

      const exists = prev.find(
        x => x.stream_id === cam.stream_id
      )

      if (exists) {
        return prev.filter(
          x => x.stream_id !== cam.stream_id
        )
      }

      if (prev.length >= layout) {
        return prev
      }

      return [...prev, cam]
    })
  }}
/>
          <div className="streamArea">
            <div className="playerWrap">
              {selected ? (
        <Player
  src={
    liveUrl ||
    `/api/streams/${encodeURIComponent(
      selected.stream_id
    )}/live/index.m3u8`
  }
  posterLabel={`${selected.name} — ${selected.stream_type}`}
/>
              ) : (
                <div className="emptyStream">
                  <ServerCrash size={42} />
                  <h3>No camera selected</h3>
                  <p>Pick a stream on the left to start live view.</p>
                </div>
              )}
              {liveLoading && <div className="liveLoading">Starting stream…</div>}
            </div>

            <CameraDetails camera={selected} recordings={recordings} onStartLive={handleStartLive} onStopLive={handleStopLive} onOpenPlayback={handlePlayback} />
            <Playback streamId={selected?.stream_id} segments={playbackSegments} />
          </div>
        </div>
      </main>
    </div>
  )
}