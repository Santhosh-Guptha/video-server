import { useEffect, useRef, useState } from 'react';
import { AlertCircle, Loader2, Play, Volume2, VolumeX, Maximize2 } from 'lucide-react';
import { StreamHealthBadge, StreamHealthState } from './StreamHealthBadge';
import { SessionStatsOverlay, PlayerStats } from './SessionStatsOverlay';

interface WebRTCPlayerProps {
  streamId: string;
  posterLabel?: string;
  isFocused?: boolean;
  minimal?: boolean;
  onFallbackToHls: () => void;
}

export function WebRTCPlayer({ streamId, posterLabel, isFocused, minimal, onFallbackToHls }: WebRTCPlayerProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const pcRef = useRef<RTCPeerConnection | null>(null);
  const statsIntervalRef = useRef<number | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const connectionTimeoutRef = useRef<number | null>(null);

  const [muted, setMuted] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [health, setHealth] = useState<StreamHealthState>('CONNECTING');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [showStats, setShowStats] = useState(false);
  const [stats, setStats] = useState<PlayerStats>({ protocol: 'WHEP', reconnections: 0 });

  // Keep track of previous stats values for delta calculations
  const prevStatsRef = useRef<{
    timestamp: number;
    bytesReceived: number;
    framesDecoded: number;
  }>({ timestamp: 0, bytesReceived: 0, framesDecoded: 0 });

  const reconnectCountRef = useRef(0);
  const maxReconnectAttempts = 1;

  useEffect(() => {
    startWebRTC();

    // Visibility change handling to optimize offscreen tabs
    const handleVisibility = () => {
      if (document.hidden) {
        console.log(`[WebRTCPlayer:${streamId}] Tab hidden. Pausing stats collection.`);
        stopStatsInterval();
      } else {
        console.log(`[WebRTCPlayer:${streamId}] Tab active. Resuming stats collection.`);
        startStatsInterval();
      }
    };

    document.addEventListener('visibilitychange', handleVisibility);

    return () => {
      document.removeEventListener('visibilitychange', handleVisibility);
      cleanupConnection();
    };
  }, [streamId]);

  useEffect(() => {
    const video = videoRef.current;
    if (video) video.muted = muted;
  }, [muted]);

  const cleanupConnection = () => {
    stopStatsInterval();
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    if (connectionTimeoutRef.current) {
      clearTimeout(connectionTimeoutRef.current);
      connectionTimeoutRef.current = null;
    }

    if (pcRef.current) {
      // Send WHEP session termination delete request
      const sessionUrl = stats.protocol === 'WHEP' ? (pcRef.current as any).sessionUrl : null;
      if (sessionUrl) {
        fetch(sessionUrl, { method: 'DELETE' }).catch(() => {});
      }
      pcRef.current.close();
      pcRef.current = null;
    }
  };

  const startWebRTC = async () => {
    cleanupConnection();
    setLoaded(false);
    setHealth('CONNECTING');
    setErrorMessage(null);

    // Initial connection timeout (falls back to HLS if WebRTC fails to connect in 3 seconds)
    connectionTimeoutRef.current = window.setTimeout(() => {
      console.warn(`[WebRTCPlayer:${streamId}] WebRTC connection timed out. Falling back to HLS.`);
      onFallbackToHls();
    }, 3000);

    try {
      // 1. Fetch ICE servers
      const iceResp = await fetch('/api/webrtc/ice-servers');
      if (!iceResp.ok) throw new Error('Failed to retrieve ICE server configuration');
      const { iceServers } = await iceResp.json();

      // 2. Setup RTCPeerConnection
      const pc = new RTCPeerConnection({ iceServers });
      pcRef.current = pc;

      // Create dummy audio/video transceivers for receive-only direction
      pc.addTransceiver('video', { direction: 'recvonly' });
      pc.addTransceiver('audio', { direction: 'recvonly' });

      pc.ontrack = (event) => {
        const video = videoRef.current;
        if (video && event.streams && event.streams[0]) {
          video.srcObject = event.streams[0];
          video.play().catch((err) => console.log('Video play error:', err));
          setLoaded(true);
          setHealth('ONLINE');
          reconnectCountRef.current = 0;
          if (connectionTimeoutRef.current) {
            clearTimeout(connectionTimeoutRef.current);
            connectionTimeoutRef.current = null;
          }
        }
      };

      pc.oniceconnectionstatechange = () => {
        console.log(`[WebRTCPlayer:${streamId}] ICE state: ${pc.iceConnectionState}`);
        if (pc.iceConnectionState === 'disconnected' || pc.iceConnectionState === 'failed') {
          handleDisconnection('ICE Connection Disconnected');
        }
      };

      // 3. Create WebRTC offer
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);

      // 4. Send Offer to FastAPI signaling proxy
      const user_id = uuidv4(); // Generate dummy viewer ID
      const whepResp = await fetch(`/api/streams/${streamId}/live/whep?user_id=${user_id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/sdp' },
        body: offer.sdp,
      });

      if (!whepResp.ok) {
        const errText = await whepResp.text();
        const error = new Error(`Signaling failed: ${errText || whepResp.statusText}`);
        (error as any).status = whepResp.status;
        throw error;
      }

      // Get Session URL from Location header
      const locationHeader = whepResp.headers.get('Location');
      if (!locationHeader) throw new Error('Missing WHEP Location session header');
      
      const sessionUrl = locationHeader;
      (pc as any).sessionUrl = sessionUrl;
      (pc as any).sessionId = sessionUrl.split('/').pop();

      // Handle Trickle ICE Candidates
      pc.onicecandidate = (event) => {
        if (event.candidate && pcRef.current === pc) {
          fetch(sessionUrl, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/trickle-ice-sdpfrag' },
            body: event.candidate.candidate,
          }).catch((err) => console.error('Trickle candidate error:', err));
        }
      };

      // Apply SDP Answer
      const answerSdp = await whepResp.text();
      await pc.setRemoteDescription(new RTCSessionDescription({
        type: 'answer',
        sdp: answerSdp
      }));

      // Initialize stats gathering
      startStatsInterval();

    } catch (err: any) {
      console.error(`[WebRTCPlayer:${streamId}] WHEP connection failed:`, err);
      const isPermanent = err && (err.status === 400 || err.status === 415 || (err.message && err.message.toLowerCase().includes('codec')));
      handleDisconnection(err.message || 'Negotiation failed', isPermanent);
    }
  };

  const handleDisconnection = (reason: string, isPermanent = false) => {
    setHealth('RECOVERING');
    setErrorMessage(reason);
    cleanupConnection();

    if (!isPermanent && reconnectCountRef.current < maxReconnectAttempts) {
      reconnectCountRef.current += 1;
      const backoffDelay = Math.min(1000 * Math.pow(2, reconnectCountRef.current), 10000);
      console.log(`[WebRTCPlayer:${streamId}] Reconnecting (attempt ${reconnectCountRef.current}) in ${backoffDelay}ms...`);
      setStats(prev => ({ ...prev, reconnections: reconnectCountRef.current }));
      
      reconnectTimeoutRef.current = window.setTimeout(() => {
        startWebRTC();
      }, backoffDelay);
    } else {
      console.error(`[WebRTCPlayer:${streamId}] Permanent failure or max reconnection attempts reached. Falling back to HLS.`);
      setHealth('FAILED');
      onFallbackToHls();
    }
  };

  const startStatsInterval = () => {
    stopStatsInterval();
    if (document.hidden) return; // Don't run stats if tab is offscreen

    statsIntervalRef.current = window.setInterval(async () => {
      const pc = pcRef.current;
      if (!pc || pc.iceConnectionState !== 'connected') return;

      try {
        const rtcStats = await pc.getStats();
        let videoTrackStats: any = null;
        let candidatePairStats: any = null;

        rtcStats.forEach((report) => {
          if (report.type === 'inbound-rtp' && report.mediaType === 'video') {
            videoTrackStats = report;
          }
          if (report.type === 'candidate-pair' && report.state === 'succeeded') {
            candidatePairStats = report;
          }
        });

        if (videoTrackStats) {
          const now = Date.now();
          const timeDelta = (now - prevStatsRef.current.timestamp) / 1000; // in seconds

          const bytesReceived = videoTrackStats.bytesReceived || 0;
          const bytesDelta = bytesReceived - prevStatsRef.current.bytesReceived;
          const bitrate = timeDelta > 0 ? (bytesDelta * 8) / (timeDelta * 1000) : 0; // kbps

          const framesDecoded = videoTrackStats.framesDecoded || 0;
          const framesDelta = framesDecoded - prevStatsRef.current.framesDecoded;
          const fps = timeDelta > 0 ? framesDelta / timeDelta : 0;

          const rtt = candidatePairStats ? candidatePairStats.currentRoundTripTime * 1000 : undefined; // ms
          const packetsReceived = videoTrackStats.packetsReceived || 0;
          const packetsLost = videoTrackStats.packetsLost || 0;
          const packetLoss = (packetsReceived + packetsLost) > 0 ? packetsLost / (packetsReceived + packetsLost) : 0;

          const resolution = videoTrackStats.frameWidth && videoTrackStats.frameHeight
            ? `${videoTrackStats.frameWidth}x${videoTrackStats.frameHeight}`
            : undefined;

          const newStats: PlayerStats = {
            protocol: 'WHEP',
            resolution,
            fps,
            bitrate,
            rtt,
            packetLoss,
            jitter: videoTrackStats.jitter ? videoTrackStats.jitter * 1000 : undefined, // ms
            reconnections: reconnectCountRef.current,
          };

          setStats(newStats);

          // Update prev values
          prevStatsRef.current = {
            timestamp: now,
            bytesReceived,
            framesDecoded,
          };

          // Send stats payload back to control plane API every 4-6 seconds
          // We can throttle sending to backend by checking if timestamp modulo 2 is 0
          if (Math.floor(now / 1000) % 6 < 2) {
            const sessionId = (pc as any).sessionId;
            if (sessionId) {
              fetch(`/api/webrtc/streams/${streamId}/stats`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  session_id: sessionId,
                  fps,
                  resolution: resolution || null,
                  bitrate,
                  rtt: rtt ?? null,
                  packet_loss: packetLoss,
                  jitter: videoTrackStats.jitter ? videoTrackStats.jitter * 1000 : null,
                  frames_dropped: videoTrackStats.framesDropped || 0,
                  decoder_latency: videoTrackStats.totalDecodeTime && framesDecoded > 0 
                    ? (videoTrackStats.totalDecodeTime / framesDecoded) * 1000 
                    : null
                })
              }).catch(() => {});
            }
          }
        }
      } catch (e) {
        console.error('Error fetching WebRTC stats:', e);
      }
    }, 2000);
  };

  const stopStatsInterval = () => {
    if (statsIntervalRef.current) {
      clearInterval(statsIntervalRef.current);
      statsIntervalRef.current = null;
    }
  };

  const uuidv4 = () => {
    if (typeof window !== 'undefined' && window.crypto && typeof window.crypto.getRandomValues === 'function') {
      try {
        return '10000000-1000-4000-8000-100000000000'.replace(/[018]/g, (c: any) =>
          (c ^ crypto.getRandomValues(new Uint8Array(1))[0] & 15 >> c / 4).toString(16)
        );
      } catch (e) {
        console.warn('crypto.getRandomValues failed, falling back to Math.random', e);
      }
    }
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
      const r = (Math.random() * 16) | 0;
      const v = c === 'x' ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  };

  return (
    <div className={`playerShell ${isFocused ? 'focused' : ''} ${minimal ? 'minimalMode' : ''}`} style={{ width: '100%', height: '100%', position: 'relative' }}>
      {!minimal && (
        <div className="playerHeader">
          <div>
            <div className="eyebrow">{posterLabel ?? 'Live feed'}</div>
            <h3 className="panelTitle">Real-time WebRTC camera view</h3>
          </div>
          <div className="playerChips" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <StreamHealthBadge status={health} errorMessage={errorMessage} />
            <span className="chip chipLive"><span className="dotPulse" />Live</span>
            <span className="chip" style={{ background: 'rgba(56, 189, 248, 0.15)', color: '#38bdf8', borderColor: 'rgba(56, 189, 248, 0.3)' }}>WebRTC (WHEP)</span>
            <span className="chip">Sub-second Latency</span>
          </div>
        </div>
      )}

      <div className="playerViewport" style={{ position: 'relative', overflow: 'hidden', background: '#090d16' }}>
        {minimal && (
          <div className="minimalCameraLabel" style={{ zIndex: 11 }}>
            {posterLabel ?? 'Live feed'}
            <span style={{ marginLeft: '6px', fontSize: '9px', opacity: 0.8, color: '#38bdf8' }}>WebRTC</span>
          </div>
        )}
        
        {!loaded && (
          <div className="playerOverlay" style={{ background: 'rgba(9, 13, 22, 0.85)', backdropFilter: 'blur(8px)' }}>
            <Loader2 className="spin" size={20} style={{ color: '#38bdf8' }} />
            <div className="overlayText" style={{ color: '#cbd5e1' }}>
              {health === 'RECOVERING' 
                ? `Reconnecting stream (attempt ${reconnectCountRef.current})...` 
                : 'Negotiating WebRTC stream…'}
            </div>
          </div>
        )}

        <video 
          ref={videoRef} 
          className="videoEl" 
          controls={!minimal} 
          autoPlay 
          playsInline 
          muted={muted}
          style={{ width: '100%', height: '100%', objectFit: 'contain' }}
        />
        
        <div className="fakeStamp" style={{ backgroundColor: 'rgba(239, 68, 68, 0.2)', border: '1px solid rgba(239, 68, 68, 0.4)', color: '#ef4444' }}>
          WEBRTC LIVE
        </div>

        <SessionStatsOverlay 
          stats={stats} 
          visible={showStats} 
          onToggle={() => setShowStats(!showStats)} 
        />
      </div>

      {!minimal && (
        <div className="playerControls">
          <button className="miniBtn" type="button" onClick={() => setMuted(m => !m)}>
            {muted ? <VolumeX size={16} /> : <Volume2 size={16} />}
            {muted ? 'Unmute' : 'Mute'}
          </button>
          <button className="miniBtn" type="button" onClick={() => videoRef.current?.play().catch(() => {})}>
            <Play size={16} /> Play
          </button>
          <button className="miniBtn" type="button" onClick={() => videoRef.current?.requestFullscreen?.()}>
            <Maximize2 size={16} /> Fullscreen
          </button>
          <div className="playerHint" style={{ color: '#64748b' }}>WHEP session active</div>
        </div>
      )}

      {!minimal && (
        <div className="playerFooter" style={{ borderColor: 'rgba(255,255,255,0.05)' }}>
          <AlertCircle size={14} style={{ color: '#38bdf8' }} />
          <span>Using ultra-low latency WebRTC stream proxy. Bypassing media packets.</span>
        </div>
      )}
    </div>
  );
}
