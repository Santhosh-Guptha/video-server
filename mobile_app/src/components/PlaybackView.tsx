import React, { useState, useEffect, useRef } from 'react';
import {
  History,
  Calendar,
  Clock,
  Play,
  Pause,
  FastForward,
  Rewind,
  Copy,
  ExternalLink,
  Sliders,
  Film
} from 'lucide-react';
import type { CameraConfig, PlaybackParams, StreamMode } from '../types/camera';
import { buildPlaybackRtspUrl, getVlcDeepLink } from '../services/rtspBuilder';

interface PlaybackViewProps {
  cameras: CameraConfig[];
  activeMode: StreamMode;
}

export const PlaybackView: React.FC<PlaybackViewProps> = ({ cameras, activeMode }) => {
  const [selectedCamId, setSelectedCamId] = useState<number>(cameras[0]?.id || 1);
  const [startDate, setStartDate] = useState<string>(new Date().toISOString().split('T')[0]);
  const [startTime, setStartTime] = useState<string>('09:00:00');
  const [endDate, setEndDate] = useState<string>(new Date().toISOString().split('T')[0]);
  const [endTime, setEndTime] = useState<string>('10:00:00');
  const [speed, setSpeed] = useState<number>(1);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [timelineHour, setTimelineHour] = useState<number>(9.5); // 09:30 AM
  const [copiedPlaybackUrl, setCopiedPlaybackUrl] = useState<boolean>(false);

  const selectedCam = cameras.find((c) => c.id === selectedCamId) || cameras[0];

  const playbackParams: PlaybackParams = {
    cameraId: selectedCamId,
    startDate,
    startTime,
    endDate,
    endTime,
    speed
  };

  const playbackRtspUrl = selectedCam
    ? buildPlaybackRtspUrl(selectedCam, playbackParams, activeMode)
    : '';



  const handleCopyPlaybackUrl = () => {
    navigator.clipboard.writeText(playbackRtspUrl);
    setCopiedPlaybackUrl(true);
    setTimeout(() => setCopiedPlaybackUrl(false), 2000);
  };

  const formatHourString = (decimalHour: number): string => {
    const hrs = Math.floor(decimalHour);
    const mins = Math.floor((decimalHour - hrs) * 60);
    return `${hrs.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:00`;
  };

  return (
    <div className="playback-container">
      {/* Top Header & Camera Selector */}
      <div className="playback-header">
        <div className="flex items-center gap-2">
          <History className="w-5 h-5 text-emerald-400" />
          <h2 className="section-title">NVR Footage Playback</h2>
        </div>

        <div className="cam-selector-group">
          <label>Select NVR Channel:</label>
          <select
            value={selectedCamId}
            onChange={(e) => setSelectedCamId(Number(e.target.value))}
          >
            {cameras.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} (Ch {c.channel} - {c.nvrBrand.toUpperCase()})
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Date & Time Range Controls */}
      <div className="playback-params-card">
        <div className="params-grid">
          <div className="param-item">
            <label>
              <Calendar className="w-3.5 h-3.5 text-blue-400 inline mr-1" />
              Date
            </label>
            <input
              type="date"
              value={startDate}
              onChange={(e) => {
                setStartDate(e.target.value);
                setEndDate(e.target.value);
              }}
            />
          </div>

          <div className="param-item">
            <label>
              <Clock className="w-3.5 h-3.5 text-emerald-400 inline mr-1" />
              Start Time
            </label>
            <input
              type="time"
              step="1"
              value={startTime}
              onChange={(e) => setStartTime(e.target.value)}
            />
          </div>

          <div className="param-item">
            <label>
              <Clock className="w-3.5 h-3.5 text-amber-400 inline mr-1" />
              End Time
            </label>
            <input
              type="time"
              step="1"
              value={endTime}
              onChange={(e) => setEndTime(e.target.value)}
            />
          </div>

          <div className="param-item">
            <label>
              <Sliders className="w-3.5 h-3.5 text-purple-400 inline mr-1" />
              Speed Multiplier
            </label>
            <select
              value={speed}
              onChange={(e) => setSpeed(Number(e.target.value))}
            >
              <option value={0.5}>0.5x Slow</option>
              <option value={1}>1x Normal</option>
              <option value={2}>2x Speed</option>
              <option value={4}>4x Speed</option>
              <option value={8}>8x Speed</option>
              <option value={16}>16x Fast</option>
            </select>
          </div>
        </div>
      </div>

      {/* Playback Canvas Screen */}
      <div className="playback-player-wrapper">
        <div className="playback-screen">
          <PlaybackCanvasPlayer
            cameraName={selectedCam?.name || 'Godown Camera'}
            timeString={formatHourString(timelineHour)}
            isPlaying={isPlaying}
            speed={speed}
          />
        </div>

        {/* Playback Controls Bar */}
        <div className="playback-controls-bar">
          <button
            type="button"
            className="play-btn"
            onClick={() => setIsPlaying(!isPlaying)}
          >
            {isPlaying ? <Pause className="w-5 h-5" /> : <Play className="w-5 h-5 ml-0.5" />}
          </button>

          <div className="seek-controls">
            <button type="button" onClick={() => setTimelineHour(Math.max(0, timelineHour - 0.25))}>
              <Rewind className="w-4 h-4" />
            </button>
            <span className="current-seek-time">{formatHourString(timelineHour)}</span>
            <button type="button" onClick={() => setTimelineHour(Math.min(24, timelineHour + 0.25))}>
              <FastForward className="w-4 h-4" />
            </button>
          </div>

          <a
            href={getVlcDeepLink(playbackRtspUrl)}
            className="vlc-play-btn"
            title="Stream Recorded NVR Footage in VLC App"
          >
            <ExternalLink className="w-4 h-4 mr-1" />
            VLC Playback
          </a>
        </div>
      </div>

      {/* 24-Hour Visual Timeline Scrubber */}
      <div className="timeline-container">
        <div className="timeline-header">
          <span>24-Hour Recording Timeline</span>
          <span className="timeline-legend">
            <span className="legend-dot continuous" /> Continuous
            <span className="legend-dot motion" /> Motion
            <span className="legend-dot alarm" /> Alarm
          </span>
        </div>

        <div className="timeline-track-wrapper">
          {/* Hour Markers */}
          <div className="timeline-hours">
            {Array.from({ length: 25 }, (_, i) => (
              <span key={i} className="hour-tick">
                {i % 3 === 0 ? `${i}:00` : ''}
              </span>
            ))}
          </div>

          {/* Interactive Scrubber Bar */}
          <div className="timeline-bar">
            {/* Mock Continuous Recording Blocks */}
            <div className="recording-block continuous" style={{ left: '0%', width: '100%' }} />

            {/* Motion Event Blocks */}
            <div className="recording-block motion" style={{ left: '37.8%', width: '4.8%' }} title="Motion 09:05 - 09:12" />
            <div className="recording-block motion" style={{ left: '39.2%', width: '10.4%' }} title="Motion 09:25 - 09:40" />
            <div className="recording-block alarm" style={{ left: '40.6%', width: '3.4%' }} title="Alarm 09:45 - 09:50" />

            {/* Scrubber Playhead Indicator */}
            <input
              type="range"
              min={0}
              max={24}
              step={0.01}
              value={timelineHour}
              onChange={(e) => {
                const val = parseFloat(e.target.value);
                setTimelineHour(val);
                setStartTime(formatHourString(val));
              }}
              className="timeline-range-slider"
            />
          </div>
        </div>
      </div>

      {/* Generated NVR RTSP Playback URL Output */}
      <div className="nvr-rtsp-box">
        <div className="box-title">
          <Film className="w-4 h-4 text-emerald-400" />
          <span>Generated NVR RTSP Playback URL ({selectedCam?.nvrBrand.toUpperCase()})</span>
        </div>
        <code className="playback-url-code">{playbackRtspUrl}</code>

        <div className="box-actions">
          <button type="button" className="btn-copy" onClick={handleCopyPlaybackUrl}>
            <Copy className="w-3.5 h-3.5 mr-1 inline" />
            {copiedPlaybackUrl ? 'Copied!' : 'Copy Playback URL'}
          </button>
        </div>
      </div>
    </div>
  );
};

