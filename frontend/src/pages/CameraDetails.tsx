import { Play, Square, CalendarClock, FileVideo2, CheckCircle2, XCircle, X } from 'lucide-react'
import type { Camera, RecordingSegment } from '../types'

const codecLabel = (codec?: string | null) => {
  if (!codec) return 'Unknown'
  const u = codec.toUpperCase()
  if (u.includes('H265') || u.includes('HEVC')) return 'H.265'
  if (u.includes('H264')) return 'H.264'
  return codec
}

type Props = {
  camera?: Camera
  recordings: RecordingSegment[]
  onStartLive: () => void
  onStopLive: () => void
  onOpenPlayback: () => void
  onClose?: () => void
}

export function CameraDetails({ camera, recordings, onStartLive, onStopLive, onOpenPlayback, onClose }: Props) {
  if (!camera) {
    return (
      <section className="detailsPanel">
        <div className="emptyState">
          <FileVideo2 size={42} />
          <h3>Select a camera</h3>
          <p>Choose a stream from the dashboard to view live video, metadata, and recordings.</p>
        </div>
      </section>
    )
  }

  const raw = (() => {
    try { return JSON.parse(camera.raw_json || '{}') } catch { return {} }
  })()

  return (
    <section className="detailsPanel" id="live" style={{ border: 'none', background: 'transparent', padding: 0, boxShadow: 'none' }}>
      <div className="panelHead" style={{ width: '100%' }}>
        <div style={{ flex: 1 }}>
          <div className="eyebrow">Live session</div>
          <h2 className="panelTitle" style={{ fontSize: '1.2rem', margin: '4px 0' }}>{camera.name}</h2>
          <div className="panelSub" style={{ fontSize: '0.8rem', opacity: 0.8 }}>{camera.stream_id} • {camera.stream_type}</div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '8px' }}>
          {onClose && (
            <button 
              onClick={onClose} 
              style={{ background: 'none', border: 'none', color: '#64748b', cursor: 'pointer', padding: '4px' }}
              title="Close Drawer"
            >
              <X size={18} />
            </button>
          )}
          <div className={`statusLarge ${camera.active ? 'ok' : 'off'}`} style={{ padding: '4px 10px', fontSize: '0.78rem' }}>
            {camera.active ? <CheckCircle2 size={12} /> : <XCircle size={12} />}
            {camera.active ? 'Online' : 'Offline'}
          </div>
        </div>
      </div>

      <div className="actionRow">
        <button className="primaryBtn" onClick={onStartLive}><Play size={16} /> Start live</button>
        <button className="secondaryBtn" onClick={onStopLive}><Square size={16} /> Stop</button>
        <button className="secondaryBtn" onClick={onOpenPlayback}><CalendarClock size={16} /> Playback</button>
      </div>

      <div className="detailGrid">
        <Detail label="Resolution" value={`${camera.width ?? '-'} × ${camera.height ?? '-'}`} />
        <Detail label="FPS" value={`${camera.fps ?? '-'} fps`} />
        <Detail label="Codec" value={codecLabel(camera.archive_type)} />
        <Detail label="Archive days" value={String(raw.archiveDays ?? '-')} />
        <Detail label="Bitrate" value={camera.bitrate ? `${Math.round(camera.bitrate / 1000)} kbps` : '-'} />
        <Detail label="Transcode" value={camera.transcode ? 'Enabled' : 'Copy'} />
      </div>

      <div className="recordingsCard">
        <div className="cardHeader">
          <div>
            <div className="eyebrow">Recent recordings</div>
            <h3>Indexed segments</h3>
          </div>
          <span className="chip">{recordings.length} files</span>
        </div>

        <div className="recordingList">
          {recordings.length === 0 ? (
            <div className="recordingEmpty">No recordings indexed yet.</div>
          ) : recordings.slice(0, 6).map((r) => (
            <div className="recordRow" key={r.id}>
              <div className="recordName">{r.file_path}</div>
              <div className="recordTime">{new Date(r.start_ts * 1000).toLocaleString()} → {new Date(r.end_ts * 1000).toLocaleString()}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

function Detail({ label, value }: { label: string; value: string }) {
  return <div className="detailCard"><span>{label}</span><strong>{value}</strong></div>
}
