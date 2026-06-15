import React from 'react';
import { Shield, ShieldAlert, ShieldOff, Activity, AlertTriangle, CheckCircle, Wifi, WifiOff } from 'lucide-react';

export type StreamHealthState = 'REGISTERED' | 'CONNECTING' | 'ONLINE' | 'DEGRADED' | 'RECOVERING' | 'OFFLINE' | 'FAILED' | 'DISABLED';

interface StreamHealthBadgeProps {
  status: StreamHealthState;
  errorMessage?: string | null;
}

export function StreamHealthBadge({ status, errorMessage }: StreamHealthBadgeProps) {
  const getBadgeConfig = () => {
    switch (status) {
      case 'ONLINE':
        return {
          bg: 'rgba(16, 185, 129, 0.15)',
          border: 'rgba(16, 185, 129, 0.3)',
          color: '#34d399',
          icon: <Wifi size={12} className="mr-1" />,
          label: 'Online',
          pulse: true,
        };
      case 'CONNECTING':
        return {
          bg: 'rgba(59, 130, 246, 0.15)',
          border: 'rgba(59, 130, 246, 0.3)',
          color: '#60a5fa',
          icon: <Activity size={12} className="mr-1 spin" />,
          label: 'Connecting',
          pulse: false,
        };
      case 'RECOVERING':
        return {
          bg: 'rgba(245, 158, 11, 0.15)',
          border: 'rgba(245, 158, 11, 0.3)',
          color: '#fbbf24',
          icon: <Activity size={12} className="mr-1 spin" />,
          label: 'Recovering',
          pulse: false,
        };
      case 'DEGRADED':
        return {
          bg: 'rgba(239, 68, 68, 0.15)',
          border: 'rgba(239, 68, 68, 0.3)',
          color: '#f87171',
          icon: <AlertTriangle size={12} className="mr-1" />,
          label: 'Degraded',
          pulse: true,
        };
      case 'FAILED':
        return {
          bg: 'rgba(220, 38, 38, 0.2)',
          border: 'rgba(220, 38, 38, 0.4)',
          color: '#fca5a5',
          icon: <ShieldAlert size={12} className="mr-1" />,
          label: 'Failed',
          pulse: false,
        };
      case 'OFFLINE':
        return {
          bg: 'rgba(107, 114, 128, 0.15)',
          border: 'rgba(107, 114, 128, 0.3)',
          color: '#9ca3af',
          icon: <WifiOff size={12} className="mr-1" />,
          label: 'Offline',
          pulse: false,
        };
      case 'DISABLED':
        return {
          bg: 'rgba(107, 114, 128, 0.1)',
          border: 'rgba(107, 114, 128, 0.2)',
          color: '#6b7280',
          icon: <ShieldOff size={12} className="mr-1" />,
          label: 'Disabled',
          pulse: false,
        };
      case 'REGISTERED':
      default:
        return {
          bg: 'rgba(139, 92, 246, 0.15)',
          border: 'rgba(139, 92, 246, 0.3)',
          color: '#a78bfa',
          icon: <CheckCircle size={12} className="mr-1" />,
          label: 'Registered',
          pulse: false,
        };
    }
  };

  const config = getBadgeConfig();

  return (
    <div
      title={errorMessage ? `Status detail: ${errorMessage}` : `Stream is ${config.label}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        padding: '2px 8px',
        borderRadius: '9999px',
        fontSize: '11px',
        fontWeight: 600,
        backgroundColor: config.bg,
        border: `1px solid ${config.border}`,
        color: config.color,
        backdropFilter: 'blur(4px)',
        userSelect: 'none',
        transition: 'all 0.2s ease',
      }}
    >
      {config.pulse && (
        <span
          style={{
            display: 'inline-block',
            width: '6px',
            height: '6px',
            borderRadius: '50%',
            backgroundColor: config.color,
            marginRight: '6px',
            boxShadow: `0 0 8px ${config.color}`,
            animation: 'pulse 1.5s infinite ease-in-out',
          }}
          className="dotPulse"
        />
      )}
      {config.icon}
      {config.label}
    </div>
  );
}
