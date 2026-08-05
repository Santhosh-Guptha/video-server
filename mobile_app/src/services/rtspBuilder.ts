import type { CameraConfig, PlaybackParams, StreamMode } from '../types/camera';

/**
 * Builds the exact RTSP URL for Live Streaming based on NVR Brand and active mode (Local IP vs Remote DDNS).
 */
export function buildLiveRtspUrl(cam: CameraConfig, mode: StreamMode = 'remote'): string {
  const host = mode === 'local' ? cam.localIp : cam.remoteHost;
  const port = cam.rtspPort || 554;
  const user = encodeURIComponent(cam.username);
  const pass = encodeURIComponent(cam.password);
  const auth = user && pass ? `${user}:${pass}@` : '';
  const ch = cam.channel || 1;
  const quality = cam.streamQuality || 'main';

  switch (cam.nvrBrand) {
    case 'hikvision': {
      const streamId = quality === 'main' ? `${ch}01` : `${ch}02`;
      return `rtsp://${auth}${host}:${port}/Streaming/channels/${streamId}`;
    }
    case 'dahua': {
      const subtype = quality === 'main' ? 0 : 1;
      return `rtsp://${auth}${host}:${port}/cam/realmonitor?channel=${ch}&subtype=${subtype}`;
    }
    case 'uniview': {
      const stream = quality === 'main' ? 0 : 1;
      return `rtsp://${auth}${host}:${port}/unicast/c${ch}/s${stream}/live`;
    }
    case 'onvif':
    case 'custom':
    default: {
      return `rtsp://${auth}${host}:${port}/h264/ch${ch}/${quality}/av_stream`;
    }
  }
}

/**
 * Formats a Date object into Hikvision RTSP timestamp format: YYYYMMDDTHHMMSSZ
 */
function formatHikvisionTimestamp(dateStr: string, timeStr: string): string {
  // dateStr: YYYY-MM-DD, timeStr: HH:mm:ss
  const cleanDate = dateStr.replace(/-/g, '');
  const cleanTime = timeStr.replace(/:/g, '');
  return `${cleanDate}T${cleanTime}Z`;
}

/**
 * Formats a Date object into Dahua RTSP timestamp format: YYYY-MM-DD_HH:MM:SS
 */
function formatDahuaTimestamp(dateStr: string, timeStr: string): string {
  return `${dateStr}_${timeStr}`;
}

/**
 * Builds the NVR Playback RTSP Stream URL with start and end time parameters.
 */
export function buildPlaybackRtspUrl(cam: CameraConfig, params: PlaybackParams, mode: StreamMode = 'remote'): string {
  const host = mode === 'local' ? cam.localIp : cam.remoteHost;
  const port = cam.rtspPort || 554;
  const user = encodeURIComponent(cam.username);
  const pass = encodeURIComponent(cam.password);
  const auth = user && pass ? `${user}:${pass}@` : '';
  const ch = cam.channel || 1;

  switch (cam.nvrBrand) {
    case 'hikvision': {
      const start = formatHikvisionTimestamp(params.startDate, params.startTime);
      const end = formatHikvisionTimestamp(params.endDate, params.endTime);
      const trackId = `${ch}01`;
      return `rtsp://${auth}${host}:${port}/Streaming/tracks/${trackId}?starttime=${start}&endtime=${end}`;
    }
    case 'dahua': {
      const start = formatDahuaTimestamp(params.startDate, params.startTime);
      const end = formatDahuaTimestamp(params.endDate, params.endTime);
      return `rtsp://${auth}${host}:${port}/cam/realmonitor?channel=${ch}&subtype=0&starttime=${start}&endtime=${end}`;
    }
    case 'uniview':
    case 'onvif':
    case 'custom':
    default: {
      const start = `${params.startDate}T${params.startTime}Z`;
      const end = `${params.endDate}T${params.endTime}Z`;
      return `rtsp://${auth}${host}:${port}/playback/ch${ch}?starttime=${start}&endtime=${end}`;
    }
  }
}

/**
 * Converts standard rtsp:// link to vlc:// deep link for direct opening on mobile Android/iOS VLC app.
 */
export function getVlcDeepLink(rtspUrl: string): string {
  return `vlc://${rtspUrl}`;
}
