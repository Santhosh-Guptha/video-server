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

export function Dashboard({
  cameras,
  query,
  setQuery,
  selectedStreamIds,
  focusedStreamId,
  onSelect,
}: DashboardProps) {
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
          <div style={{ display: 'flex', gap: '30px' }}>
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
                {cameras.filter(c => c.raw_json.includes('"edgePush"')).length} nodes
              </div>
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
                    <div className="camName">{camera.name}</div>
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
              </div>
            </button>
          );
        })}
      </div>
    </section>
  );
}
