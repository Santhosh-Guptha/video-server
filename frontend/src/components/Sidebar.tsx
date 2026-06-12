import { Camera, RefreshCw, Radar, Clock3 } from 'lucide-react'

type SidebarProps = {
  onRefresh: () => void
  totalCameras: number
  liveCameras: number
  lastSyncText: string
}

export function Sidebar({ onRefresh, totalCameras, liveCameras, lastSyncText }: SidebarProps) {
  return (
    <aside className="sidebar">
      <div className="brandBlock">
        <div className="brandMark">CV</div>
        <div>
          <div className="brandTitle">Camera Video Platform</div>
          <div className="brandSub">Live view • Recording • Playback</div>
        </div>
      </div>

      <button className="refreshBtn" onClick={onRefresh}>
        <RefreshCw size={16} /> Sync Cameras
      </button>

      <div className="statGrid">
        <div className="statCard">
          <Camera size={18} />
          <div className="statValue">{totalCameras}</div>
          <div className="statLabel">Cameras</div>
        </div>
        <div className="statCard">
          <Radar size={18} />
          <div className="statValue">{liveCameras}</div>
          <div className="statLabel">Streaming</div>
        </div>
      </div>

      <div className="infoCard">
        <div className="infoTitle"><Clock3 size={16} /> Last sync</div>
        <div className="infoText">{lastSyncText}</div>
      </div>

      <nav className="navList">
        <a href="#dashboard" className="navItem active">Dashboard</a>
        <a href="#live" className="navItem">Live View</a>
        <a href="#playback" className="navItem">Playback</a>
      </nav>

      <div className="sidebarNote">The backend is wired to <code>/api/cameras/camera-videoserver</code>.</div>
    </aside>
  )
}
