import React from 'react';
import { Settings, Cpu, Wifi, Zap, Activity } from 'lucide-react';

export type PlayerStats = {
  resolution?: string;
  fps?: number;
  bitrate?: number; // in kbps
  rtt?: number; // in ms
  packetLoss?: number; // 0 to 1
  jitter?: number; // in ms
  protocol?: string;
  reconnections?: number;
};

interface SessionStatsOverlayProps {
  stats: PlayerStats;
  visible: boolean;
  onToggle: () => void;
}

export function SessionStatsOverlay({ stats, visible, onToggle }: SessionStatsOverlayProps) {
  if (!visible) {
    return (
      <button
        onClick={onToggle}
        title="Show connection statistics"
        style={{
          position: 'absolute',
          bottom: '12px',
          right: '12px',
          zIndex: 10,
          background: 'rgba(15, 23, 42, 0.6)',
          backdropFilter: 'blur(8px)',
          border: '1px solid rgba(255, 255, 255, 0.1)',
          borderRadius: '8px',
          padding: '6px',
          color: '#e2e8f0',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          transition: 'all 0.2s ease',
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.backgroundColor = 'rgba(15, 23, 42, 0.8)';
          e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.2)';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.backgroundColor = 'rgba(15, 23, 42, 0.6)';
          e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.1)';
        }}
      >
        <Activity size={14} />
      </button>
    );
  }

  const formatPacketLoss = (loss?: number) => {
    if (loss === undefined) return '0.00%';
    return `${(loss * 100).toFixed(2)}%`;
  };

  return (
    <div
      style={{
        position: 'absolute',
        bottom: '12px',
        right: '12px',
        zIndex: 10,
        width: '210px',
        background: 'rgba(15, 23, 42, 0.85)',
        backdropFilter: 'blur(12px)',
        border: '1px solid rgba(255, 255, 255, 0.15)',
        borderRadius: '12px',
        padding: '12px',
        color: '#f8fafc',
        fontFamily: 'Inter, system-ui, sans-serif',
        fontSize: '11px',
        boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.5)',
        transition: 'all 0.2s ease',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          borderBottom: '1px solid rgba(255, 255, 255, 0.1)',
          paddingBottom: '8px',
          marginBottom: '8px',
        }}
      >
        <span style={{ fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase', color: '#94a3b8', display: 'flex', alignItems: 'center' }}>
          <Zap size={12} className="mr-1" style={{ color: '#fbbf24' }} /> Stream Stats
        </span>
        <button
          onClick={onToggle}
          style={{
            background: 'none',
            border: 'none',
            color: '#64748b',
            cursor: 'pointer',
            padding: '2px',
            fontSize: '10px',
            fontWeight: 600,
          }}
          onMouseEnter={(e) => { e.currentTarget.style.color = '#cbd5e1'; }}
          onMouseLeave={(e) => { e.currentTarget.style.color = '#64748b'; }}
        >
          Hide
        </button>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span style={{ color: '#64748b' }}>Protocol</span>
          <span style={{ fontWeight: 600, color: '#38bdf8' }}>{stats.protocol ?? 'WHEP'}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span style={{ color: '#64748b' }}>Resolution</span>
          <span style={{ fontWeight: 600 }}>{stats.resolution ?? 'N/A'}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span style={{ color: '#64748b' }}>FPS</span>
          <span style={{ fontWeight: 600, color: (stats.fps ?? 0) < 10 ? '#f87171' : '#34d399' }}>
            {stats.fps !== undefined ? Math.round(stats.fps) : 'N/A'}
          </span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span style={{ color: '#64748b' }}>Bitrate</span>
          <span style={{ fontWeight: 600 }}>
            {stats.bitrate !== undefined ? `${Math.round(stats.bitrate)} kbps` : 'N/A'}
          </span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span style={{ color: '#64748b' }}>Latency (RTT)</span>
          <span style={{ fontWeight: 600, color: (stats.rtt ?? 0) > 150 ? '#fbbf24' : '#34d399' }}>
            {stats.rtt !== undefined ? `${Math.round(stats.rtt)} ms` : 'N/A'}
          </span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span style={{ color: '#64748b' }}>Jitter</span>
          <span style={{ fontWeight: 600 }}>
            {stats.jitter !== undefined ? `${stats.jitter.toFixed(1)} ms` : 'N/A'}
          </span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span style={{ color: '#64748b' }}>Packet Loss</span>
          <span style={{ fontWeight: 600, color: (stats.packetLoss ?? 0) > 0.02 ? '#f87171' : '#f8fafc' }}>
            {formatPacketLoss(stats.packetLoss)}
          </span>
        </div>
        {stats.reconnections !== undefined && stats.reconnections > 0 && (
          <div style={{ display: 'flex', justifyContent: 'space-between', borderTop: '1px solid rgba(255, 255, 255, 0.05)', paddingTop: '4px' }}>
            <span style={{ color: '#64748b' }}>Reconnects</span>
            <span style={{ fontWeight: 600, color: '#fbbf24' }}>{stats.reconnections}</span>
          </div>
        )}
      </div>
    </div>
  );
}
