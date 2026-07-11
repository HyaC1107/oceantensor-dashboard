export const ANOMALY_SCORE = 0.76;
export const SEVERITY = 'WARNING'; // NORMAL | CAUTION | WARNING | DANGER

export const SENSOR_OVERLAY = {
  windSpeed: 12.4,
  windDir: 'NNE',
  seaTemp: 24.3,
  currentSpeed: 0.38,
};

export const CAUSATION_DATA = [
  { label: '용존산소 (DO)', value: 42, color: '#00E5FF' },
  { label: '염분',          value: 28, color: '#8B5CF6' },
  { label: '수온',          value: 22, color: '#FF8A3D' },
  { label: '일사량',        value: 5,  color: '#FFD700' },
  { label: '조류 속도',     value: 3,  color: '#FF4D4F' },
];

export const ANOMALY_SITES = [
  { id: 'A1', lat: 34.300, lon: 127.045, name: '완도 금일 1구역', score: 0.82 },
  { id: 'A2', lat: 34.803, lon: 127.325, name: '고흥 동강 1구역', score: 0.76 },
  { id: 'A3', lat: 34.795, lon: 126.018, name: '신안 비금 1구역', score: 0.68 },
];

export const NORMAL_SITES = [
  { id: 'N1', lat: 34.342, lon: 126.968, name: '완도 생일 1구역', score: 0.21 },
  { id: 'N2', lat: 34.305, lon: 126.118, name: '진도 조도 1구역', score: 0.33 },
  { id: 'N3', lat: 34.636, lon: 127.695, name: '여수 돌산 1구역', score: 0.44 },
  { id: 'N4', lat: 34.687, lon: 125.930, name: '신안 도초 1구역', score: 0.29 },
];

// 7일 시계열 (6시간 단위 → 28포인트)
const base = new Date('2026-06-13T00:00:00');
export const TIMELINE_DATA = Array.from({ length: 28 }, (_, i) => {
  const d = new Date(base.getTime() + i * 6 * 3600000);
  const t = i / 27;
  const noise = () => (Math.random() - 0.5) * 0.4;
  return {
    time: `${String(d.getMonth()+1).padStart(2,'0')}/${String(d.getDate()).padStart(2,'0')} ${String(d.getHours()).padStart(2,'0')}h`,
    temp:     +(21.5 + 3.2 * t + Math.sin(i * 0.45) * 1.1 + noise()).toFixed(2),
    do:       +(8.4  - 2.9 * t + Math.sin(i * 0.35) * 0.7 + noise()).toFixed(2),
    salinity: +(32.4 + Math.sin(i * 0.22) * 1.2 + noise() * 0.6).toFixed(2),
  };
});

// 실제 어업면허 데이터(kimFarmGeo.json) 기반 데모 이상 점수
// 실제 시스템에서는 AI 모델이 계산
export const DEMO_FARM_SCORES = {
  F04: { score: 0.84, severity: 'DANGER'  },
  F09: { score: 0.77, severity: 'WARNING' },
  F17: { score: 0.71, severity: 'WARNING' },
  F31: { score: 0.63, severity: 'WARNING' },
  F44: { score: 0.48, severity: 'CAUTION' },
  F58: { score: 0.42, severity: 'CAUTION' },
};

export const FLOW_STEPS = [
  { id: 'sensor', label: '센서 데이터',   icon: '📡', color: '#00E5FF', desc: '수온·DO·염분·조류' },
  { id: 'image',  label: '이미지 특징',   icon: '🔬', color: '#8B5CF6', desc: '엽체 RGB · NIR' },
  { id: 'fuse',   label: '특징 융합',     icon: '🔗', color: '#FFD700', desc: 'Cross-Attention' },
  { id: 'model',  label: 'Tiny Transformer', icon: '🧠', color: '#FF8A3D', desc: '4 ST-Block · d=256' },
  { id: 'out',    label: '이상 탐지',     icon: '⚡', color: '#FF4D4F', desc: 'WBI Score + Stage' },
];
