import { useEffect, useMemo, useState, useRef } from 'react'
import type { Camera, RecordingSegment } from './types'
import { Sidebar } from './components/Sidebar'
import { Player } from './components/Player'
import { Dashboard } from './pages/Dashboard'
import { CameraDetails } from './pages/CameraDetails'
import { Playback } from './pages/Playback'
import { EdgePushPage } from './pages/EdgePush'
import { LiveWall } from './pages/LiveWall'
import { fetchCameras, fetchPlayback, fetchRecordings, startLive, stopLive, syncCameras } from './lib/api'
import { Activity, RefreshCcw, ServerCrash, Square, Play, X, Maximize2, Minimize2, ChevronDown, Search } from 'lucide-react'

function getStreamIdForLayout(cam: Camera, layoutSize: number): string {
  if (!cam.streams || cam.streams.length === 0) {
    return cam.stream_id;
  }
  const targetProfile = layoutSize === 1 ? 'MAIN' : 'SUB';
  const matchedStream = cam.streams.find(s => s.profile_type === targetProfile);
  if (matchedStream) {
    return matchedStream.stream_id;
  }
  const mainStream = cam.streams.find(s => s.profile_type === 'MAIN');
  if (mainStream) return mainStream.stream_id;
  const subStream = cam.streams.find(s => s.profile_type === 'SUB');
  if (subStream) return subStream.stream_id;
  return cam.stream_id;
}

