import React, { useState, useEffect, useRef } from 'react'
import { Video, Mic, MicOff, Wifi, WifiOff, Settings, AlertTriangle, CheckCircle2, Play, Square, RefreshCw, Radio, ExternalLink } from 'lucide-react'
import { Player } from '../components/Player'
import type { Camera } from '../types'

interface WebcamStreamProps {
  edgeCameras: Camera[]
  onRefresh: () => void
}

export function WebcamStream({ edgeCameras, onRefresh }: WebcamStreamProps) {
  // Device Selection States
  const [videoDevices, setVideoDevices] = useState<MediaDeviceInfo[]>([])
  const [audioDevices, setAudioDevices] = useState<MediaDeviceInfo[]>([])
  const [selectedVideoId, setSelectedVideoId] = useState<string>('')
  const [selectedAudioId, setSelectedAudioId] = useState<string>('')
  const [audioEnabled, setAudioEnabled] = useState<boolean>(true)
  const [videoEnabled, setVideoEnabled] = useState<boolean>(true)

  // Stream Target States
  const [streamId, setStreamId] = useState<string>('webcam_stream')
  const [cameraName, setCameraName] = useState<string>('Local Webcam')
  const [selectedTargetType, setSelectedTargetType] = useState<'existing' | 'custom'>('custom')
  const [isRegistering, setIsRegistering] = useState<boolean>(false)

  // Streaming state
  const [isStreaming, setIsStreaming] = useState<boolean>(false)
  const [status, setStatus] = useState<'inactive' | 'accessing' | 'connecting' | 'streaming' | 'error'>('inactive')
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [duration, setDuration] = useState<number>(0)
  
  // WebRTC Stats
  const [stats, setStats] = useState<{
    fps: number
    resolution: string
    bitrate: number
    rtt: number | null
    packetLoss: number
  }>({
    fps: 0,
    resolution: '—',
    bitrate: 0,
    rtt: null,
    packetLoss: 0
  })

  // Media references
  const localVideoRef = useRef<HTMLVideoElement | null>(null)
  const localStreamRef = useRef<MediaStream | null>(null)
  const pcRef = useRef<RTCPeerConnection | null>(null)
  const timerRef = useRef<number | null>(null)
  const statsRef = useRef<number | null>(null)
  const prevStatsRef = useRef<{ timestamp: number; bytesSent: number }>({ timestamp: 0, bytesSent: 0 })

  // Egress preview state
  const [showEgressPreview, setShowEgressPreview] = useState<boolean>(false)

  // Enumerate devices on mount
  useEffect(() => {
    async function getDevices() {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        if (window.isSecureContext === false) {
          setErrorMsg('Webcam access blocked: Browsers disable media capture on insecure remote origins (HTTP). Access via HTTPS or add ' + window.location.origin + ' to your browser\'s secure origin overrides (e.g. chrome://flags/#unsafely-treat-insecure-origin-as-secure).');
        } else {
          setErrorMsg('Media devices API is not supported or accessible on this browser/environment.');
        }
        return
      }

      try {
        // Request permissions first to get labels
        await navigator.mediaDevices.getUserMedia({ audio: true, video: true })
          .then(stream => {
            // Immediately stop tracks to free device
            stream.getTracks().forEach(track => track.stop())
          })
          .catch(err => {
            console.warn('Initial permission request failed:', err)
            if (err.name === 'NotAllowedError') {
              setErrorMsg('Camera and microphone permission was denied. Please grant permission in your browser settings.');
            } else if (err.name === 'NotFoundError') {
              setErrorMsg('No camera or microphone devices were found.');
            } else {
              setErrorMsg(`Media access permission error: ${err.message || err.name}`);
            }
          })

        const devices = await navigator.mediaDevices.enumerateDevices()
        const video = devices.filter(d => d.kind === 'videoinput')
        const audio = devices.filter(d => d.kind === 'audioinput')
        
        setVideoDevices(video)
        setAudioDevices(audio)

        if (video.length > 0) setSelectedVideoId(video[0].deviceId)
        if (audio.length > 0) setSelectedAudioId(audio[0].deviceId)
      } catch (err: any) {
        console.error('Failed to enumerate media devices:', err)
        setErrorMsg(`Could not access media devices: ${err.message || err.name}`);
      }
    }
    getDevices()
  }, [])

  // Manage Local Preview Stream
  useEffect(() => {
    if (isStreaming) return // Don't interrupt active streaming

    async function startPreview() {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        return
      }

      if (localStreamRef.current) {
        localStreamRef.current.getTracks().forEach(t => t.stop())
        localStreamRef.current = null
      }

      if (!videoEnabled && !audioEnabled) {
        if (localVideoRef.current) localVideoRef.current.srcObject = null
        return
      }

      try {
        const constraints: MediaStreamConstraints = {
          video: videoEnabled ? {
            deviceId: selectedVideoId ? { exact: selectedVideoId } : undefined,
            width: { ideal: 1280 },
            height: { ideal: 720 },
            frameRate: { ideal: 30 }
          } : false,
          audio: audioEnabled ? {
            deviceId: selectedAudioId ? { exact: selectedAudioId } : undefined,
            echoCancellation: true,
            noiseSuppression: true
          } : false
        }

        const stream = await navigator.mediaDevices.getUserMedia(constraints)
        localStreamRef.current = stream
        if (localVideoRef.current) {
          localVideoRef.current.srcObject = stream
        }
        setErrorMsg(null) // Clear any previous preview errors if successful
      } catch (err: any) {
        console.error('Failed to start local preview:', err)
        if (err.name === 'NotAllowedError') {
          setErrorMsg('Camera and microphone permission was denied. Please grant permission in your browser settings.');
        } else if (err.name === 'NotFoundError') {
          setErrorMsg('No camera or microphone devices were found matching selected constraints.');
        } else if (err.name === 'OverconstrainedError') {
          setErrorMsg('The selected camera resolution or constraints are not supported by the hardware.');
        } else {
          setErrorMsg(`Failed to start camera preview: ${err.message || err.name}`);
        }
      }
    }

    startPreview()

    return () => {
      if (localStreamRef.current && !isStreaming) {
        localStreamRef.current.getTracks().forEach(t => t.stop())
      }
    }
  }, [selectedVideoId, selectedAudioId, videoEnabled, audioEnabled, isStreaming])

  // Timer effect for active stream duration
  useEffect(() => {
    if (isStreaming) {
      setDuration(0)
      timerRef.current = window.setInterval(() => {
        setDuration(prev => prev + 1)
      }, 1000)
    } else {
      if (timerRef.current) {
        clearInterval(timerRef.current)
        timerRef.current = null
      }
      setDuration(0)
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [isStreaming])

  // Helper to format bytes
  const formatBitrate = (kbps: number) => {
    if (kbps < 1024) return `${kbps.toFixed(0)} kbps`
    return `${(kbps / 1024).toFixed(2)} Mbps`
  }

  // Helper to format duration
  const formatDuration = (seconds: number) => {
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
  }

  // Register camera locally helper
  const registerCameraIfNeeded = async (targetId: string, name: string) => {
    setIsRegistering(true)
    try {
      const res = await fetch(`/api/edge/register/${encodeURIComponent(targetId)}?name=${encodeURIComponent(name)}`, {
        method: 'POST'
      })
      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || 'Failed to auto-register camera')
      }
      console.log(`Auto-registered camera ${targetId} successfully`)
      onRefresh()
    } catch (err: any) {
      console.error(err)
      setErrorMsg(`Auto-registration failed: ${err.message}`)
    } finally {
      setIsRegistering(false)
    }
  }

  // WebRTC WHIP Push Implementation
  const startStreaming = async () => {
    setErrorMsg(null)
    setStatus('accessing')

    const targetStreamId = selectedTargetType === 'existing' ? streamId : streamId.trim()
    if (!targetStreamId) {
      setErrorMsg('Please specify a valid Stream ID')
      setStatus('error')
      return
    }

    // Auto-register custom camera if not present in edgeCameras list
    if (selectedTargetType === 'custom') {
      const isAlreadyRegistered = edgeCameras.some(c => c.stream_id === targetStreamId)
      if (!isAlreadyRegistered) {
        await registerCameraIfNeeded(targetStreamId, cameraName)
      }
    }

    try {
      // 1. Ensure we have the local tracks
      if (!localStreamRef.current) {
        throw new Error('Local camera/microphone stream is not initialized')
      }

      setStatus('connecting')

      // 2. Fetch ICE Servers
      const iceResp = await fetch('/api/webrtc/ice-servers')
      if (!iceResp.ok) throw new Error('Failed to retrieve ICE server configuration')
      const { iceServers } = await iceResp.json()

      // 3. Create RTCPeerConnection
      const pc = new RTCPeerConnection({ iceServers })
      pcRef.current = pc

      // Add local media tracks to Peer Connection
      localStreamRef.current.getTracks().forEach(track => {
        pc.addTrack(track, localStreamRef.current!)
      })

      // Get track information for stats panel
      let width = 0
      let height = 0
      let frameRate = 0
      const videoTrack = localStreamRef.current.getVideoTracks()[0]
      if (videoTrack) {
        const settings = videoTrack.getSettings()
        width = settings.width || 0
        height = settings.height || 0
        frameRate = settings.frameRate || 0
        setStats(prev => ({
          ...prev,
          resolution: width && height ? `${width}x${height}` : '—',
          fps: frameRate
        }))
      }

      // Handle ICE Connection State Changes
      pc.oniceconnectionstatechange = () => {
        console.log(`[WHIP] ICE State: ${pc.iceConnectionState}`)
        if (pc.iceConnectionState === 'connected') {
          setStatus('streaming')
          setIsStreaming(true)
        } else if (pc.iceConnectionState === 'failed' || pc.iceConnectionState === 'disconnected') {
          stopStreaming()
          setErrorMsg('WebRTC transmission interrupted. Connection lost.')
        }
      }

      // Create WebRTC SDP Offer
      const offer = await pc.createOffer()
      await pc.setLocalDescription(offer)

      // Wait for ICE candidate gathering (WHIP prefers fully bundled SDPs)
      await new Promise<void>((resolve) => {
        if (pc.iceGatheringState === 'complete') {
          resolve()
        } else {
          function checkState() {
            if (pc.iceGatheringState === 'complete') {
              pc.removeEventListener('icegatheringstatechange', checkState)
              resolve()
            }
          }
          pc.addEventListener('icegatheringstatechange', checkState)
          // Fallback timeout
          setTimeout(() => {
            pc.removeEventListener('icegatheringstatechange', checkState)
            resolve()
          }, 1500)
        }
      })

      // 4. Send WHIP POST SDP Offer
      const whipResp = await fetch(`/api/streams/${encodeURIComponent(targetStreamId)}/live/whip`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/sdp'
        },
        body: pc.localDescription?.sdp
      })

      if (!whipResp.ok) {
        const text = await whipResp.text()
        throw new Error(`Media server signaling failed: ${text || whipResp.statusText}`)
      }

      const answerSdp = await whipResp.text()
      await pc.setRemoteDescription(new RTCSessionDescription({
        type: 'answer',
        sdp: answerSdp
      }))

      // Register session URL for trickle candidates or termination
      const locationHeader = whipResp.headers.get('Location')
      if (locationHeader) {
        (pc as any).sessionUrl = locationHeader;
        
        // Trickle ICE support (Optional for WHIP but good to have)
        pc.onicecandidate = (event) => {
          if (event.candidate && pcRef.current === pc) {
            const candidateStr = event.candidate.candidate;
            const bodyContent = candidateStr.startsWith('a=') ? candidateStr : `a=${candidateStr}\r\n`;
            fetch(locationHeader, {
              method: 'PATCH',
              headers: { 'Content-Type': 'application/trickle-ice-sdpfrag' },
              body: bodyContent
            }).catch(e => console.error('[WHIP] Trickle candidate send failed:', e))
          }
        }
      }

      // If connection state immediately changes to connected or gathers fast
      if (pc.iceConnectionState === 'connected' || pc.iceConnectionState === 'completed') {
        setStatus('streaming')
        setIsStreaming(true)
      } else {
        // Wait for iceconnection state change, but assume connecting
        setStatus('connecting')
      }

      // Initialize Stats Gathering
      startStatsInterval()

    } catch (err: any) {
      console.error('[WHIP] Ingestion failed:', err)
      setErrorMsg(err.message || 'Failed to establish WebRTC WHIP link with MediaMTX')
      setStatus('error')
      stopStreaming()
    }
  }

  const stopStreaming = () => {
    stopStatsInterval()
    
    if (pcRef.current) {
      const sessionUrl = (pcRef.current as any).sessionUrl
      if (sessionUrl) {
        fetch(sessionUrl, { method: 'DELETE' }).catch(() => {})
      }
      pcRef.current.close()
      pcRef.current = null
    }

    if (localStreamRef.current) {
      localStreamRef.current.getTracks().forEach(t => t.stop())
      localStreamRef.current = null
    }

    setIsStreaming(false)
    setStatus('inactive')
    setStats({
      fps: 0,
      resolution: '—',
      bitrate: 0,
      rtt: null,
      packetLoss: 0
    })
    setShowEgressPreview(false)
  }

  // Outbound WebRTC Statistics
  const startStatsInterval = () => {
    stopStatsInterval()
    prevStatsRef.current = { timestamp: Date.now(), bytesSent: 0 }

    statsRef.current = window.setInterval(async () => {
      const pc = pcRef.current
      if (!pc || pc.iceConnectionState !== 'connected') return

      try {
        const rtcStats = await pc.getStats()
        let outboundStats: any = null
        let candidatePairStats: any = null

        rtcStats.forEach(report => {
          if (report.type === 'outbound-rtp' && report.mediaType === 'video') {
            outboundStats = report
          }
          if (report.type === 'candidate-pair' && report.state === 'succeeded') {
            candidatePairStats = report
          }
        })

        if (outboundStats) {
          const now = Date.now()
          const durationSec = (now - prevStatsRef.current.timestamp) / 1000
          const bytesSent = outboundStats.bytesSent || 0
          const bytesDelta = bytesSent - prevStatsRef.current.bytesSent

          // kbps
          const bitrate = durationSec > 0 ? (bytesDelta * 8) / (durationSec * 1000) : 0

          const rtt = candidatePairStats ? candidatePairStats.currentRoundTripTime * 1000 : null
          const packetsSent = outboundStats.packetsSent || 0
          const retransmittedPackets = outboundStats.retransmittedPacketsSent || 0
          const packetLoss = packetsSent > 0 ? retransmittedPackets / packetsSent : 0

          setStats(prev => ({
            ...prev,
            bitrate,
            rtt,
            packetLoss
          }))

          prevStatsRef.current = { timestamp: now, bytesSent }
        }
      } catch (e) {
        console.error('Error fetching WebRTC outbound stats:', e)
      }
    }, 1000)
  }

  const stopStatsInterval = () => {
    if (statsRef.current) {
      clearInterval(statsRef.current)
      statsRef.current = null
    }
  }

  return (
    <div className="webcamStreamPage" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '20px', height: '100%', overflowY: 'auto', color: '#e2e8f0' }}>
      
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2 style={{ fontSize: '1.25rem', fontWeight: 700, color: '#f8fafc', margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Radio size={22} style={{ color: '#ef4444', animation: isStreaming ? 'pulse 2s infinite' : 'none' }} />
            Webcam Edge Push Broadcast
          </h2>
          <span style={{ fontSize: '0.78rem', color: '#94a3b8' }}>
            Stream your local webcam feed into the VMS container using the WebRTC WHIP egress standard.
          </span>
        </div>
      </div>

      {/* Warning/Error Banner */}
      {errorMsg && (
        <div style={{ padding: '12px 16px', background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.2)', borderRadius: '12px', fontSize: '0.85rem', color: '#f87171', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <AlertTriangle size={16} />
          {errorMsg}
        </div>
      )}

      {/* Main Layout Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: '360px 1fr', gap: '24px' }}>
        
        {/* Settings Panel */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', padding: '20px', background: 'rgba(30, 41, 59, 0.3)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: '16px' }}>
          <h3 style={{ margin: 0, fontSize: '0.95rem', fontWeight: 700, color: '#f1f5f9', display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Settings size={16} /> Ingestion Settings
          </h3>

          {/* Device Selection */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div>
              <label style={{ fontSize: '0.75rem', color: '#94a3b8', display: 'block', marginBottom: '6px' }}>Video Source (Camera)</label>
              <select 
                value={selectedVideoId} 
                onChange={e => setSelectedVideoId(e.target.value)} 
                disabled={isStreaming || !videoEnabled}
                className="vms-select"
              >
                {videoDevices.map(d => (
                  <option key={d.deviceId} value={d.deviceId}>{d.label || `Camera ${d.deviceId.slice(0, 5)}`}</option>
                ))}
                {videoDevices.length === 0 && <option value="">No cameras found</option>}
              </select>
            </div>

            <div>
              <label style={{ fontSize: '0.75rem', color: '#94a3b8', display: 'block', marginBottom: '6px' }}>Audio Source (Microphone)</label>
              <select 
                value={selectedAudioId} 
                onChange={e => setSelectedAudioId(e.target.value)} 
                disabled={isStreaming || !audioEnabled}
                className="vms-select"
              >
                {audioDevices.map(d => (
                  <option key={d.deviceId} value={d.deviceId}>{d.label || `Mic ${d.deviceId.slice(0, 5)}`}</option>
                ))}
                {audioDevices.length === 0 && <option value="">No microhones found</option>}
              </select>
            </div>
            
            {/* Capture Toggles */}
            <div style={{ display: 'flex', gap: '16px', marginTop: '4px' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.8rem', color: '#cbd5e1', cursor: 'pointer' }}>
                <input 
                  type="checkbox" 
                  checked={videoEnabled} 
                  onChange={e => {
                    setVideoEnabled(e.target.checked)
                    if (!e.target.checked) setStats(prev => ({ ...prev, resolution: '—', fps: 0 }))
                  }} 
                  disabled={isStreaming} 
                />
                Capture Video
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.8rem', color: '#cbd5e1', cursor: 'pointer' }}>
                <input 
                  type="checkbox" 
                  checked={audioEnabled} 
                  onChange={e => setAudioEnabled(e.target.checked)} 
                  disabled={isStreaming} 
                />
                Capture Audio
              </label>
            </div>
          </div>

          <div style={{ height: '1px', background: 'rgba(255,255,255,0.06)' }} />

          {/* Ingestion Target Configuration */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div>
              <label style={{ fontSize: '0.75rem', color: '#94a3b8', display: 'block', marginBottom: '6px' }}>Target Stream Destination</label>
              <div style={{ display: 'flex', gap: '8px', marginBottom: '10px' }}>
                <button
                  type="button"
                  onClick={() => {
                    setSelectedTargetType('custom')
                    setStreamId('webcam_stream')
                  }}
                  disabled={isStreaming}
                  style={{
                    flex: 1, padding: '6px', fontSize: '0.75rem', borderRadius: '8px', cursor: 'pointer', border: '1px solid',
                    backgroundColor: selectedTargetType === 'custom' ? 'rgba(59,130,246,0.15)' : 'transparent',
                    borderColor: selectedTargetType === 'custom' ? '#3b82f6' : 'rgba(255,255,255,0.08)',
                    color: selectedTargetType === 'custom' ? '#60a5fa' : '#94a3b8'
                  }}
                >
                  Custom Stream ID
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setSelectedTargetType('existing')
                    if (edgeCameras.length > 0) setStreamId(edgeCameras[0].stream_id)
                  }}
                  disabled={isStreaming}
                  style={{
                    flex: 1, padding: '6px', fontSize: '0.75rem', borderRadius: '8px', cursor: 'pointer', border: '1px solid',
                    backgroundColor: selectedTargetType === 'existing' ? 'rgba(59,130,246,0.15)' : 'transparent',
                    borderColor: selectedTargetType === 'existing' ? '#3b82f6' : 'rgba(255,255,255,0.08)',
                    color: selectedTargetType === 'existing' ? '#60a5fa' : '#94a3b8'
                  }}
                >
                  Registered Edge
                </button>
              </div>
            </div>

            {selectedTargetType === 'existing' ? (
              <div>
                <label style={{ fontSize: '0.75rem', color: '#94a3b8', display: 'block', marginBottom: '6px' }}>Select Edge Camera</label>
                <select 
                  value={streamId} 
                  onChange={e => setStreamId(e.target.value)} 
                  disabled={isStreaming}
                  className="vms-select"
                >
                  {edgeCameras.map(c => (
                    <option key={c.id} value={c.stream_id}>{c.name} ({c.stream_id})</option>
                  ))}
                  {edgeCameras.length === 0 && <option value="">No registered edge cameras found</option>}
                </select>
              </div>
            ) : (
              <>
                <div>
                  <label style={{ fontSize: '0.75rem', color: '#94a3b8', display: 'block', marginBottom: '6px' }}>Stream ID (alphanumeric/slug)</label>
                  <input 
                    value={streamId} 
                    onChange={e => setStreamId(e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, ''))} 
                    disabled={isStreaming}
                    placeholder="e.g. office_webcam"
                    className="vms-input"
                  />
                </div>
                <div>
                  <label style={{ fontSize: '0.75rem', color: '#94a3b8', display: 'block', marginBottom: '6px' }}>Camera Display Name</label>
                  <input 
                    value={cameraName} 
                    onChange={e => setCameraName(e.target.value)} 
                    disabled={isStreaming}
                    placeholder="e.g. My Laptop Webcam"
                    className="vms-input"
                  />
                </div>
              </>
            )}
          </div>

          {/* Trigger Button */}
          <div style={{ marginTop: '10px' }}>
            {isStreaming ? (
              <button 
                onClick={stopStreaming}
                style={{
                  width: '100%', padding: '12px', background: 'linear-gradient(135deg, #ef4444 0%, #b91c1c 100%)',
                  border: 'none', borderRadius: '10px', color: '#fff', fontSize: '0.88rem', fontWeight: 700,
                  cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px'
                }}
              >
                <Square size={16} /> Stop Broadcast
              </button>
            ) : (
              <button 
                onClick={startStreaming}
                disabled={isRegistering || (!videoEnabled && !audioEnabled) || (selectedTargetType === 'existing' && edgeCameras.length === 0)}
                style={{
                  width: '100%', padding: '12px', 
                  background: isRegistering ? 'rgba(16, 185, 129, 0.4)' : 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
                  border: 'none', borderRadius: '10px', color: '#fff', fontSize: '0.88rem', fontWeight: 700,
                  cursor: isRegistering ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px'
                }}
              >
                <Play size={16} /> {isRegistering ? 'Registering...' : 'Start Broadcast'}
              </button>
            )}
          </div>
        </div>

        {/* Studio Workspace / Preview Panel */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          
          {/* Status Bar */}
          <div style={{ 
            padding: '12px 18px', 
            background: 'rgba(15, 23, 42, 0.45)', 
            border: '1px solid rgba(255, 255, 255, 0.05)', 
            borderRadius: '12px',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{
                width: '10px', height: '10px', borderRadius: '50%',
                backgroundColor: status === 'streaming' ? '#10b981' : status === 'connecting' ? '#f59e0b' : status === 'accessing' ? '#3b82f6' : '#64748b',
                boxShadow: status === 'streaming' ? '0 0 10px #10b981' : 'none',
                animation: status === 'streaming' || status === 'connecting' ? 'pulse 2s infinite' : 'none'
              }} />
              <span style={{ fontSize: '0.88rem', fontWeight: 600 }}>
                Status: {
                  status === 'streaming' ? 'Live Streaming' :
                  status === 'connecting' ? 'Connecting WHIP Session...' :
                  status === 'accessing' ? 'Accessing Media Capture Devices...' :
                  status === 'error' ? 'Failed' : 'Ready to Stream'
                }
              </span>
            </div>
            
            {isStreaming && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
                <span style={{ fontSize: '0.82rem', fontFamily: 'monospace', background: 'rgba(239, 68, 68, 0.15)', color: '#fca5a5', padding: '2px 8px', borderRadius: '6px', border: '1px solid rgba(239,68,68,0.2)' }}>
                  REC {formatDuration(duration)}
                </span>
              </div>
            )}
          </div>

          {/* Videos Grid */}
          <div style={{ display: 'grid', gridTemplateColumns: showEgressPreview ? '1fr 1fr' : '1fr', gap: '20px' }}>
            
            {/* Local Preview */}
            <div style={{ 
              background: '#090d16', 
              border: '1px solid rgba(255, 255, 255, 0.08)', 
              borderRadius: '16px',
              overflow: 'hidden',
              display: 'flex',
              flexDirection: 'column',
              aspectRatio: '16/9',
              position: 'relative'
            }}>
              <div style={{ 
                position: 'absolute', top: '12px', left: '12px', zIndex: 10,
                background: 'rgba(15, 23, 42, 0.75)', border: '1px solid rgba(255,255,255,0.1)',
                padding: '4px 10px', borderRadius: '8px', fontSize: '0.72rem', display: 'flex', alignItems: 'center', gap: '4px'
              }}>
                <Video size={12} /> Local Camera Ingest Preview
              </div>

              {!videoEnabled && (
                <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '12px', color: '#64748b' }}>
                  <WifiOff size={40} />
                  <span style={{ fontSize: '0.85rem' }}>Local video capture is disabled</span>
                </div>
              )}

              {videoEnabled && (
                <video 
                  ref={localVideoRef} 
                  autoPlay 
                  playsInline 
                  muted 
                  style={{ width: '100%', height: '100%', objectFit: 'contain', transform: 'scaleX(-1)' }} 
                />
              )}
            </div>

            {/* Server Return Preview */}
            {showEgressPreview && (
              <div style={{ 
                background: '#090d16', 
                border: '1px solid rgba(255, 255, 255, 0.08)', 
                borderRadius: '16px',
                overflow: 'hidden',
                display: 'flex',
                flexDirection: 'column',
                aspectRatio: '16/9',
                position: 'relative'
              }}>
                <div style={{ 
                  position: 'absolute', top: '12px', left: '12px', zIndex: 10,
                  background: 'rgba(15, 23, 42, 0.75)', border: '1px solid rgba(255,255,255,0.1)',
                  padding: '4px 10px', borderRadius: '8px', fontSize: '0.72rem', display: 'flex', alignItems: 'center', gap: '4px'
                }}>
                  <Radio size={12} style={{ color: '#38bdf8' }} /> VMS Broadcast Egress View (Live from Server)
                </div>

                <div style={{ width: '100%', height: '100%' }}>
                  <Player 
                    src={`/api/streams/${encodeURIComponent(streamId)}/live/index.m3u8`}
                    posterLabel={`${cameraName} — VMS Egress`}
                    minimal={true}
                  />
                </div>
              </div>
            )}
          </div>

          {/* Stats & Actions */}
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '20px' }}>
            
            {/* Outbound WebRTC Transmission Stats */}
            <div style={{ padding: '16px 20px', background: 'rgba(15, 23, 42, 0.3)', border: '1px solid rgba(255, 255, 255, 0.05)', borderRadius: '14px' }}>
              <h4 style={{ margin: '0 0 12px 0', fontSize: '0.82rem', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Outgoing WebRTC Link Stats
              </h4>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '10px' }}>
                <div style={statItemStyle}>
                  <span style={statLabelStyle}>Resolution</span>
                  <span style={statValStyle}>{stats.resolution}</span>
                </div>
                <div style={statItemStyle}>
                  <span style={statLabelStyle}>FPS</span>
                  <span style={statValStyle}>{stats.fps ? stats.fps.toFixed(0) : '—'}</span>
                </div>
                <div style={statItemStyle}>
                  <span style={statLabelStyle}>Out Bitrate</span>
                  <span style={statValStyle}>{stats.bitrate ? formatBitrate(stats.bitrate) : '0 kbps'}</span>
                </div>
                <div style={statItemStyle}>
                  <span style={statLabelStyle}>Packet Loss</span>
                  <span style={{ ...statValStyle, color: stats.packetLoss > 0.05 ? '#f87171' : '#34d399' }}>
                    {(stats.packetLoss * 100).toFixed(1)}%
                  </span>
                </div>
              </div>
            </div>

            {/* Verification Tools */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', justifyContent: 'center' }}>
              {isStreaming ? (
                <button
                  type="button"
                  onClick={() => setShowEgressPreview(!showEgressPreview)}
                  style={{
                    padding: '12px',
                    borderRadius: '10px',
                    border: '1px solid rgba(59, 130, 246, 0.3)',
                    background: 'rgba(59, 130, 246, 0.1)',
                    color: '#60a5fa',
                    fontWeight: 600,
                    fontSize: '0.8rem',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '6px',
                    transition: 'all 0.2s'
                  }}
                >
                  {showEgressPreview ? 'Hide Return Feed' : 'Test Return Feed (WHEP)'}
                </button>
              ) : (
                <div style={{ textAlign: 'center', fontSize: '0.78rem', color: '#64748b', border: '1px dashed rgba(255,255,255,0.05)', borderRadius: '10px', padding: '16px' }}>
                  Start broadcasting to test live egress return.
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
      
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
      `}</style>
    </div>
  )
}

// Styled via styles.css (.vms-input, .vms-select)

const statItemStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: '4px',
  background: 'rgba(15, 23, 42, 0.4)',
  padding: '8px 12px',
  borderRadius: '8px',
  border: '1px solid rgba(255,255,255,0.03)'
}

const statLabelStyle: React.CSSProperties = {
  fontSize: '0.68rem',
  color: '#64748b'
}

const statValStyle: React.CSSProperties = {
  fontSize: '0.85rem',
  fontWeight: 700,
  color: '#e2e8f0'
}
