import React, { useState, useEffect } from "react";
import {
  Camera,
  Search,
  Activity,
  Shield,
  HardDrive,
  Check,
  AlertTriangle,
  Flame,
  Radio
} from "lucide-react";

import type { Camera as CameraType } from "../types";

type DashboardProps = {
  cameras: CameraType[];
  query: string;
  setQuery: (value: string) => void;
  selectedStreamIds: string[];
  focusedStreamId?: string;
  onSelect: (camera: CameraType) => void;
};

const codecLabel = (codec?: string | null) => {
  if (!codec) return "Unknown";

  const u = codec.toUpperCase();

  if (u.includes("H265") || u.includes("HEVC")) {
    return "H.265";
  }

  if (u.includes("H264")) {
    return "H.264";
  }

  return codec;
};

const formatDuration = (sec: number) => {
  const hrs = Math.floor(sec / 3600);
  const mins = Math.floor((sec % 3600) / 60);
  if (hrs > 0) {
    return `${hrs}h ${mins}m`;
  }
  return `${mins}m ${Math.round(sec % 60)}s`;
};

export function Dashboard({
  cameras,
  query,
  setQuery,
  selectedStreamIds,
  focusedStreamId,
  onSelect,
}: DashboardProps) {
  const [recoveredStats, setRecoveredStats] = useState<{
    total_count: number;
    total_duration: number;
    by_stream: Record<string, { count: number; duration: number }>;
    recent: any[];
  }>({
    total_count: 0,
    total_duration: 0,
    by_stream: {},
    recent: []
  });

  useEffect(() => {
    async function loadRecoveredStats() {
      try {
        const res = await fetch("/api/recordings/recovered-stats");
        if (res.ok) {
          const data = await res.json();
          setRecoveredStats(data);
        }
      } catch (e) {
        console.error("Failed to load recovered stats", e);
      }
    }
    loadRecoveredStats();
  }, []);
  const filtered = cameras.filter((c) => {
    const q = query.toLowerCase();

    return (
      c.name.toLowerCase().includes(q) ||
      c.stream_id.toLowerCase().includes(q) ||
      c.stream_type.toLowerCase().includes(q) ||
      String(c.fps ?? "").includes(q) ||
      String(c.width ?? "").includes(q) ||
      String(c.height ?? "").includes(q) ||
      String(c.archive_type ?? "")
        .toLowerCase()
        .includes(q)
    );
  });

  // Calculate stats across all cameras and streams
  const activeCameras = cameras.filter((c) => c.active).length;
  const inactiveCameras = cameras.length - activeCameras;

  let onlineStreams = 0;
  let connectingStreams = 0;
  let reconnectingStreams = 0;
  let offlineStreams = 0;
  let errorStreams = 0;
  let totalStreams = 0;

  cameras.forEach((c) => {
    if (c.streams && c.streams.length > 0) {
      c.streams.forEach((s) => {
        totalStreams++;
        if (s.status === 'ONLINE') onlineStreams++;
        else if (s.status === 'CONNECTING') connectingStreams++;
        else if (s.status === 'RECONNECTING') reconnectingStreams++;
        else if (s.status === 'OFFLINE' || s.status === 'REGISTERED') offlineStreams++;
        else if (s.status === 'ERROR') errorStreams++;
      });
    } else {
      totalStreams++;
      if (c.active) onlineStreams++;
      else offlineStreams++;
    }
  });

  return (
    <section className="content" id="dashboard">
      <div className="hero">
        <div>
          <div className="eyebrow">Enterprise VMS Ingestion</div>
          <h1>Camera Streams & Ingest Status</h1>
          <p>
            Monitor stream health, resolution mappings, and active transcode pipelines.
            Camera streams are dynamically ingested and transcoded via MediaMTX and monitored by FastAPI.
          </p>
        </div>

        <div className="heroStats" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '10px' }}>
          <div className="heroStat">
            <Camera size={18} />
            <div>
              <strong>{cameras.length}</strong>
              <span>Cameras</span>
            </div>
          </div>

          <div className="heroStat">
            <Shield size={18} />
            <div>
              <strong>{activeCameras}</strong>
              <span>Active Cams</span>
            </div>
          </div>

          <div className="heroStat" style={{ borderLeft: '1px solid rgba(255, 255, 255, 0.1)', paddingLeft: '15px' }}>
            <Radio size={18} style={{ color: '#10b981' }} />
            <div>
              <strong style={{ color: '#10b981' }}>{onlineStreams}</strong>
              <span>Streams Online</span>
            </div>
          </div>

          <div className="heroStat">
            <Flame size={18} style={{ color: '#f59e0b' }} />
            <div>
              <strong style={{ color: '#f59e0b' }}>{connectingStreams + reconnectingStreams}</strong>
              <span>Syncing</span>
            </div>
          </div>

          <div className="heroStat">
            <AlertTriangle size={18} style={{ color: '#ef4444' }} />
            <div>
              <strong style={{ color: '#ef4444' }}>{errorStreams}</strong>
              <span>Errors</span>
            </div>
          </div>
        </div>
      </div>

      {/* Stream Health Dashboard Panel */}
      <div className="streamDashboardPanel" style={{ display: 'flex', gap: '20px', margin: '20px 0', background: 'rgba(30, 41, 59, 0.5)', padding: '15px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.05)' }}>
        <div style={{ flex: 1 }}>
          <h4 style={{ margin: '0 0 10px 0', fontSize: '14px', color: '#94a3b8' }}>Ingestion Pipe Statistics</h4>
          <div style={{ display: 'flex', gap: '30px', flexWrap: 'wrap' }}>
            <div>
              <span style={{ fontSize: '12px', color: '#64748b' }}>WebRTC WHEP Ready</span>
              <div style={{ fontSize: '18px', fontWeight: 'bold', color: '#f8fafc' }}>{onlineStreams} streams</div>
            </div>
            <div>
              <span style={{ fontSize: '12px', color: '#64748b' }}>HLS Fallback Active</span>
              <div style={{ fontSize: '18px', fontWeight: 'bold', color: '#38bdf8' }}>{totalStreams} streams</div>
            </div>
            <div>
              <span style={{ fontSize: '12px', color: '#64748b' }}>Active Edge Pushes</span>
              <div style={{ fontSize: '18px', fontWeight: 'bold', color: '#a855f7' }}>
                {cameras.filter(c => !c.rtsp_url || c.rtsp_url.trim() === "" || !c.rtsp_url.trim().toLowerCase().startsWith("rtsp://")).length} nodes
              </div>
            </div>
            <div>
              <span style={{ fontSize: '12px', color: '#64748b' }}>Recovered Files</span>
              <div style={{ fontSize: '18px', fontWeight: 'bold', color: '#f59e0b' }}>{recoveredStats.total_count} files</div>
            </div>
            <div>
              <span style={{ fontSize: '12px', color: '#64748b' }}>Recovered Duration</span>
              <div style={{ fontSize: '18px', fontWeight: 'bold', color: '#f59e0b' }}>{formatDuration(recoveredStats.total_duration)}</div>
            </div>
          </div>
        </div>
      </div>

      <div className="searchBar">
        <Search size={18} />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search by name, stream ID, codec, status..."
        />
      </div>

      <div className="gridWrap">
        {filtered.map((camera) => {
          const isSelected = selectedStreamIds.includes(camera.stream_id);
          const isFocused = focusedStreamId === camera.stream_id;
          
          return (
            <button
              key={camera.id}
              className={`cameraCard ${isSelected ? "selected" : ""} ${isFocused ? "focused" : ""}`}
              onClick={() => onSelect(camera)}
            >
              <div className="cameraTop">
                <div className="cardHeaderArea">
                  <span className="selectionCheck">
                    <Check size={12} strokeWidth={3} />
                  </span>
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                      <div className="camName">{camera.name}</div>
                      {(() => {
                        const isEdge = !camera.rtsp_url || camera.rtsp_url.trim() === "" || !camera.rtsp_url.trim().toLowerCase().startsWith("rtsp://");
                        return (
                          <span style={{
                            fontSize: '0.62rem',
                            padding: '2px 6px',
                            borderRadius: '4px',
                            fontWeight: 700,
                            background: isEdge ? 'rgba(168, 85, 247, 0.15)' : 'rgba(59, 130, 246, 0.15)',
                            color: isEdge ? '#c084fc' : '#60a5fa',
                            border: `1px solid ${isEdge ? 'rgba(168, 85, 247, 0.2)' : 'rgba(59, 130, 246, 0.2)'}`
                          }}>
                            {isEdge ? 'EDGE PUSH' : 'RTSP PULL'}
                          </span>
                        );
                      })()}
                    </div>
                    <div className="camSub">
                      ID: {camera.source_camera_id} • {camera.stream_id}
                    </div>
                  </div>
                </div>

                <span
                  className={`statusPill ${
                    camera.active ? "ok" : "off"
                  }`}
                >
                  {camera.active ? "Active" : "Inactive"}
                </span>
              </div>

              {/* Stream Profiles Area showing dynamic status */}
              <div className="streamProfilesArea" style={{ display: 'flex', gap: '6px', margin: '12px 0 6px 0', flexWrap: 'wrap' }}>
                {camera.streams && camera.streams.map((s) => {
                  let statusClass = "offline";
                  if (s.status === 'ONLINE') statusClass = "online";
                  else if (s.status === 'RECONNECTING' || s.status === 'CONNECTING') statusClass = "warning";
                  else if (s.status === 'ERROR') statusClass = "error";
                  
                  return (
                    <span key={s.id} className={`streamBadge ${statusClass}`}>
                      {s.profile_type}: {s.status.toLowerCase()}
                    </span>
                  );
                })}
              </div>

              <div className="cameraMeta" style={{ borderTop: '1px solid rgba(255,255,255,0.03)', paddingTop: '10px' }}>
                <div>
                  <span>Codec</span>
                  <strong>{codecLabel(camera.archive_type)}</strong>
                </div>

                <div>
                  <span>FPS</span>
                  <strong>{camera.fps ?? "-"}</strong>
                </div>

                <div>
                  <span>Resolution</span>
                  <strong>
                    {camera.width ?? "-"} × {camera.height ?? "-"}
                  </strong>
                </div>

                <div>
                  <span>Bitrate</span>
                  <strong>
                    {camera.bitrate
                      ? `${Math.round(camera.bitrate / 1000)} kbps`
                      : "-"}
                  </strong>
                </div>
              </div>

              <div className="cameraFooter">
                <span className="footTag">
                  <Activity size={14} />
                  {camera.transcode ? " Transcode" : " Copy"}
                </span>

                <span className="footTag">
                  {camera.camera_type || "UNKNOWN"}
                </span>

                {recoveredStats.by_stream[camera.stream_id] && (
                  <span className="footTag" style={{ background: 'rgba(245, 158, 11, 0.15)', color: '#f59e0b', borderColor: 'rgba(245, 158, 11, 0.3)' }}>
                    {recoveredStats.by_stream[camera.stream_id].count} recovered
                  </span>
                )}
              </div>
            </button>
          );
        })}
      </div>

      {recoveredStats.recent && recoveredStats.recent.length > 0 && (
        <div style={{ marginTop: '30px', background: 'rgba(30, 41, 59, 0.4)', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.05)', padding: '20px' }}>
          <h3 style={{ margin: '0 0 15px 0', fontSize: '1.1rem', color: '#fff', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Activity size={18} style={{ color: '#f59e0b' }} />
            Recently Recovered Segments
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {recoveredStats.recent.map((rec: any) => {
              const cam = cameras.find(c => c.stream_id === rec.stream_id);
              const camName = cam ? cam.name : rec.stream_id;
              return (
                <div key={rec.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 16px', background: 'rgba(15, 23, 42, 0.4)', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.02)' }}>
                  <div>
                    <span style={{ fontWeight: 600, color: '#f8fafc', fontSize: '0.86rem' }}>{rec.filename}</span>
                    <div style={{ fontSize: '0.75rem', color: '#64748b', marginTop: '2px' }}>
                      Camera: <span style={{ color: '#cbd5e1' }}>{camName}</span> • Stream: <span style={{ color: '#cbd5e1' }}>{rec.stream_id}</span>
                    </div>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px', fontSize: '0.8rem' }}>
                    <span style={{ color: '#94a3b8' }}>Duration: {Math.round(rec.duration)}s</span>
                    <span style={{ color: '#64748b' }}>{new Date(rec.created_at).toLocaleString()}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </section>
  );
}
