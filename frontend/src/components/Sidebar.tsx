import { Camera, RefreshCw, Radar, Clock3, Wifi } from 'lucide-react'

type SidebarProps = {
  onRefresh: () => void
  totalCameras: number
  liveCameras: number
  lastSyncText: string
  activeTab: string
  setActiveTab: (tab: string) => void
}

export function Sidebar({ onRefresh, totalCameras, liveCameras, lastSyncText, activeTab, setActiveTab }: SidebarProps) {
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
        <button
          type="button"
          className={`navItem ${activeTab === 'dashboard' ? 'active' : ''}`}
          onClick={() => setActiveTab('dashboard')}
          style={{ textAlign: 'left', width: '100%' }}
        >
          Dashboard
        </button>
        <button
          type="button"
          className={`navItem ${activeTab === 'live' ? 'active' : ''}`}
          onClick={() => setActiveTab('live')}
          style={{ textAlign: 'left', width: '100%' }}
        >
          Live View
        </button>
        <button
          type="button"
          className={`navItem ${activeTab === 'playback' ? 'active' : ''}`}
          onClick={() => setActiveTab('playback')}
          style={{ textAlign: 'left', width: '100%' }}
        >
          Playback
        </button>
        <button
          type="button"
          className={`navItem ${activeTab === 'edgepush' ? 'active' : ''}`}
          onClick={() => setActiveTab('edgepush')}
          style={{ textAlign: 'left', width: '100%', display: 'flex', alignItems: 'center', gap: '6px' }}
        >
          <Wifi size={14} /> Edge Push
        </button>
      </nav>

      <div className="sidebarNote">The backend is wired to <code>/api/cameras/camera-videoserver</code>.</div>
    </aside>
  )
}
