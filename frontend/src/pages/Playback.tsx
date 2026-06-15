import React, { useState, useEffect, useRef, useMemo } from 'react'
import { Calendar, Film, Loader2, AlertCircle, FileVideo, ChevronDown, Clock, Activity } from 'lucide-react'
import type { Camera, RecordingSegment } from '../types'

type Props = {
  streamId?: string
  cameraName?: string
  cameras: Camera[]
  onSelectCamera: (camera: Camera) => void
}

type TimelinePayload = {
  segments: { start_ts: number; end_ts: number; duration: number }[]
  gaps: { start_ts: number; end_ts: number; duration: number }[]
  coverage_percent: number
  recorded_duration: number
  gap_duration: number
  segment_count: number
  first_recording_ts: number | null
  last_recording_ts: number | null
}

export function Playback({ streamId, cameraName, cameras, onSelectCamera }: Props) {
  // Available dates loaded from API
  const [availableDates, setAvailableDates] = useState<string[]>([])
  const [selectedDate, setSelectedDate] = useState('')
  const [selectedTime, setSelectedTime] = useState('00:00')
  const [loading, setLoading] = useState(false)
  const [hasSearched, setHasSearched] = useState(false)

  // Daily Timeline data
  const [timeline, setTimeline] = useState<TimelinePayload | null>(null)
  const [rawSegments, setRawSegments] = useState<RecordingSegment[]>([])

  // Playback state
  const [currentSegment, setCurrentSegment] = useState<RecordingSegment | null>(null)
  const [currentAbsoluteTs, setCurrentAbsoluteTs] = useState<number>(0)
  const [isDragging, setIsDragging] = useState(false)
  const [zoomLevel, setZoomLevel] = useState<'24h' | '6h' | '1h'>('24h')
  const [playbackSpeed, setPlaybackSpeed] = useState<number>(1.0)
  const [videoSrc, setVideoSrc] = useState<string>('')
  const [isPaused, setIsPaused] = useState(true)

  // Interactive Hover tooltip state
  const [hoverTime, setHoverTime] = useState<number | null>(null)
  const [hoverTooltip, setHoverTooltip] = useState<{ text: string; x: number } | null>(null)

  // Ref elements
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const timelineRef = useRef<HTMLDivElement | null>(null)
  const pendingSeekOffset = useRef<number | null>(null)

  // Camera search dropdown
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const dropdownRef = useRef<HTMLDivElement | null>(null)

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
      setTimeline(null)
      setRawSegments([])
      setVideoSrc('')
      setCurrentSegment(null)
      setHasSearched(false)
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
    setTimeline(null)
    setRawSegments([])
    setVideoSrc('')
    setCurrentSegment(null)
    setHasSearched(false)
  }, [streamId])

  // Get start/end timestamps of the selected day in local timezone
  const dayBoundaries = useMemo(() => {
    if (!selectedDate) return { start: 0, end: 0 }
    const dtStart = new Date(`${selectedDate}T00:00:00`)
    const startTs = Math.floor(dtStart.getTime() / 1000)
    return {
      start: startTs,
      end: startTs + 86400
    }
  }, [selectedDate])

  // Calculate the active window depending on current playhead & zoom resolution
  const timelineWindow = useMemo(() => {
    const { start: dayStart, end: dayEnd } = dayBoundaries
    if (!selectedDate) return { start: 0, end: 0, duration: 86400 }

    let duration = 86400
    if (zoomLevel === '6h') duration = 21600
    if (zoomLevel === '1h') duration = 3600

    if (zoomLevel === '24h') {
      return { start: dayStart, end: dayEnd, duration }
    }

    // Center the window on the current playhead
    const refTs = currentAbsoluteTs || dayStart
    let wStart = refTs - duration / 2
    let wEnd = refTs + duration / 2

    if (wStart < dayStart) {
      wStart = dayStart
      wEnd = dayStart + duration
    }
    if (wEnd > dayEnd) {
      wEnd = dayEnd
      wStart = dayEnd - duration
    }

    return { start: wStart, end: wEnd, duration }
  }, [zoomLevel, currentAbsoluteTs, dayBoundaries, selectedDate])

  // Fetch timeline segments and coverage statistics
  async function loadTimelineData(targetTsToPlay?: number) {
    if (!streamId || !selectedDate) return
    setLoading(true)
    try {
      // 1. Fetch raw segments for matching (so we have file paths)
      const rawRes = await fetch(`/api/playback/${encodeURIComponent(streamId)}?start_ts=${dayBoundaries.start}&end_ts=${dayBoundaries.end}`)
      let rawSegs: RecordingSegment[] = []
      if (rawRes.ok) {
        rawSegs = await rawRes.json()
        setRawSegments(rawSegs)
      }

      // 2. Fetch timeline coverage metrics
      const timelineRes = await fetch(`/api/playback/${encodeURIComponent(streamId)}/timeline?date=${selectedDate}`)
      if (timelineRes.ok) {
        const payload: TimelinePayload = await timelineRes.json()
        setTimeline(payload)
        setHasSearched(true)

        // 3. Initiate playback if requested
        if (targetTsToPlay !== undefined) {
          playSegmentAtTimestamp(targetTsToPlay, rawSegs)
        } else {
          // Play from beginning of recorded footage
          if (payload.first_recording_ts) {
            playSegmentAtTimestamp(payload.first_recording_ts, rawSegs)
          } else {
            playSegmentAtTimestamp(dayBoundaries.start, rawSegs)
          }
        }
      }
    } catch (e) {
      console.error('Failed to load timeline:', e)
    } finally {
      setLoading(false)
    }
  }

  // Play a specific segment matching a timestamp
  function playSegmentAtTimestamp(ts: number, segList: RecordingSegment[]) {
    // Find segment covering this timestamp
    let match = segList.find((s) => s.start_ts <= ts && ts <= s.end_ts)
    
    if (match) {
      const offset = ts - match.start_ts
      pendingSeekOffset.current = offset
      setCurrentSegment(match)
      setCurrentAbsoluteTs(ts)
      setVideoSrc(`/api/recordings/file?path=${encodeURIComponent(match.file_path)}`)
      setTimeout(() => {
        if (videoRef.current) {
          videoRef.current.load()
        }
      }, 50)
    } else {
      // Find the next closest segment after this timestamp
      const nextSeg = segList
        .filter((s) => s.start_ts >= ts)
        .sort((a, b) => a.start_ts - b.start_ts)[0]

      if (nextSeg) {
        pendingSeekOffset.current = 0
        setCurrentSegment(nextSeg)
        setCurrentAbsoluteTs(nextSeg.start_ts)
        setVideoSrc(`/api/recordings/file?path=${encodeURIComponent(nextSeg.file_path)}`)
        setTimeout(() => {
          if (videoRef.current) {
            videoRef.current.load()
          }
        }, 50)
      } else {
        // No segments found after this timestamp
        setVideoSrc('')
        setCurrentSegment(null)
        setCurrentAbsoluteTs(ts)
      }
    }
  }

  function handleLoadPlayback() {
    if (!selectedDate || !selectedTime) return
    const localDateTimeStr = `${selectedDate}T${selectedTime}`
    const startTs = Math.floor(new Date(localDateTimeStr).getTime() / 1000)
    loadTimelineData(startTs)
  }

  // Handle Video Time updates (sync playhead)
  const handleTimeUpdate = () => {
    const video = videoRef.current
    if (!video || !currentSegment || isDragging) return
    const currentAbs = currentSegment.start_ts + video.currentTime
    setCurrentAbsoluteTs(currentAbs)
  }

  // Handle Segment transitions when the current file ends
  const handleVideoEnded = () => {
    if (!currentSegment || rawSegments.length === 0) return

    // Find the next segment in chronological order
    const nextSeg = rawSegments
      .filter((s) => s.start_ts >= currentSegment.end_ts)
      .sort((a, b) => a.start_ts - b.start_ts)[0]

    if (nextSeg) {
      console.log(`[playback] Transitioning to next segment: ${nextSeg.file_path}`)
      pendingSeekOffset.current = 0
      setCurrentSegment(nextSeg)
      setCurrentAbsoluteTs(nextSeg.start_ts)
      setVideoSrc(`/api/recordings/file?path=${encodeURIComponent(nextSeg.file_path)}`)
      setTimeout(() => {
        if (videoRef.current) {
          videoRef.current.load()
          videoRef.current.play().catch(() => {})
        }
      }, 50)
    } else {
      console.log('[playback] End of recorded timeline reached')
      setIsPaused(true)
    }
  }

  // Handles metadata loading (restores seek offsets)
  const handleLoadedMetadata = () => {
    const video = videoRef.current
    if (!video) return
    
    // Apply speed settings
    video.playbackRate = playbackSpeed

    if (pendingSeekOffset.current !== null) {
      video.currentTime = pendingSeekOffset.current
      pendingSeekOffset.current = null
    }

    if (!isPaused) {
      video.play().catch(() => {})
    }
  }

  // Dynamic seeking triggered by timeline clicks or drags
  const seekToTimestamp = (targetTs: number) => {
    playSegmentAtTimestamp(targetTs, rawSegments)
  }

  const handleTimelineInteraction = (e: React.MouseEvent<HTMLDivElement> | MouseEvent) => {
    const timeline = timelineRef.current
    if (!timeline) return
    const rect = timeline.getBoundingClientRect()
    const clientX = 'clientX' in e ? e.clientX : (e as MouseEvent).clientX
    const clickX = Math.max(0, Math.min(clientX - rect.left, rect.width))
    const percentage = clickX / rect.width
    const clickedTs = timelineWindow.start + percentage * timelineWindow.duration
    return clickedTs
  }

  const handleMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    setIsDragging(true)
    const ts = handleTimelineInteraction(e)
    if (ts !== undefined) {
      setCurrentAbsoluteTs(ts)
    }
  }

  useEffect(() => {
    if (!isDragging) return

    const handleMouseMove = (e: MouseEvent) => {
      const ts = handleTimelineInteraction(e)
      if (ts !== undefined) {
        setCurrentAbsoluteTs(ts)
      }
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
  }, [isDragging, currentAbsoluteTs, rawSegments])

  // Mouse hover event (updates tooltip)
  const handleMouseMoveTimeline = (e: React.MouseEvent<HTMLDivElement>) => {
    const timeline = timelineRef.current
    if (!timeline || rawSegments.length === 0) return
    const rect = timeline.getBoundingClientRect()
    const hoverX = Math.max(0, Math.min(e.clientX - rect.left, rect.width))
    const percentage = hoverX / rect.width
    const ts = timelineWindow.start + percentage * timelineWindow.duration
    setHoverTime(ts)

    // Check if hover falls in a segment
    const hoverSeg = rawSegments.find((s) => s.start_ts <= ts && ts <= s.end_ts)
    let text = `${new Date(ts * 1000).toLocaleTimeString()}`
    if (hoverSeg) {
      const dur = Math.round(hoverSeg.end_ts - hoverSeg.start_ts)
      text += ` [Recorded - Duration: ${dur}s]`
    } else {
      text += ' [Gap - No video]'
    }

    setHoverTooltip({ text, x: hoverX })
  }

  const handleMouseLeaveTimeline = () => {
    setHoverTime(null)
    setHoverTooltip(null)
  }

  // Format Unix Timestamp into HH:MM:SS
  function formatTimeLabel(ts: number) {
    if (!ts) return '00:00:00'
    const dateObj = new Date(ts * 1000)
    return dateObj.toLocaleTimeString([], { hour12: false })
  }

  // Generate tick markers dynamically for visual rulers
  const rulerTicks = useMemo(() => {
    const ticks = []
    const count = 12 // Number of major indicators on the timeline ruler
    for (let i = 0; i <= count; i++) {
      const ts = timelineWindow.start + (i / count) * timelineWindow.duration
      ticks.push({
        label: new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false }),
        positionPercent: (i / count) * 100
      })
    }
    return ticks
  }, [timelineWindow])

  // Speed adjustments
  const handleSpeedChange = (rate: number) => {
    setPlaybackSpeed(rate)
    if (videoRef.current) {
      videoRef.current.playbackRate = rate
    }
  }

  // Format durations into human-readable hours and minutes
  function formatDuration(sec: number) {
    const hrs = Math.floor(sec / 3600)
    const mins = Math.floor((sec % 3600) / 60)
    return `${hrs}h ${mins}m`
  }

  return (
    <section className="content" id="playback">
      <div className="panelHead">
        <div>
          <div className="eyebrow">Enterprise Playback Engine</div>
          <h2 className="panelTitle">{cameraName ?? 'Select a Camera'}</h2>
          <div className="panelSub">
            {streamId ? `Stream ID: ${streamId}` : 'Select a camera feed to open visual logs'}
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
            <div className="dropdownMenu" style={{ right: 0, left: 'auto', width: '280px', zIndex: 100 }}>
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
          
          {/* Timeline KPI Density Dashboard Cards */}
          {timeline && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '14px' }}>
              <div className="summaryMetricCell" style={{ background: '#0f172a', padding: '14px', borderRadius: '14px', border: '1px solid rgba(148,163,184,0.1)' }}>
                <div style={{ fontSize: '0.75rem', color: '#94a3b8', fontWeight: 600 }}>Recording Coverage</div>
                <div style={{ fontSize: '1.25rem', fontWeight: 700, color: '#10b981', marginTop: '4px' }}>{timeline.coverage_percent}%</div>
              </div>
              <div className="summaryMetricCell" style={{ background: '#0f172a', padding: '14px', borderRadius: '14px', border: '1px solid rgba(148,163,184,0.1)' }}>
                <div style={{ fontSize: '0.75rem', color: '#94a3b8', fontWeight: 600 }}>Recorded Time</div>
                <div style={{ fontSize: '1.25rem', fontWeight: 700, color: '#60a5fa', marginTop: '4px' }}>{formatDuration(timeline.recorded_duration)}</div>
              </div>
              <div className="summaryMetricCell" style={{ background: '#0f172a', padding: '14px', borderRadius: '14px', border: '1px solid rgba(148,163,184,0.1)' }}>
                <div style={{ fontSize: '0.75rem', color: '#94a3b8', fontWeight: 600 }}>Gaps Count</div>
                <div style={{ fontSize: '1.25rem', fontWeight: 700, color: '#f59e0b', marginTop: '4px' }}>{timeline.gaps.length} gaps</div>
              </div>
              <div className="summaryMetricCell" style={{ background: '#0f172a', padding: '14px', borderRadius: '14px', border: '1px solid rgba(148,163,184,0.1)' }}>
                <div style={{ fontSize: '0.75rem', color: '#94a3b8', fontWeight: 600 }}>Total Chunks</div>
                <div style={{ fontSize: '1.25rem', fontWeight: 700, color: '#cbd5e1', marginTop: '4px' }}>{timeline.segment_count} files</div>
              </div>
              <div className="summaryMetricCell" style={{ background: '#0f172a', padding: '14px', borderRadius: '14px', border: '1px solid rgba(148,163,184,0.1)' }}>
                <div style={{ fontSize: '0.75rem', color: '#94a3b8', fontWeight: 600 }}>First Video Log</div>
                <div style={{ fontSize: '1rem', fontWeight: 700, color: '#94a3b8', marginTop: '6px' }}>
                  {timeline.first_recording_ts ? new Date(timeline.first_recording_ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : 'N/A'}
                </div>
              </div>
              <div className="summaryMetricCell" style={{ background: '#0f172a', padding: '14px', borderRadius: '14px', border: '1px solid rgba(148,163,184,0.1)' }}>
                <div style={{ fontSize: '0.75rem', color: '#94a3b8', fontWeight: 600 }}>Last Video Log</div>
                <div style={{ fontSize: '1rem', fontWeight: 700, color: '#94a3b8', marginTop: '6px' }}>
                  {timeline.last_recording_ts ? new Date(timeline.last_recording_ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : 'N/A'}
                </div>
              </div>
            </div>
          )}

          {/* Controls Bar */}
          <div className="controlsBar" style={{ margin: 0, padding: '14px 20px' }}>
            {availableDates.length > 0 ? (
              <div className="controlGroup" style={{ flexWrap: 'wrap', gap: '14px', width: '100%', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '16px', flexWrap: 'wrap' }}>
                  
                  {/* Date selection dropdown */}
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

                  {/* Hour input */}
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
                    onClick={handleLoadPlayback}
                    disabled={loading}
                    style={{ borderRadius: '12px', padding: '9px 18px', fontSize: '0.86rem' }}
                  >
                    {loading ? <Loader2 className="spin" size={14} /> : 'Load Visual Logs'}
                  </button>
                </div>

                {/* Speed Controls */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                  {videoSrc && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span className="controlLabel">Play Speed:</span>
                      <div className="btnToggleGroup">
                        {[0.5, 1.0, 2.0, 4.0, 8.0].map((rate) => (
                          <button
                            key={rate}
                            className={`toggleBtn ${playbackSpeed === rate ? 'active' : ''}`}
                            onClick={() => handleSpeedChange(rate)}
                            style={{ padding: '4px 8px', fontSize: '0.78rem' }}
                          >
                            {rate}x
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#94a3b8', fontSize: '0.9rem' }}>
                <AlertCircle size={16} />
                No recordings indexed yet for this camera.
              </div>
            )}
          </div>

          {/* Continuous Player Viewport & Interactive Timeline */}
          {videoSrc ? (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '18px', maxWidth: '960px', margin: '0 auto', width: '100%' }}>
              <div className="playerShell" style={{ padding: '14px' }}>
                
                <div className="playerHeader" style={{ padding: '0 0 10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <span className="eyebrow">Enterprise Playback Viewer</span>
                    <h3 className="panelTitle" style={{ fontSize: '1.05rem', margin: '4px 0 0' }}>
                      Local File: {currentSegment ? currentSegment.file_path.split(/[\\/]/).pop() : ''}
                    </h3>
                  </div>
                  
                  {/* Zoom controls */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span className="controlLabel" style={{ fontSize: '0.78rem' }}>Timeline Span:</span>
                    <div className="btnToggleGroup">
                      {(['24h', '6h', '1h'] as const).map((z) => (
                        <button
                          key={z}
                          className={`toggleBtn ${zoomLevel === z ? 'active' : ''}`}
                          onClick={() => setZoomLevel(z)}
                          style={{ padding: '4px 10px', fontSize: '0.78rem' }}
                        >
                          {z.toUpperCase()}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>

                {/* HTML5 video element */}
                <div className="playerViewport" style={{ position: 'relative', overflow: 'hidden', borderRadius: '20px', marginBottom: '14px', background: '#020617' }}>
                  <video
                    ref={videoRef}
                    className="videoEl"
                    src={videoSrc}
                    controls
                    autoPlay
                    playsInline
                    onTimeUpdate={handleTimeUpdate}
                    onEnded={handleVideoEnded}
                    onLoadedMetadata={handleLoadedMetadata}
                    onPlay={() => setIsPaused(false)}
                    onPause={() => setIsPaused(true)}
                    style={{ width: '100%', height: '100%', objectFit: 'contain' }}
                  >
                    Your browser does not support the video tag.
                  </video>
                </div>

                {/* Visual Scrubber timeline */}
                <div style={{ padding: '8px 4px 14px', position: 'relative' }}>
                  
                  <div className="timelineTitle" style={{ fontSize: '0.82rem', fontWeight: 600, color: '#94a3b8', marginBottom: '12px', display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}><Clock size={12} /> Playback Time (Local Server Time)</span>
                    <span style={{ color: '#10b981', fontWeight: 700 }}>{formatTimeLabel(currentAbsoluteTs)}</span>
                  </div>
                  
                  {/* Outer container */}
                  <div style={{ position: 'relative' }}>
                    
                    {/* Hover Tooltip display */}
                    {hoverTooltip && (
                      <div
                        style={{
                          position: 'absolute',
                          bottom: '34px',
                          left: `${hoverTooltip.x}px`,
                          transform: 'translateX(-50%)',
                          background: 'rgba(15, 23, 42, 0.95)',
                          border: '1px solid rgba(148, 163, 184, 0.25)',
                          padding: '6px 12px',
                          borderRadius: '8px',
                          color: '#fff',
                          fontSize: '0.72rem',
                          whiteSpace: 'nowrap',
                          pointerEvents: 'none',
                          zIndex: 10,
                          boxShadow: '0 4px 12px rgba(0,0,0,0.5)'
                        }}
                      >
                        {hoverTooltip.text}
                      </div>
                    )}

                    {/* Timeline bar with segments */}
                    <div
                      ref={timelineRef}
                      className="timelineBar"
                      onMouseDown={handleMouseDown}
                      onMouseMove={handleMouseMoveTimeline}
                      onMouseLeave={handleMouseLeaveTimeline}
                      style={{
                        height: '28px',
                        background: '#090d16',
                        borderRadius: '10px',
                        position: 'relative',
                        cursor: 'pointer',
                        border: '1px solid rgba(148, 163, 184, 0.16)',
                        overflow: 'hidden',
                        boxShadow: 'inset 0 2px 4px rgba(0,0,0,0.8)'
                      }}
                    >
                      {/* Render recorded segments clamped to the current active zoom window */}
                      {rawSegments.map((seg, idx) => {
                        const start = Math.max(seg.start_ts, timelineWindow.start)
                        const end = Math.min(seg.end_ts, timelineWindow.end)
                        if (start >= end) return null

                        const leftPercent = ((start - timelineWindow.start) / timelineWindow.duration) * 100
                        const widthPercent = ((end - start) / timelineWindow.duration) * 100
                        return (
                          <div
                            key={idx}
                            className="timelineSegment"
                            style={{
                              position: 'absolute',
                              left: `${Math.max(0, Math.min(100, leftPercent))}%`,
                              width: `${Math.max(0.1, Math.min(100, widthPercent))}%`,
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
                          left: `${Math.max(0, Math.min(100, ((currentAbsoluteTs - timelineWindow.start) / timelineWindow.duration) * 100))}%`,
                          width: '4px',
                          height: '100%',
                          background: '#ef4444',
                          boxShadow: '0 0 10px #ef4444',
                          top: 0,
                          pointerEvents: 'none',
                          zIndex: 6
                        }}
                      />
                    </div>
                  </div>

                  {/* Timeline Ruler Tick marks */}
                  <div style={{ position: 'relative', height: '22px', marginTop: '8px' }}>
                    {rulerTicks.map((tick, i) => (
                      <div
                        key={i}
                        style={{
                          position: 'absolute',
                          left: `${tick.positionPercent}%`,
                          transform: 'translateX(-50%)',
                          display: 'flex',
                          flexDirection: 'column',
                          alignItems: 'center',
                          pointerEvents: 'none'
                        }}
                      >
                        <div style={{ width: '1px', height: '5px', background: 'rgba(148, 163, 184, 0.4)' }} />
                        <span style={{ fontSize: '0.68rem', color: '#64748b', fontWeight: 600, marginTop: '3px' }}>
                          {tick.label}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="playerFooter" style={{ marginTop: '24px', display: 'flex', alignItems: 'center', gap: '8px', color: '#94a3b8' }}>
                  <Activity size={14} style={{ color: '#10b981' }} />
                  <span style={{ fontSize: '0.8rem' }}>
                    Seeking performs sub-second direct range streaming. Playback automatically jumps over recorded gaps.
                  </span>
                </div>
              </div>
            </div>
          ) : (
            hasSearched && (
              <div className="emptyState" style={{ padding: '40px 20px', background: '#090d16', borderRadius: '20px', textAlign: 'center' }}>
                <FileVideo size={48} style={{ color: '#64748b', margin: '0 auto' }} />
                <h3 style={{ marginTop: '12px', color: '#fff' }}>No video logs found</h3>
                <p style={{ marginTop: '6px', color: '#94a3b8' }}>Try selecting another date or time from the picker.</p>
              </div>
            )
          )}
        </div>
      ) : (
        <div className="emptyState" style={{ padding: '40px 20px', background: '#090d16', borderRadius: '20px', textAlign: 'center' }}>
          <FileVideo size={48} style={{ color: '#64748b', margin: '0 auto' }} />
          <h3 style={{ marginTop: '12px', color: '#fff' }}>No camera selected</h3>
          <p style={{ marginTop: '6px', color: '#94a3b8' }}>Select a camera from the dropdown menu to inspect its video timeline.</p>
        </div>
      )}
    </section>
  )
}
