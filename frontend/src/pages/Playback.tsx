import { useState, useEffect, useRef } from 'react'
import { Calendar, PlayCircle, Download, Film, Loader2, Play, AlertCircle, FileVideo, SkipForward } from 'lucide-react'
import type { RecordingSegment } from '../types'

type Props = {
  streamId?: string
  cameraName?: string
}

export function Playback({ streamId, cameraName }: Props) {
  const [dateTime, setDateTime] = useState('')
  const [segments, setSegments] = useState<RecordingSegment[]>([])
  const [currentIndex, setCurrentIndex] = useState(-1)
  const [loading, setLoading] = useState(false)
  const videoRef = useRef<HTMLVideoElement | null>(null)

  // Initialize date-time input to 2 hours ago
  useEffect(() => {
    const twoHoursAgo = new Date(Date.now() - 2 * 3600 * 1000)
    const year = twoHoursAgo.getFullYear()
    const month = String(twoHoursAgo.getMonth() + 1).padStart(2, '0')
    const day = String(twoHoursAgo.getDate()).padStart(2, '0')
    const hours = String(twoHoursAgo.getHours()).padStart(2, '0')
    const minutes = String(twoHoursAgo.getMinutes()).padStart(2, '0')
    setDateTime(`${year}-${month}-${day}T${hours}:${minutes}`)
  }, [])

  // Fetch recordings from the specified start time
  async function fetchSegmentsForTime(targetDateTime: string) {
    if (!streamId || !targetDateTime) return
    setLoading(true)
    const startTs = Math.floor(new Date(targetDateTime).getTime() / 1000)
    // Fetch 12 hours of recordings starting from target time
    const endTs = startTs + 12 * 3600 
    try {
      const res = await fetch(`/api/playback/${encodeURIComponent(streamId)}?start_ts=${startTs}&end_ts=${endTs}`)
      if (res.ok) {
        const data: RecordingSegment[] = await res.json()
        setSegments(data)
        if (data.length > 0) {
          setCurrentIndex(0)
        } else {
          setCurrentIndex(-1)
        }
      }
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  // Refetch when camera selection changes
  useEffect(() => {
    if (streamId && dateTime) {
      fetchSegmentsForTime(dateTime)
    } else {
      setSegments([])
      setCurrentIndex(-1)
    }
  }, [streamId])

  // Automatically advance to the next segment when the current one finishes
  function handleVideoEnded() {
    if (currentIndex >= 0 && currentIndex < segments.length - 1) {
      setCurrentIndex(prev => prev + 1)
    }
  }

  const currentSegment = segments[currentIndex]

  return (
    <section className="content" id="playback">
      <div className="panelHead">
        <div>
          <div className="eyebrow">Continuous Playback</div>
          <h2 className="panelTitle">{cameraName ?? 'No Camera Selected'}</h2>
          <div className="panelSub">
            {streamId ? `Stream ID: ${streamId}` : 'Select a camera to load recorded video history'}
          </div>
        </div>
      </div>

      {streamId ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
          {/* Controls Bar */}
          <div className="controlsBar" style={{ margin: 0 }}>
            <div className="controlGroup">
              <span className="controlLabel"><Calendar size={14} /> Start Time</span>
              <input
                type="datetime-local"
                value={dateTime}
                onChange={(e) => setDateTime(e.target.value)}
                className="searchBar"
                style={{
                  width: 'auto',
                  padding: '8px 12px',
                  borderRadius: '12px',
                  border: '1px solid rgba(148,163,184,0.16)',
                  background: 'rgba(2,6,23,0.4)',
                  color: '#fff',
                  fontSize: '0.9rem'
                }}
              />
              <button
                className="primaryBtn"
                onClick={() => fetchSegmentsForTime(dateTime)}
                disabled={loading}
                style={{ borderRadius: '12px', padding: '9px 18px', fontSize: '0.86rem' }}
              >
                {loading ? <Loader2 className="spin" size={14} /> : 'Load Playback'}
              </button>
            </div>

            {segments.length > 0 && (
              <div className="controlGroup">
                <span className="chip" style={{ background: 'rgba(59,130,246,0.12)', borderColor: 'rgba(59,130,246,0.2)' }}>
                  {segments.length} segments loaded
                </span>
              </div>
            )}
          </div>

          {/* Main Playback workspace split */}
          {segments.length > 0 ? (
            <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: '18px', alignItems: 'start' }}>
              {/* Left Column: Player */}
              <div className="playerShell">
                <div className="playerHeader">
                  <div>
                    <span className="eyebrow">Playing segment {currentIndex + 1} of {segments.length}</span>
                    <h3 className="panelTitle" style={{ fontSize: '1.05rem', margin: '4px 0 0', wordBreak: 'break-all' }}>
                      {currentSegment?.file_path.split(/[\\/]/).pop()}
                    </h3>
                  </div>
                  <div className="playerChips">
                    <span className="chip chipLive" style={{ background: 'rgba(59,130,246,0.15)', color: '#60a5fa', borderColor: 'rgba(96,165,250,0.2)' }}>
                      <Film size={12} /> Playback
                    </span>
                  </div>
                </div>

                <div className="playerViewport" style={{ position: 'relative', overflow: 'hidden', borderRadius: '20px' }}>
                  <video
                    ref={videoRef}
                    src={currentSegment ? `/api/recordings/file?path=${encodeURIComponent(currentSegment.file_path)}` : undefined}
                    className="videoEl"
                    controls
                    autoPlay
                    playsInline
                    onEnded={handleVideoEnded}
                    style={{ width: '100%', height: '100%', objectFit: 'contain' }}
                  />
                </div>

                <div className="playerControls" style={{ marginTop: '12px' }}>
                  <span className="playerHint" style={{ fontSize: '0.8rem', color: '#94a3b8' }}>
                    Segment Start: {currentSegment ? new Date(currentSegment.start_ts * 1000).toLocaleString() : '-'}
                  </span>
                  {currentIndex < segments.length - 1 && (
                    <button
                      className="miniBtn"
                      type="button"
                      onClick={() => setCurrentIndex(prev => prev + 1)}
                      style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '6px' }}
                    >
                      <SkipForward size={14} /> Skip Segment
                    </button>
                  )}
                </div>

                <div className="playerFooter" style={{ marginTop: '12px' }}>
                  <AlertCircle size={14} />
                  <span>Playback will automatically advance to the next recorded segment file.</span>
                </div>
              </div>

              {/* Right Column: List of segments */}
              <div className="playbackCard" style={{ margin: 0, padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
                <h3 style={{ margin: '0 0 6px', fontSize: '1.05rem', color: '#fff' }}>Playlist Timeline</h3>
                
                <div style={{ display: 'grid', gap: '8px', maxHeight: '430px', overflowY: 'auto', paddingRight: '4px' }}>
                  {segments.map((seg, idx) => {
                    const isActive = idx === currentIndex
                    return (
                      <button
                        key={seg.id}
                        type="button"
                        onClick={() => setCurrentIndex(idx)}
                        className={`playbackRow`}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          width: '100%',
                          textAlign: 'left',
                          background: isActive ? 'linear-gradient(135deg, rgba(37,99,235,0.15), rgba(15,23,42,0.85))' : 'rgba(2,6,23,0.3)',
                          borderColor: isActive ? 'rgba(59,130,246,0.35)' : 'rgba(148,163,184,0.1)',
                          cursor: 'pointer',
                          padding: '12px 14px',
                          borderRadius: '16px',
                          borderWidth: '1px',
                          borderStyle: 'solid',
                          transition: 'all 0.15s ease'
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', minWidth: 0 }}>
                          <PlayCircle size={18} style={{ color: isActive ? '#60a5fa' : '#94a3b8', flexShrink: 0 }} />
                          <div style={{ minWidth: 0 }}>
                            <div
                              className="playbackName"
                              style={{
                                color: isActive ? '#fff' : '#cbd5e1',
                                fontWeight: isActive ? '800' : '500',
                                fontSize: '0.9rem',
                                whiteSpace: 'nowrap',
                                overflow: 'hidden',
                                textOverflow: 'ellipsis'
                              }}
                            >
                              {seg.file_path.split(/[\\/]/).pop()}
                            </div>
                            <div className="recordTime" style={{ fontSize: '0.78rem', color: '#94a3b8', marginTop: '4px' }}>
                              {new Date(seg.start_ts * 1000).toLocaleTimeString()} - {new Date(seg.end_ts * 1000).toLocaleTimeString()}
                            </div>
                          </div>
                        </div>

                        {isActive && (
                          <span
                            className="chip chipLive"
                            style={{
                              fontSize: '0.72rem',
                              padding: '4px 8px',
                              background: 'rgba(34,197,94,0.15)',
                              color: '#4ade80',
                              borderColor: 'rgba(34,197,94,0.25)',
                              marginLeft: '8px',
                              flexShrink: 0
                            }}
                          >
                            Playing
                          </span>
                        )}
                      </button>
                    )
                  })}
                </div>
              </div>
            </div>
          ) : (
            <div className="emptyState" style={{ padding: '40px 20px' }}>
              <FileVideo size={42} style={{ color: '#64748b' }} />
              <h3 style={{ marginTop: '12px' }}>No Playback Segments Found</h3>
              <p style={{ marginTop: '6px', maxWidth: '45ch' }}>
                There are no recorded segments starting from the selected time range. Please select another date/time or ensure the camera is recording.
              </p>
            </div>
          )}
        </div>
      ) : (
        <div className="emptyState" style={{ padding: '40px 20px' }}>
          <FileVideo size={42} style={{ color: '#64748b' }} />
          <h3 style={{ marginTop: '12px' }}>Select a Camera</h3>
          <p style={{ marginTop: '6px' }}>Go to the Dashboard tab to select a camera to load recorded video history.</p>
        </div>
      )}
    </section>
  )
}
