import { useState, useEffect, useRef } from 'react'
import { Calendar, PlayCircle, Film, Loader2, AlertCircle, FileVideo, ChevronDown, Search } from 'lucide-react'
import type { Camera } from '../types'

type Props = {
  streamId?: string
  cameraName?: string
  cameras: Camera[]
  onSelectCamera: (camera: Camera) => void
}

export function Playback({ streamId, cameraName, cameras, onSelectCamera }: Props) {
  const [availableDates, setAvailableDates] = useState<string[]>([])
  const [selectedDate, setSelectedDate] = useState('')
  const [selectedTime, setSelectedTime] = useState('00:00')
  const [streamUrl, setStreamUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [hasSearched, setHasSearched] = useState(false)
  const videoRef = useRef<HTMLVideoElement | null>(null)

  const [segments, setSegments] = useState<any[]>([])
  const [currentAbsoluteTs, setCurrentAbsoluteTs] = useState<number>(0)
  const [rangeStartTs, setRangeStartTs] = useState<number>(0)
  const [isDragging, setIsDragging] = useState(false)
  const timelineRef = useRef<HTMLDivElement | null>(null)
  const [currentStreamStartTs, setCurrentStreamStartTs] = useState<number>(0)

  const [dropdownOpen, setDropdownOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const dropdownRef = useRef<HTMLDivElement | null>(null)

  const [summary, setSummary] = useState<{ count: number; min_start_ts: number | null; max_end_ts: number | null } | null>(null)
  const [loadingSummary, setLoadingSummary] = useState(false)

  // Handle click outside for dropdown
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Fetch summary when streamId changes
  useEffect(() => {
    if (!streamId) {
      setSummary(null)
      return
    }

    async function loadSummary() {
      setLoadingSummary(true)
      try {
        const res = await fetch(`/api/playback/${encodeURIComponent(streamId!)}/summary`)
        if (res.ok) {
          const data = await res.json()
          setSummary(data)
        }
      } catch (e) {
        console.error('Failed to load summary:', e)
      } finally {
        setLoadingSummary(false)
      }
    }

    loadSummary()
  }, [streamId])

  const filteredCameras = cameras.filter(
    (cam) =>
      cam.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      cam.stream_id.toLowerCase().includes(searchQuery.toLowerCase())
  )

  // Fetch available dates when camera changes
  useEffect(() => {
    if (!streamId) {
      setAvailableDates([])
      setSelectedDate('')
      setStreamUrl('')
      setHasSearched(false)
      setSegments([])
      return
    }

    async function loadAvailableDates() {
      setLoading(true)
      try {
        const res = await fetch(`/api/playback/${encodeURIComponent(streamId!)}/available-dates`)
        if (res.ok) {
          const dates: string[] = await res.json()
          setAvailableDates(dates)
          if (dates.length > 0) {
            setSelectedDate(dates[dates.length - 1])
          } else {
            setSelectedDate('')
          }
        }
      } catch (e) {
        console.error('Failed to load dates:', e)
      } finally {
        setLoading(false)
      }
    }

    loadAvailableDates()
    setStreamUrl('')
    setHasSearched(false)
    setSegments([])
    setCurrentStreamStartTs(0)
  }, [streamId])

  async function loadPlaybackData(targetStartTs: number) {
    if (!streamId) return
    setLoading(true)
    try {
      const endTs = targetStartTs + 3600
      const response = await fetch(`/api/playback/${encodeURIComponent(streamId)}?start_ts=${targetStartTs}&end_ts=${endTs}`)
      if (response.ok) {
        const segs = await response.json()
        setSegments(segs)

        if (segs.length > 0) {
          // Check if the backend shifted the start time because there were no recordings in the requested hour
          let alignedRangeStart = targetStartTs
          if (segs[0].start_ts > targetStartTs + 3600 || segs[0].start_ts < targetStartTs) {
            alignedRangeStart = segs[0].start_ts
          }

          setRangeStartTs(alignedRangeStart)
          const actualStartTs = Math.max(alignedRangeStart, segs[0].start_ts)
          const streamEndTs = alignedRangeStart + 3600
          const url = `/api/playback/${encodeURIComponent(streamId)}/stream.mp4?start_ts=${actualStartTs}&end_ts=${streamEndTs}`
          
          setStreamUrl(url)
          setCurrentStreamStartTs(actualStartTs)
          setCurrentAbsoluteTs(actualStartTs)
          setHasSearched(true)
          setTimeout(() => {
            if (videoRef.current) {
              videoRef.current.load()
            }
          }, 50)
        } else {
          setRangeStartTs(targetStartTs)
          setCurrentAbsoluteTs(targetStartTs)
          setStreamUrl('')
          setHasSearched(true)
        }
      }
    } catch (e) {
      console.error('Failed to load playback segments:', e)
    } finally {
      setLoading(false)
    }
  }

  function handleLoadStream() {
    if (!streamId || !selectedDate || !selectedTime) return
    const localDateTimeStr = `${selectedDate}T${selectedTime}`
    const startTs = Math.floor(new Date(localDateTimeStr).getTime() / 1000)
    loadPlaybackData(startTs)
  }

  const handleTimeUpdate = () => {
    const video = videoRef.current
    if (!video || segments.length === 0 || isDragging) return
    const absTs = getAbsoluteTsFromVideoTime(video.currentTime, segments, rangeStartTs, currentStreamStartTs)
    setCurrentAbsoluteTs(absTs)
  }

  const seekToTimestamp = (targetTs: number) => {
    if (!streamId) return
    const endTs = rangeStartTs + 3600
    const url = `/api/playback/${encodeURIComponent(streamId)}/stream.mp4?start_ts=${targetTs}&end_ts=${endTs}`
    setStreamUrl(url)
    setCurrentStreamStartTs(targetTs)
    setTimeout(() => {
      if (videoRef.current) {
        videoRef.current.load()
      }
    }, 50)
  }

  const handleMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    setIsDragging(true)
    handleSeekFromEvent(e)
  }

  const handleSeekFromEvent = (e: React.MouseEvent<HTMLDivElement> | MouseEvent) => {
    const timeline = timelineRef.current
    if (!timeline) return
    const rect = timeline.getBoundingClientRect()
    const clientX = 'clientX' in e ? e.clientX : (e as MouseEvent).clientX
    const clickX = Math.max(0, Math.min(clientX - rect.left, rect.width))
    const percentage = clickX / rect.width
    const clickedTs = rangeStartTs + percentage * 3600
    setCurrentAbsoluteTs(clickedTs)
  }

  useEffect(() => {
    if (!isDragging) return

    const handleMouseMove = (e: MouseEvent) => {
      handleSeekFromEvent(e)
    }

    const handleMouseUp = () => {
      setIsDragging(false)
      seekToTimestamp(currentAbsoluteTs)
    }

    window.addEventListener('mousemove', handleMouseMove)
    window.addEventListener('mouseup', handleMouseUp)

    return () => {
      window.removeEventListener('mousemove', handleMouseMove)
      window.removeEventListener('mouseup', handleMouseUp)
    }
  }, [isDragging, currentAbsoluteTs])

  function formatTimeLabel(ts: number) {
    if (!ts) return ''
    return new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  }

  function getAbsoluteTsFromVideoTime(videoTime: number, segs: any[], startTs: number, streamStartTs: number): number {
    const startIndex = segs.findIndex(seg => seg.end_ts >= streamStartTs)
    if (startIndex === -1) {
      return (streamStartTs || startTs) + videoTime
    }

    let remaining = videoTime
    for (let i = startIndex; i < segs.length; i++) {
      const seg = segs[i]
      const duration = seg.end_ts - seg.start_ts
      if (remaining <= duration) {
        return seg.start_ts + remaining
      }
      remaining -= duration
    }
    if (segs.length > 0) {
      return segs[segs.length - 1].end_ts
    }
    return (streamStartTs || startTs) + videoTime
  }

  return (
    <section className="content" id="playback">
      <div className="panelHead">
        <div>
          <div className="eyebrow">Seamless Continuous Playback</div>
          <h2 className="panelTitle">{cameraName ?? 'Select a Camera'}</h2>
          <div className="panelSub">
            {streamId ? `Stream ID: ${streamId}` : 'Choose a camera feed to start'}
          </div>
        </div>

        {/* Searchable Camera Selector */}
        <div className="dropdownContainer" ref={dropdownRef}>
          <button
            type="button"
            className="dropdownTrigger"
            onClick={() => setDropdownOpen(!dropdownOpen)}
            style={{ minWidth: '220px' }}
          >
            <span>{cameraName ?? 'Select Camera…'}</span>
            <ChevronDown size={14} style={{ opacity: 0.7 }} />
          </button>

          {dropdownOpen && (
            <div className="dropdownMenu" style={{ right: 0, left: 'auto', width: '280px' }}>
              <div className="dropdownSearchWrapper">
                <input
                  type="text"
                  className="dropdownSearchInput"
                  placeholder="Search cameras..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  autoFocus
                />
              </div>
              <div className="dropdownList">
                {filteredCameras.length > 0 ? (
                  filteredCameras.map((cam) => (
                    <div
                      key={cam.stream_id}
                      className={`dropdownOption ${streamId === cam.stream_id ? 'selected' : ''}`}
                      onClick={() => {
                        onSelectCamera(cam)
                        setDropdownOpen(false)
                        setSearchQuery('')
                      }}
                    >
                      <div style={{ display: 'flex', flexDirection: 'column' }}>
                        <span style={{ fontWeight: 600 }}>{cam.name}</span>
                        <span style={{ fontSize: '0.72rem', opacity: 0.6 }}>{cam.stream_id} ({cam.stream_type})</span>
                      </div>
                    </div>
                  ))
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

      {streamId ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* Stream Summary Card */}
          {summary && summary.count > 0 && (
            <div className="summaryCard">
              <div className="summaryCardTitle">
                <Film size={14} style={{ color: '#60a5fa' }} /> Stream Recording Coverage & Stats
              </div>
              <div className="summaryMetricGrid">
                <div className="summaryMetricCell">
                  <div className="summaryMetricLabel">Total Indexed Segments</div>
                  <div className="summaryMetricValue">
                    {summary.count} segments ({Math.floor(summary.count)} mins)
                  </div>
                </div>
                <div className="summaryMetricCell">
                  <div className="summaryMetricLabel">Recording Start Time</div>
                  <div className="summaryMetricValue">
                    {summary.min_start_ts ? new Date(summary.min_start_ts * 1000).toLocaleString() : 'N/A'}
                  </div>
                </div>
                <div className="summaryMetricCell">
                  <div className="summaryMetricLabel">Recording End Time</div>
                  <div className="summaryMetricValue">
                    {summary.max_end_ts ? new Date(summary.max_end_ts * 1000).toLocaleString() : 'N/A'}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Minimal Controls Bar */}
          <div className="controlsBar" style={{ margin: 0, padding: '14px 20px' }}>
            {availableDates.length > 0 ? (
              <div className="controlGroup" style={{ flexWrap: 'wrap', gap: '14px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span className="controlLabel" style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <Calendar size={14} /> Date:
                  </span>
                  <select
                    value={selectedDate}
                    onChange={(e) => setSelectedDate(e.target.value)}
                    style={{
                      padding: '8px 12px',
                      borderRadius: '12px',
                      border: '1px solid rgba(148,163,184,0.16)',
                      background: 'rgba(2,6,23,0.5)',
                      color: '#fff',
                      fontSize: '0.9rem',
                      outline: 'none',
                      cursor: 'pointer'
                    }}
                  >
                    {availableDates.map((d) => {
                      const dateObj = new Date(d)
                      const formatted = dateObj.toLocaleDateString(undefined, {
                        month: 'short',
                        day: 'numeric',
                        year: 'numeric'
                      })
                      return (
                        <option key={d} value={d}>
                          {formatted}
                        </option>
                      )
                    })}
                  </select>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span className="controlLabel">Time:</span>
                  <input
                    type="time"
                    value={selectedTime}
                    onChange={(e) => setSelectedTime(e.target.value)}
                    style={{
                      padding: '8px 12px',
                      borderRadius: '12px',
                      border: '1px solid rgba(148,163,184,0.16)',
                      background: 'rgba(2,6,23,0.5)',
                      color: '#fff',
                      fontSize: '0.9rem',
                      outline: 'none'
                    }}
                  />
                </div>

                <button
                  className="primaryBtn"
                  onClick={handleLoadStream}
                  disabled={loading}
                  style={{ borderRadius: '12px', padding: '9px 18px', fontSize: '0.86rem' }}
                >
                  {loading ? <Loader2 className="spin" size={14} /> : 'Play Continuous Video'}
                </button>
              </div>
            ) : (
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#94a3b8', fontSize: '0.9rem' }}>
                <AlertCircle size={16} />
                No recordings indexed yet for this camera.
              </div>
            )}
          </div>

          {/* Continuous Player Viewport */}
          {streamUrl ? (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '18px', maxWidth: '960px', margin: '0 auto', width: '100%' }}>
              <div className="playerShell" style={{ padding: '14px' }}>
                <div className="playerHeader" style={{ padding: '0 0 10px' }}>
                  <div>
                    <span className="eyebrow">Continuous Playback Timeline</span>
                    <h3 className="panelTitle" style={{ fontSize: '1.05rem', margin: '4px 0 0' }}>
                      Streaming from: {new Date(`${selectedDate}T${selectedTime}`).toLocaleString()}
                    </h3>
                  </div>
                  <div className="playerChips">
                    <span className="chip chipLive" style={{ background: 'rgba(59,130,246,0.15)', color: '#60a5fa', borderColor: 'rgba(96,165,250,0.2)' }}>
                      <Film size={12} /> Continuous Mux
                    </span>
                  </div>
                </div>

                <div className="playerViewport" style={{ position: 'relative', overflow: 'hidden', borderRadius: '20px', marginBottom: '14px' }}>
                  <video
                    ref={videoRef}
                    className="videoEl"
                    src={streamUrl}
                    controls
                    autoPlay
                    playsInline
                    onTimeUpdate={handleTimeUpdate}
                    style={{ width: '100%', height: '100%', objectFit: 'contain' }}
                  >
                    Your browser does not support the video tag.
                  </video>
                </div>

                {/* Timeline scrubber bar */}
                <div style={{ padding: '8px 4px 14px' }}>
                  <div className="timelineTitle" style={{ fontSize: '0.82rem', fontWeight: 600, color: '#94a3b8', marginBottom: '8px', display: 'flex', justifyContent: 'space-between' }}>
                    <span>Linear Scrubber Timeline (1 Hour)</span>
                    <span style={{ color: '#60a5fa' }}>Current: {formatTimeLabel(currentAbsoluteTs)}</span>
                  </div>
                  
                  <div
                    ref={timelineRef}
                    className="timelineBar"
                    onMouseDown={handleMouseDown}
                    style={{
                      height: '24px',
                      background: '#1e293b',
                      borderRadius: '8px',
                      position: 'relative',
                      cursor: 'ew-resize',
                      border: '1px solid rgba(148, 163, 184, 0.12)',
                      overflow: 'hidden'
                    }}
                  >
                    {/* Render recording segments */}
                    {segments.map((seg, idx) => {
                      const leftPercent = ((seg.start_ts - rangeStartTs) / 3600) * 100
                      const widthPercent = ((seg.end_ts - seg.start_ts) / 3600) * 100
                      return (
                        <div
                          key={idx}
                          className="timelineSegment"
                          style={{
                            position: 'absolute',
                            left: `${Math.max(0, Math.min(100, leftPercent))}%`,
                            width: `${Math.max(0, Math.min(100, widthPercent))}%`,
                            height: '100%',
                            background: 'linear-gradient(180deg, #10b981, #059669)',
                            opacity: 0.85
                          }}
                        />
                      )
                    })}

                    {/* Playhead marker */}
                    <div
                      className="timelinePlayhead"
                      style={{
                        position: 'absolute',
                        left: `${Math.max(0, Math.min(100, ((currentAbsoluteTs - rangeStartTs) / 3600) * 100))}%`,
                        width: '3px',
                        height: '100%',
                        background: '#ef4444',
                        boxShadow: '0 0 8px #ef4444',
                        top: 0,
                        pointerEvents: 'none',
                        zIndex: 5
                      }}
                    />
                  </div>

                  {/* Timeline labels */}
                  <div className="timelineLabels" style={{ display: 'flex', justifyContent: 'space-between', marginTop: '6px', fontSize: '0.75rem', color: '#94a3b8', fontWeight: 600 }}>
                    <span>{formatTimeLabel(rangeStartTs)}</span>
                    <span>{formatTimeLabel(rangeStartTs + 1800)}</span>
                    <span>{formatTimeLabel(rangeStartTs + 3600)}</span>
                  </div>
                </div>

                <div className="playerFooter" style={{ marginTop: '12px' }}>
                  <AlertCircle size={14} />
                  <span>The timeline above highlights available recorded segments in green. Drag or click the timeline to seek instantly.</span>
                </div>
              </div>
            </div>
          ) : (
            hasSearched && (
              <div className="emptyState" style={{ padding: '40px 20px' }}>
                <FileVideo size={42} style={{ color: '#64748b' }} />
                <h3 style={{ marginTop: '12px' }}>No recordings found</h3>
                <p style={{ marginTop: '6px' }}>Try selecting another date or time.</p>
              </div>
            )
          )}
        </div>
      ) : (
        <div className="emptyState" style={{ padding: '40px 20px' }}>
          <FileVideo size={42} style={{ color: '#64748b' }} />
          <h3 style={{ marginTop: '12px' }}>No camera selected</h3>
          <p style={{ marginTop: '6px' }}>Go to the Dashboard tab to select a camera to load recorded video history.</p>
        </div>
      )}
    </section>
  )
}
