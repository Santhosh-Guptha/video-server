import {
  Camera,
  Search,
  Activity,
  Shield,
  HardDrive
} from "lucide-react";

import type { Camera as CameraType } from "../types";

type DashboardProps = {
  cameras: CameraType[];
  query: string;
  setQuery: (value: string) => void;
  selectedStreamId?: string;
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
  selectedStreamId,
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

  const active = cameras.filter((c) => c.active).length;
  const inactive = cameras.length - active;

  return (
    <section className="content" id="dashboard">
      <div className="hero">
        <div>
          <div className="eyebrow">Camera Registry</div>

          <h1>Connected Camera Streams</h1>

          <p>
            Search, inspect and manage camera streams.
            Each camera may contain HD, NORMAL and ARCHIVE streams.
          </p>
        </div>

        <div className="heroStats">
          <div className="heroStat">
            <Camera size={18} />
            <div>
              <strong>{cameras.length}</strong>
              <span>Total Streams</span>
            </div>
          </div>

          <div className="heroStat">
            <Shield size={18} />
            <div>
              <strong>{active}</strong>
              <span>Active</span>
            </div>
          </div>

          <div className="heroStat">
            <HardDrive size={18} />
            <div>
              <strong>{inactive}</strong>
              <span>Inactive</span>
            </div>
          </div>
        </div>
      </div>

      <div className="searchBar">
        <Search size={18} />

        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search by name, stream id, FPS, resolution..."
        />
      </div>

      <div className="gridWrap">
        {filtered.map((camera) => (
          <button
            key={camera.pk}
            className={`cameraCard ${
              selectedStreamId === camera.stream_id ? "selected" : ""
            }`}
            onClick={() => onSelect(camera)}
          >
            <div className="cameraTop">
              <div>
                <div className="camName">{camera.name}</div>

                <div className="camSub">
                  {camera.stream_type} • {camera.stream_id}
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

            <div className="cameraMeta">
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
        ))}
      </div>
    </section>
  );
}