// Playback Canvas Video Player Component
const PlaybackCanvasPlayer: React.FC<{
  cameraName: string;
  timeString: string;
  isPlaying: boolean;
  speed: number;
}> = ({ cameraName, timeString, isPlaying, speed }) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animId: number;
    let frame = 0;

    const render = () => {
      if (isPlaying) frame += speed;
      const width = canvas.width;
      const height = canvas.height;

      // Dark playback video canvas
      ctx.fillStyle = '#0b0f19';
      ctx.fillRect(0, 0, width, height);

      // Playback watermark & timestamp
      ctx.fillStyle = 'rgba(255, 255, 255, 0.7)';
      ctx.font = '14px monospace';
      ctx.fillText(`NVR REPLAY: ${cameraName}`, 20, 30);
      ctx.fillText(`TIMESTAMP: ${timeString}`, 20, 50);

      if (isPlaying) {
        ctx.fillStyle = '#10b981';
        ctx.fillText(`PLAYING (${speed}x)`, width - 120, 30);
      } else {
        ctx.fillStyle = '#f59e0b';
        ctx.fillText('PAUSED', width - 80, 30);
      }

      // Simulated playback video frame effect
      const boxPos = (frame * 2) % (width - 100);
      ctx.strokeStyle = '#3b82f6';
      ctx.lineWidth = 2;
      ctx.strokeRect(boxPos + 20, height / 2 - 40, 80, 80);

      animId = requestAnimationFrame(render);
    };

    render();
    return () => cancelAnimationFrame(animId);
  }, [cameraName, timeString, isPlaying, speed]);

  return <canvas ref={canvasRef} width={640} height={360} className="playback-canvas" />;
};