export default function App() {
  const [cameras, setCameras] = useState<Camera[]>([])
  const [selected, setSelected] = useState<Camera | undefined>()

  const isEdgeCamera = (cam: Camera) => !cam.rtsp_url || cam.rtsp_url.trim() === "" || !cam.rtsp_url.trim().toLowerCase().startsWith("rtsp://");

  const standardCameras = useMemo(() => {
    return cameras.filter(cam => !isEdgeCamera(cam))
  }, [cameras])

  const edgeCameras = useMemo(() => {
    return cameras.filter(cam => isEdgeCamera(cam))
  }, [cameras])

  const [selectedStreams, setSelectedStreams] = useState<Camera[]>([])

  const [layout, setLayout] = useState(() => {
    const stored = localStorage.getItem('vms_layout')
    return stored ? parseInt(stored, 10) : 4
  }) 
  const [activeTab, setActiveTab] = useState<'dashboard' | 'live' | 'playback' | 'edgepush'>(() => {
    const stored = localStorage.getItem('vms_active_tab')
    return (stored === 'dashboard' || stored === 'live' || stored === 'playback' || stored === 'edgepush') ? stored : 'dashboard'
  })
  const [query, setQuery] = useState('')
  const [recordings, setRecordings] = useState<RecordingSegment[]>([])
  const [liveUrl, setLiveUrl] = useState<string>('')
  const [statusText, setStatusText] = useState('Ready')
  const [loading, setLoading] = useState(false)
  const [liveLoading, setLiveLoading] = useState(false)
  const [lastSync, setLastSync] = useState('Never')
  const [isFullView, setIsFullView] = useState(false)
  const [liveSubTab, setLiveSubTab] = useState<'manual' | 'wall'>('manual')

  const [liveDropdownOpen, setLiveDropdownOpen] = useState(false)
  const [liveSearchQuery, setLiveSearchQuery] = useState('')
  const liveDropdownRef = useRef<HTMLDivElement | null>(null)

  // Caching states to localStorage for page-refresh persistence
  useEffect(() => {
    localStorage.setItem('vms_active_tab', activeTab)
  }, [activeTab])

  useEffect(() => {
    localStorage.setItem('vms_layout', layout.toString())
  }, [layout])

  useEffect(() => {
    if (selectedStreams.length > 0) {
      const ids = selectedStreams.map((c) => c.stream_id)
      localStorage.setItem('vms_selected_stream_ids', JSON.stringify(ids))
    } else {
      localStorage.removeItem('vms_selected_stream_ids')
    }
  }, [selectedStreams])

  useEffect(() => {
    if (selected) {
      localStorage.setItem('vms_focused_stream_id', selected.stream_id)
    } else {
      localStorage.removeItem('vms_focused_stream_id')
    }
  }, [selected])

  // Exit full view automatically if grid is cleared
  useEffect(() => {
    if (selectedStreams.length === 0) {
      setIsFullView(false)
    }
  }, [selectedStreams.length])

  // Keydown listener for Esc key to exit full view
  useEffect(() => {
    if (!isFullView) return
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setIsFullView(false)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isFullView])

  // Click-outside listener for Live View camera selector dropdown
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (liveDropdownRef.current && !liveDropdownRef.current.contains(event.target as Node)) {
        setLiveDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const filteredLiveCameras = useMemo(() => {
    return standardCameras.filter(
      (cam) =>
        cam.name.toLowerCase().includes(liveSearchQuery.toLowerCase()) ||
        cam.stream_id.toLowerCase().includes(liveSearchQuery.toLowerCase())
    )
  }, [standardCameras, liveSearchQuery])

  async function loadCameras() {
    setLoading(true)
    try {
      const data = await fetchCameras()
      setCameras(data)
      setStatusText(`Loaded ${data.length} streams`)
      setLastSync(new Date().toLocaleString())

      // Restore selected streams from localStorage
      const storedIdsJson = localStorage.getItem('vms_selected_stream_ids')
      let restoredStreams: Camera[] = []
      if (storedIdsJson) {
        try {
          const storedIds = JSON.parse(storedIdsJson) as string[]
          restoredStreams = data.filter((c) => storedIds.includes(c.stream_id))
        } catch (e) {
          console.error("Failed to parse stored stream IDs", e)
        }
      }

      const storedFocusedId = localStorage.getItem('vms_focused_stream_id')
      const restoredFocused = restoredStreams.find((c) => c.stream_id === storedFocusedId)

      const standardData = data.filter(c => !isEdgeCamera(c))
      const restoredStandardStreams = restoredStreams.filter(c => !isEdgeCamera(c))
      if (restoredStandardStreams.length > 0) {
        setSelectedStreams(restoredStandardStreams)
        setSelected(restoredFocused && !isEdgeCamera(restoredFocused) ? restoredFocused : restoredStandardStreams[0])
      } else if (standardData.length > 0) {
        setSelected(standardData[0])
        setSelectedStreams([standardData[0]])
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

  const liveCount = useMemo(() => standardCameras.filter((c) => c.active).length, [standardCameras])

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
    // Ensure the started camera is in the selectedStreams grid
    setSelectedStreams(prev => {
      if (!prev.some(x => x.stream_id === selected.stream_id)) {
        if (prev.length >= layout) {
          return [...prev.slice(1), selected]
        }
        return [...prev, selected]
      }
      return prev
    })
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
              cameras={standardCameras}
              query={query}
              setQuery={setQuery}
              selectedStreamIds={selectedStreams.map((c) => c.stream_id)}
              focusedStreamId={selected?.stream_id}
              onSelect={(cam) => {
                const isSelected = selectedStreams.some(x => x.stream_id === cam.stream_id)
                if (isSelected) {
                  const remaining = selectedStreams.filter(x => x.stream_id !== cam.stream_id)
                  setSelectedStreams(remaining)
                  if (selected?.stream_id === cam.stream_id) {
                    setSelected(remaining[0] || undefined)
                  }
                } else {
                  if (selectedStreams.length >= layout) {
                    setStatusText(`Max layout limit (${layout}) reached. Change layout grid to add more.`)
                    return
                  }
                  setSelectedStreams(prev => [...prev, cam])
                  setSelected(cam)
                }
                setActiveTab('live')
              }}
            />
          )}

          {activeTab === 'live' && (
            <div className="streamArea" style={{ display: 'flex', flexDirection: 'column' }}>
              <div className="liveSubTabs">
                <button
                  type="button"
                  className={`liveSubTab ${liveSubTab === 'manual' ? 'active' : ''}`}
                  onClick={() => setLiveSubTab('manual')}
                >
                  Manual Grid
                </button>
                <button
                  type="button"
                  className={`liveSubTab ${liveSubTab === 'wall' ? 'active' : ''}`}
                  onClick={() => setLiveSubTab('wall')}
                >
                  Live Camera Wall
                </button>
              </div>

              {liveSubTab === 'wall' ? (
                <LiveWall statusTextSetter={setStatusText} />
              ) : (
                <>
                  <div className="controlsBar">
                    <div className="controlGroup">
                      <span className="controlLabel">Layout Grid</span>
                      <div className="btnToggleGroup">
                        {[1, 2, 4, 9].map((size) => (
                          <button
                            key={size}
                            className={`toggleBtn ${layout === size ? 'active' : ''}`}
                            onClick={() => {
                              setLayout(size)
                              if (selectedStreams.length > size) {
                                const truncated = selectedStreams.slice(0, size)
                                setSelectedStreams(truncated)
                                if (selected && !truncated.some(s => s.stream_id === selected.stream_id)) {
                                  setSelected(truncated[0] || undefined)
                                }
                              }
                            }}
                          >
                            {size === 1 ? '1x1' : size === 2 ? '1x2' : size === 4 ? '2x2' : '3x3'}
                          </button>
                        ))}
                      </div>
                    </div>

                    <div className="controlGroup">
                      <span className="controlLabel">Select Feeds</span>
                      <div className="dropdownContainer" ref={liveDropdownRef}>
                        <button
                          type="button"
                          className="dropdownTrigger"
                          onClick={() => setLiveDropdownOpen(!liveDropdownOpen)}
                          style={{ minWidth: '200px' }}
                        >
                          <span>
                            {selectedStreams.length === 0
                              ? 'Select Cameras…'
                              : `${selectedStreams.length}/${layout} selected`}
                          </span>
                          <ChevronDown size={14} style={{ opacity: 0.7 }} />
                        </button>
                        {liveDropdownOpen && (
                          <div className="dropdownMenu">
                            <div className="dropdownSearchWrapper">
                              <input
                                type="text"
                                className="dropdownSearchInput"
                                placeholder="Search cameras..."
                                value={liveSearchQuery}
                                onChange={(e) => setLiveSearchQuery(e.target.value)}
                                autoFocus
                              />
                            </div>
                            <div className="dropdownList">
                              {filteredLiveCameras.length > 0 ? (
                                filteredLiveCameras.map((cam) => {
                                  const isChecked = selectedStreams.some((x) => x.stream_id === cam.stream_id)
                                  return (
                                    <div
                                      key={cam.stream_id}
                                      className={`dropdownOption ${isChecked ? 'selected' : ''}`}
                                      onClick={() => {
                                        if (isChecked) {
                                          const remaining = selectedStreams.filter((x) => x.stream_id !== cam.stream_id)
                                          setSelectedStreams(remaining)
                                          if (selected?.stream_id === cam.stream_id) {
                                            setSelected(remaining[0] || undefined)
                                          }
                                        } else {
                                          if (selectedStreams.length >= layout) {
                                            setStatusText(`Max layout limit (${layout}) reached. Change layout grid to add more.`)
                                            return
                                          }
                                          setSelectedStreams((prev) => [...prev, cam])
                                          setSelected(cam)
                                        }
                                      }}
                                    >
                                      <input
                                        type="checkbox"
                                        className="dropdownOptionCheckbox"
                                        checked={isChecked}
                                        readOnly
                                      />
                                      <div style={{ display: 'flex', flexDirection: 'column', flex: 1 }}>
                                        <span style={{ fontWeight: 600 }}>{cam.name}</span>
                                        <span style={{ fontSize: '0.72rem', opacity: 0.6 }}>{cam.stream_id} ({cam.stream_type})</span>
                                      </div>
                                    </div>
                                  )
                                })
                              ) : (
                                <div style={{ padding: '8px', fontSize: '0.8rem', color: '#94a3b8', textAlign: 'center' }}>
                                  No cameras found
                                </div>
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    </div>

                    <div className="controlGroup">
                      <button
                        className="batchBtn start"
                        onClick={startAll}
                        disabled={selectedStreams.length === 0}
                      >
                        <Play size={14} /> Start All
                      </button>
                      <button
                        className="batchBtn stop"
                        onClick={stopAll}
                        disabled={selectedStreams.length === 0}
                      >
                        <Square size={14} /> Stop All
                      </button>
                      <button
                        className="batchBtn"
                        onClick={() => {
                          setSelectedStreams([])
                          setSelected(undefined)
                        }}
                        disabled={selectedStreams.length === 0}
                      >
                        Clear
                      </button>
                      <button
                        className="batchBtn"
                        onClick={() => setIsFullView(true)}
                        disabled={selectedStreams.length === 0}
                        style={{
                          background: selectedStreams.length > 0 ? 'rgba(59, 130, 246, 0.15)' : 'rgba(15, 23, 42, 0.5)',
                          color: selectedStreams.length > 0 ? '#60a5fa' : '#cbd5e1',
                          borderColor: selectedStreams.length > 0 ? 'rgba(59, 130, 246, 0.3)' : 'rgba(148, 163, 184, 0.14)',
                        }}
                        title="View selected cameras in immersive fullscreen"
                      >
                        <Maximize2 size={14} /> Full View
                      </button>
                    </div>
                  </div>

                  <div className="playerWrap">
                    {selectedStreams.length > 0 ? (
                      <div className={`videoGrid layout-${layout}`}>
                        {selectedStreams.map((cam) => (
                          <Player
                            key={cam.stream_id}
                            src={`/api/streams/${encodeURIComponent(getStreamIdForLayout(cam, layout))}/live/index.m3u8`}
                            posterLabel={`${cam.name} — ${cam.stream_type}`}
                            isFocused={selected?.stream_id === cam.stream_id}
                            onFocus={() => setSelected(cam)}
                            onClose={() => {
                              const remaining = selectedStreams.filter(x => x.stream_id !== cam.stream_id)
                              setSelectedStreams(remaining)
                              if (selected?.stream_id === cam.stream_id) {
                                setSelected(remaining[0] || undefined)
                              }
                            }}
                          />
                        ))}
                      </div>
                    ) : (
                      <div className="emptyStream">
                        <ServerCrash size={42} />
                        <h3>No camera selected</h3>
                        <p>Go to the Dashboard tab on the left to select camera feeds.</p>
                      </div>
                    )}
                    {liveLoading && <div className="liveLoading">Starting stream…</div>}
                  </div>

                  <CameraDetails
                    camera={selected}
                    recordings={recordings}
                    onStartLive={handleStartLive}
                    onStopLive={handleStopLive}
                    onOpenPlayback={() => {
                      setActiveTab('playback')
                    }}
                  />
                </>
              )}
            </div>
          )}

          {activeTab === 'playback' && (
            <div className="streamArea">
              <Playback
                streamId={selected?.stream_id}
                cameraName={selected?.name}
                cameras={standardCameras}
                onSelectCamera={(cam) => setSelected(cam)}
              />
            </div>
          )}

          {activeTab === 'edgepush' && (
            <div className="streamArea">
              <EdgePushPage edgeCameras={edgeCameras} />
            </div>
          )}
        </div>
      </main>

      {isFullView && selectedStreams.length > 0 && (
        <div className="fullscreenVideoWall">
          <div className={`videoGrid layout-${layout}`}>
            {selectedStreams.map((cam) => (
              <Player
                key={cam.stream_id}
                src={`/api/streams/${encodeURIComponent(getStreamIdForLayout(cam, layout))}/live/index.m3u8`}
                posterLabel={`${cam.name} — ${cam.stream_type}`}
                isFocused={selected?.stream_id === cam.stream_id}
                onFocus={() => setSelected(cam)}
                onClose={() => {
                  const remaining = selectedStreams.filter(x => x.stream_id !== cam.stream_id)
                  setSelectedStreams(remaining)
                  if (selected?.stream_id === cam.stream_id) {
                    setSelected(remaining[0] || undefined)
                  }
                }}
                minimal={true}
              />
            ))}
          </div>
          <button
            className="exitFullViewBtn"
            type="button"
            onClick={() => setIsFullView(false)}
            title="Exit Full View"
          >
            <Minimize2 size={18} /> Exit Full View
          </button>
        </div>
      )}
    </div>
  )
}