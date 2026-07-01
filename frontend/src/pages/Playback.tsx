import React, { useState, useEffect, useRef, useMemo } from 'react'
import { Calendar, Film, Loader2, AlertCircle, FileVideo, ChevronDown, Clock, Activity, Play, Pause, RotateCcw, RotateCw } from 'lucide-react'
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
  const [playbackRangeEnd, setPlaybackRangeEnd] = useState<number | null>(null)
  const [clipGroupSize, setClipGroupSize] = useState<number>(10) // default 10 min
  const [downloadStart, setDownloadStart] = useState('00:00')
  const [downloadEnd, setDownloadEnd] = useState('23:59')

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

  const timeFrames = useMemo(() => {
    if (!rawSegments || rawSegments.length === 0) return []
    
    // Step 1: Group segments into contiguous blocks (gap <= 5s)
    const contiguousBlocks: { start: number; end: number }[] = []
    let currentBlock: { start: number; end: number } | null = null
    
    const sorted = [...rawSegments].sort((a, b) => a.start_ts - b.start_ts)
    
    for (const seg of sorted) {
      if (!currentBlock) {
        currentBlock = { start: seg.start_ts, end: seg.end_ts }
      } else {
        if (seg.start_ts - currentBlock.end <= 5) {
          currentBlock.end = seg.end_ts
        } else {
          contiguousBlocks.push(currentBlock)
          currentBlock = { start: seg.start_ts, end: seg.end_ts }
        }
      }
    }
    if (currentBlock) {
      contiguousBlocks.push(currentBlock)
    }

    // Step 2: Slice contiguous blocks into chunks if clipGroupSize > 0
    const chunks: { start: number; end: number; label: string }[] = []
    
    for (const block of contiguousBlocks) {
      const blockStart = block.start
      const blockEnd = block.end
      const blockDuration = blockEnd - blockStart
      
      if (clipGroupSize <= 0) {
        // Full contiguous block
        const dur = Math.round(blockDuration / 60)
        chunks.push({
          start: blockStart,
          end: blockEnd,
          label: `${new Date(blockStart * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })} - ${new Date(blockEnd * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })} (${dur} min)`
        })
      } else {
        const chunkSizeSec = clipGroupSize * 60
        let chunkStart = blockStart
        
        while (chunkStart < blockEnd) {
          let chunkEnd = chunkStart + chunkSizeSec
          if (chunkEnd > blockEnd) {
            chunkEnd = blockEnd
          }
          
          const durSec = chunkEnd - chunkStart
          const dur = Math.ceil(durSec / 60)
          
          chunks.push({
            start: chunkStart,
            end: chunkEnd,
            label: `${new Date(chunkStart * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })} - ${new Date(chunkEnd * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })} (${dur} min)`
          })
          
          chunkStart = chunkEnd
        }
      }
    }
    
    return chunks
  }, [rawSegments, clipGroupSize])

  const trimOverlay = useMemo(() => {
    if (!selectedDate || !timelineWindow.start) return null
    try {
      const startParts = downloadStart.split(':')
      const endParts = downloadEnd.split(':')
      
      const startH = parseInt(startParts[0]) || 0
      const startM = parseInt(startParts[1]) || 0
      const startS = parseInt(startParts[2]) || 0
      
      const endH = parseInt(endParts[0]) || 0
      const endM = parseInt(endParts[1]) || 0
      const endS = parseInt(endParts[2]) || 0
      
      const startD = new Date(`${selectedDate}T00:00:00`)
      startD.setHours(startH, startM, startS)
      const startTs = Math.floor(startD.getTime() / 1000)
      
      const endD = new Date(`${selectedDate}T00:00:00`)
      endD.setHours(endH, endM, endS)
      const endTs = Math.floor(endD.getTime() / 1000)
      
      if (startTs >= endTs) return null
      
      const overlapStart = Math.max(startTs, timelineWindow.start)
      const overlapEnd = Math.min(endTs, timelineWindow.end)
      if (overlapStart >= overlapEnd) return null
      
      const leftPct = ((overlapStart - timelineWindow.start) / timelineWindow.duration) * 100
      const widthPct = ((overlapEnd - overlapStart) / timelineWindow.duration) * 100
      
      return { left: leftPct, width: widthPct }
    } catch {
      return null
    }
  }, [selectedDate, downloadStart, downloadEnd, timelineWindow])

  function formatToTimeInputWithSeconds(ts: number) {
    if (!ts) return '00:00:00'
    const d = new Date(ts * 1000)
    const hrs = String(d.getHours()).padStart(2, '0')
    const mins = String(d.getMinutes()).padStart(2, '0')
    const secs = String(d.getSeconds()).padStart(2, '0')
    return `${hrs}:${mins}:${secs}`
  }

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

  const handleDownload = () => {
    if (!streamId || !selectedDate) return
    
    const normaliseTimeStr = (str: string, defaultSecs: string) => {
      const parts = str.split(':')
      if (parts.length === 2) return `${str}:${defaultSecs}`
      if (parts.length === 1) return `${str}:00:${defaultSecs}`
      return str
    }
    
    const startIso = `${selectedDate}T${normaliseTimeStr(downloadStart, '00')}`
    const endIso = `${selectedDate}T${normaliseTimeStr(downloadEnd, '59')}`
    
    const url = `/api/recordings/download?stream_id=${encodeURIComponent(streamId)}&start_time=${encodeURIComponent(startIso)}&end_time=${encodeURIComponent(endIso)}`
    
    const a = document.createElement('a')
    a.href = url
    a.download = `${streamId}_${selectedDate}_${downloadStart.replace(/:/g, '')}_to_${downloadEnd.replace(/:/g, '')}.mp4`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
  }

  // Play a specific segment matching a timestamp
  function playSegmentAtTimestamp(ts: number, segList: RecordingSegment[]) {
    // Find segment covering this timestamp
    let match = segList.find((s) => s.start_ts <= ts && ts <= s.end_ts)
    
    if (match) {
      const offset = ts - match.start_ts
      
      // If we are already playing this segment, just seek directly without reloading!
      if (currentSegment && currentSegment.file_path === match.file_path && videoRef.current) {
        videoRef.current.currentTime = offset
        setCurrentAbsoluteTs(ts)
      } else {
        pendingSeekOffset.current = offset
        setCurrentSegment(match)
        setCurrentAbsoluteTs(ts)
        setVideoSrc(`/api/recordings/file?path=${encodeURIComponent(match.file_path)}`)
        setTimeout(() => {
          if (videoRef.current) {
            videoRef.current.load()
          }
        }, 50)
      }
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
    
    // Prevent race condition: check if the video element has loaded the current segment's source
    const expectedPath = encodeURIComponent(currentSegment.file_path)
    if (!video.src.includes(expectedPath)) {
      return
    }
    
    const currentAbs = currentSegment.start_ts + video.currentTime
    
    // Stop at playbackRangeEnd constraint if set
    if (playbackRangeEnd !== null && currentAbs >= playbackRangeEnd) {
      video.pause()
      setIsPaused(true)
      setPlaybackRangeEnd(null)
      const endOffset = playbackRangeEnd - currentSegment.start_ts
      if (endOffset >= 0 && endOffset <= video.duration) {
        video.currentTime = endOffset
      }
      setCurrentAbsoluteTs(playbackRangeEnd)
      return
    }
    
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

  const togglePlayPause = () => {
    const video = videoRef.current
    if (!video) return
    if (video.paused) {
      video.play().catch(() => {})
      setIsPaused(false)
    } else {
      video.pause()
      setIsPaused(true)
    }
  }

  const handleSeek = (seconds: number) => {
    const video = videoRef.current
    if (!video || !currentSegment) return
    const newTime = video.currentTime + seconds
    const segmentDuration = currentSegment.end_ts - currentSegment.start_ts
    if (newTime >= 0 && newTime <= segmentDuration) {
      video.currentTime = newTime
      setCurrentAbsoluteTs(currentSegment.start_ts + newTime)
    } else {
      const newAbsTs = currentAbsoluteTs + seconds
      seekToTimestamp(newAbsTs)
    }
  }

  const stateRef = useRef({ currentAbsoluteTs, currentSegment, rawSegments })
  useEffect(() => {
    stateRef.current = { currentAbsoluteTs, currentSegment, rawSegments }
  }, [currentAbsoluteTs, currentSegment, rawSegments])

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      const target = event.target as HTMLElement
      if (
        target &&
        (target.tagName === 'INPUT' ||
          target.tagName === 'SELECT' ||
          target.tagName === 'TEXTAREA' ||
          target.isContentEditable)
      ) {
        return
      }

      if (event.key === ' ') {
        event.preventDefault()
        togglePlayPause()
      } else if (event.key === 'ArrowLeft') {
        event.preventDefault()
        const video = videoRef.current
        if (!video || !stateRef.current.currentSegment) return
        const newTime = video.currentTime - 10
        if (newTime >= 0) {
          video.currentTime = newTime
          setCurrentAbsoluteTs(stateRef.current.currentSegment.start_ts + newTime)
        } else {
          const newAbsTs = stateRef.current.currentAbsoluteTs - 10
          playSegmentAtTimestamp(newAbsTs, stateRef.current.rawSegments)
        }
      } else if (event.key === 'ArrowRight') {
        event.preventDefault()
        const video = videoRef.current
        if (!video || !stateRef.current.currentSegment) return
        const segmentDuration = stateRef.current.currentSegment.end_ts - stateRef.current.currentSegment.start_ts
        const newTime = video.currentTime + 10
        if (newTime <= segmentDuration) {
          video.currentTime = newTime
          setCurrentAbsoluteTs(stateRef.current.currentSegment.start_ts + newTime)
        } else {
          const newAbsTs = stateRef.current.currentAbsoluteTs + 10
          playSegmentAtTimestamp(newAbsTs, stateRef.current.rawSegments)
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

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
      setPlaybackRangeEnd(null)
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
      const isRecovered = hoverSeg.file_path.includes('_recovered')
      text += ` [${isRecovered ? 'Recovered' : 'Recorded'} - Duration: ${dur}s]`
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
              <>
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

                  {timeFrames.length > 0 && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span className="controlLabel" style={{ fontSize: '0.86rem', color: '#94a3b8' }}>Interval:</span>
                      <select
                        value={clipGroupSize}
                        onChange={(e) => {
                          setClipGroupSize(parseInt(e.target.value))
                          setPlaybackRangeEnd(null)
                        }}
                        style={{
                          padding: '8px 12px',
                          borderRadius: '12px',
                          border: '1px solid rgba(148, 163, 184, 0.16)',
                          background: 'rgba(15, 23, 42, 0.8)',
                          color: '#fff',
                          fontSize: '0.86rem',
                          outline: 'none',
                          cursor: 'pointer'
                        }}
                      >
                        <option value="10">10 Min Chunks</option>
                        <option value="5">5 Min Chunks</option>
                        <option value="2">2 Min Chunks</option>
                        <option value="0">Contiguous Blocks</option>
                      </select>

                      <span className="controlLabel" style={{ fontSize: '0.86rem', color: '#94a3b8', marginLeft: '8px' }}>Jump to Clip:</span>
                      <select
                        onChange={(e) => {
                          const idx = parseInt(e.target.value)
                          if (!isNaN(idx)) {
                            const block = timeFrames[idx]
                            seekToTimestamp(block.start)
                            setPlaybackRangeEnd(block.end)
                            setIsPaused(false)
                            
                            const startStr = formatToTimeInputWithSeconds(block.start)
                            const endStr = formatToTimeInputWithSeconds(block.end)
                            setDownloadStart(startStr)
                            setDownloadEnd(endStr)

                            setTimeout(() => {
                              if (videoRef.current) {
                                videoRef.current.play().catch(() => {})
                              }
                            }, 100)
                          }
                        }}
                        style={{
                          padding: '8px 12px',
                          borderRadius: '12px',
                          border: '1px solid rgba(148, 163, 184, 0.16)',
                          background: 'rgba(15, 23, 42, 0.8)',
                          color: '#fff',
                          fontSize: '0.86rem',
                          outline: 'none',
                          cursor: 'pointer'
                        }}
                        defaultValue=""
                      >
                        <option value="" disabled>-- Select time range --</option>
                        {timeFrames.map((block, idx) => (
                          <option key={idx} value={idx}>
                            {block.label}
                          </option>
                        ))}
                      </select>
                    </div>
                  )}
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

              {/* Export / Download segment option */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '14px', flexWrap: 'wrap', marginTop: '12px', paddingTop: '12px', borderTop: '1px solid rgba(255, 255, 255, 0.06)', width: '100%' }}>
                <span className="controlLabel" style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#10b981', fontWeight: 600 }}>
                  <Film size={14} /> Export / Download Footage:
                </span>
                
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ fontSize: '0.8rem', color: '#94a3b8' }}>From:</span>
                  <input
                    type="time"
                    step="1"
                    value={downloadStart}
                    onChange={(e) => setDownloadStart(e.target.value)}
                    style={{
                      padding: '6px 10px',
                      borderRadius: '8px',
                      border: '1px solid rgba(148, 163, 184, 0.16)',
                      background: 'rgba(2,6,23,0.5)',
                      color: '#fff',
                      fontSize: '0.82rem',
                      outline: 'none'
                    }}
                  />
                  <button
                    className="secondaryBtn"
                    onClick={() => {
                      if (currentAbsoluteTs) {
                        setDownloadStart(formatToTimeInputWithSeconds(currentAbsoluteTs))
                      }
                    }}
                    style={{
                      borderRadius: '6px',
                      padding: '4px 8px',
                      fontSize: '0.74rem',
                      background: 'rgba(59, 130, 246, 0.15)',
                      color: '#60a5fa',
                      border: '1px solid rgba(59, 130, 246, 0.3)',
                      cursor: 'pointer'
                    }}
                  >
                    Set Start
                  </button>
                </div>
                
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ fontSize: '0.8rem', color: '#94a3b8' }}>To:</span>
                  <input
                    type="time"
                    step="1"
                    value={downloadEnd}
                    onChange={(e) => setDownloadEnd(e.target.value)}
                    style={{
                      padding: '6px 10px',
                      borderRadius: '8px',
                      border: '1px solid rgba(148, 163, 184, 0.16)',
                      background: 'rgba(2,6,23,0.5)',
                      color: '#fff',
                      fontSize: '0.82rem',
                      outline: 'none'
                    }}
                  />
                  <button
                    className="secondaryBtn"
                    onClick={() => {
                      if (currentAbsoluteTs) {
                        setDownloadEnd(formatToTimeInputWithSeconds(currentAbsoluteTs))
                      }
                    }}
                    style={{
                      borderRadius: '6px',
                      padding: '4px 8px',
                      fontSize: '0.74rem',
                      background: 'rgba(59, 130, 246, 0.15)',
                      color: '#60a5fa',
                      border: '1px solid rgba(59, 130, 246, 0.3)',
                      cursor: 'pointer'
                    }}
                  >
                    Set End
                  </button>
                </div>
                
                <button
                  className="primaryBtn"
                  onClick={handleDownload}
                  style={{
                    borderRadius: '8px',
                    padding: '7px 14px',
                    fontSize: '0.78rem',
                    background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
                    borderColor: 'rgba(16, 185, 129, 0.3)',
                    cursor: 'pointer'
                  }}
                >
                  Download Merged MP4
                </button>
              </div>
              </>
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

                {/* On-Screen Video Controls */}
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '16px',
                  marginBottom: '20px',
                  padding: '10px 20px',
                  background: 'rgba(15, 23, 42, 0.6)',
                  borderRadius: '16px',
                  border: '1px solid rgba(148, 163, 184, 0.08)'
                }}>
                  <button
                    onClick={() => handleSeek(-10)}
                    className="toggleBtn"
                    title="Rewind 10s (Left Arrow)"
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                      padding: '8px 16px',
                      borderRadius: '12px',
                      fontSize: '0.85rem',
                      fontWeight: 600,
                      cursor: 'pointer'
                    }}
                  >
                    <RotateCcw size={16} />
                    <span>-10s</span>
                  </button>

                  <button
                    onClick={togglePlayPause}
                    className="primaryBtn"
                    title="Play/Pause (Space)"
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      width: '42px',
                      height: '42px',
                      borderRadius: '50%',
                      padding: 0,
                      background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
                      borderColor: 'rgba(16, 185, 129, 0.3)',
                      cursor: 'pointer'
                    }}
                  >
                    {isPaused ? <Play size={20} fill="#fff" /> : <Pause size={20} fill="#fff" />}
                  </button>

                  <button
                    onClick={() => handleSeek(10)}
                    className="toggleBtn"
                    title="Forward 10s (Right Arrow)"
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                      padding: '8px 16px',
                      borderRadius: '12px',
                      fontSize: '0.85rem',
                      fontWeight: 600,
                      cursor: 'pointer'
                    }}
                  >
                    <span>+10s</span>
                    <RotateCw size={16} />
                  </button>
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
                        const isRecovered = seg.file_path.includes('_recovered')
                        return (
                          <div
                            key={idx}
                            className="timelineSegment"
                            style={{
                              position: 'absolute',
                              left: `${Math.max(0, Math.min(100, leftPercent))}%`,
                              width: `${Math.max(0.1, Math.min(100, widthPercent))}%`,
                              height: '100%',
                              background: isRecovered 
                                ? 'linear-gradient(180deg, #f59e0b, #d97706)' 
                                : 'linear-gradient(180deg, #10b981, #059669)',
                              opacity: 0.85
                            }}
                          />
                        )
                      })}

                      {/* Trim range visual highlight */}
                      {trimOverlay && (
                        <div
                          style={{
                            position: 'absolute',
                            left: `${trimOverlay.left}%`,
                            width: `${trimOverlay.width}%`,
                            height: '100%',
                            background: 'rgba(59, 130, 246, 0.25)',
                            borderLeft: '2px dashed #3b82f6',
                            borderRight: '2px dashed #3b82f6',
                            pointerEvents: 'none',
                            zIndex: 4
                          }}
                        />
                      )}
                      
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

                  {/* Timeline Legend */}
                  <div style={{ display: 'flex', gap: '16px', fontSize: '0.75rem', marginTop: '16px', justifyContent: 'flex-end', color: '#94a3b8' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <div style={{ width: '12px', height: '12px', borderRadius: '3px', background: 'linear-gradient(180deg, #10b981, #059669)' }} />
                      <span>Normal Recording</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <div style={{ width: '12px', height: '12px', borderRadius: '3px', background: 'linear-gradient(180deg, #f59e0b, #d97706)' }} />
                      <span>Recovered Footage</span>
                    </div>
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
