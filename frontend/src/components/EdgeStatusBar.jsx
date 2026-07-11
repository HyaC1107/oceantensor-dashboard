import { motion } from 'framer-motion';

function StatusChip({ label, value, ok }) {
  const col = ok ? '#00FF88' : '#FF4D4F';
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 7,
      background: ok ? 'rgba(0,255,136,0.05)' : 'rgba(255,77,79,0.05)',
      border: `1px solid ${col}20`,
      borderRadius: 4, padding: '3px 10px',
    }}>
      <motion.div
        style={{ width: 5, height: 5, borderRadius: '50%', background: col, boxShadow: `0 0 6px ${col}`, flexShrink: 0 }}
        animate={!ok ? { opacity: [0.3, 1, 0.3] } : {}}
        transition={{ duration: 1.2, repeat: Infinity }}
      />
      <div>
        <div style={{ fontSize: 7, color: 'rgba(255,255,255,0.22)', letterSpacing: 2, fontFamily: 'Courier New,monospace' }}>
          {label}
        </div>
        <div style={{ fontSize: 10, fontWeight: 700, color: col, fontFamily: 'Courier New,monospace' }}>
          {value}
        </div>
      </div>
    </div>
  );
}

export default function EdgeStatusBar({ data }) {
  const edge     = data?.edge_status ?? 'offline';
  const mqtt     = data?.mqtt_status ?? 'disconnected';
  const lat      = data?.inference_latency_ms ?? null;
  const salinity = data?.salinity ?? null;

  return (
    <div style={st.bar}>
      <div style={st.scanline} />
      <div style={st.left}>
        <span style={st.sysLabel}>EDGE STATUS</span>
        <div style={st.vSep} />
      </div>
      <div style={st.chips}>
        <StatusChip label="JETSON"    value={edge.toUpperCase()} ok={edge === 'online'} />
        <StatusChip label="MQTT"      value={mqtt.toUpperCase()} ok={mqtt === 'connected'} />
        <StatusChip label="INFERENCE" value={lat !== null ? `${lat} ms` : '— ms'} ok={lat !== null && lat < 50} />
        <StatusChip label="SALINITY"  value={salinity !== null ? `${salinity.toFixed(1)} PSU` : '— PSU'}
          ok={salinity !== null && salinity >= 30 && salinity <= 35} />
      </div>
      <div style={st.right}>
        <div style={st.vSep} />
        <span style={st.sysLabel}>TTORI OCEAN WATCH</span>
        <span style={st.ver}>v1.0</span>
      </div>
    </div>
  );
}

const st = {
  bar: {
    position: 'relative', flexShrink: 0,
    height: 38, display: 'flex', alignItems: 'center', gap: 8,
    padding: '0 16px',
    background: 'rgba(5,11,24,0.98)',
    borderTop: '1px solid rgba(0,229,255,0.12)',
    overflow: 'hidden',
  },
  scanline: {
    position: 'absolute', inset: 0, pointerEvents: 'none',
    background: 'repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,229,255,0.008) 2px,rgba(0,229,255,0.008) 3px)',
  },
  left:  { display: 'flex', alignItems: 'center', gap: 8 },
  right: { display: 'flex', alignItems: 'center', gap: 6, marginLeft: 'auto' },
  chips: { display: 'flex', alignItems: 'center', gap: 6 },
  sysLabel: {
    fontSize: 7, color: 'rgba(0,229,255,0.35)', letterSpacing: 3,
    fontFamily: 'Courier New,monospace', whiteSpace: 'nowrap',
  },
  ver: { fontSize: 8, color: 'rgba(255,255,255,0.15)', fontFamily: 'Courier New,monospace' },
  vSep: { width: 1, height: 18, background: 'rgba(0,229,255,0.15)' },
};
