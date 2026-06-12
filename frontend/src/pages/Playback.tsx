import { CalendarRange, PlayCircle, Download } from 'lucide-react'
import type { RecordingSegment } from '../types'

type Props = { streamId?: string; segments: RecordingSegment[] }

export function Playback({ streamId, segments }: Props) {
  return (
    <section className="content" id="playback">
      <div className="panelHead">
        <div>
          <div className="eyebrow">Playback</div>
          <h2 className="panelTitle">{streamId ?? 'Select a camera'}</h2>
          <div className="panelSub">Search indexed recordings and open clips</div>
        </div>
        <div className="chip"><CalendarRange size={14} /> Last 24h</div>
      </div>

      <div className="playbackCard">
        {segments.length === 0 ? (
          <div className="recordingEmpty">No playback segments in the selected window.</div>
        ) : segments.map((seg) => (
          <div className="playbackRow" key={seg.id}>
            <div>
              <div className="playbackName">{seg.file_path}</div>
              <div className="recordTime">{new Date(seg.start_ts * 1000).toLocaleString()} → {new Date(seg.end_ts * 1000).toLocaleString()}</div>
            </div>
            <div className="playbackActions">
              <button className="miniBtn" type="button"><PlayCircle size={16} /> Play</button>
              <button className="miniBtn" type="button"><Download size={16} /> Export</button>
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}
