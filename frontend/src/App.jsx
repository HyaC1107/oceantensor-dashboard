import { useWebSocket }   from './hooks/useWebSocket';
import { useState, useEffect } from 'react';
import TopBar             from './components/TopBar';
import SensorGrid         from './components/SensorGrid';
import WBIGauge           from './components/WBIGauge';
import TimeSeriesChart    from './components/TimeSeriesChart';
import NutrientPanel      from './components/NutrientPanel';
import AlertFeed          from './components/AlertFeed';
import EdgeStatusBar      from './components/EdgeStatusBar';
import XaiAnalysisTab     from './components/XaiAnalysisTab';
import SimulationTab      from './components/SimulationTab';
import RAGPanel           from './components/RAGPanel';
import RagDocsPanel       from './components/RagDocsPanel';
import AdminPage          from './pages/AdminPage';
import HudDashboard       from './components/hud/Dashboard';

const WS_URL  = import.meta.env.VITE_WS_URL  ?? 'ws://localhost:8000/ws/sensor';
const FARM_ID = import.meta.env.VITE_FARM_ID ?? 'A7';

const TABS = [
  { id: 'hud',       label: '🔴 어텐션 맵'   },
  { id: 'xai',       label: '🧠 XAI 분석'   },
  { id: 'sim',       label: '🧪 시뮬레이션' },
  { id: 'qa',        label: '💬 AI Q&A'     },
];

function useHash() {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const handler = () => setHash(window.location.hash);
    window.addEventListener('hashchange', handler);
    return () => window.removeEventListener('hashchange', handler);
  }, []);
  return hash;
}

export default function App() {
  const hash = useHash();
  const { data, status, history } = useWebSocket(WS_URL);
  const [activeTab, setActiveTab] = useState('hud');

  if (hash === '#admin') return <AdminPage />;

  return (
    <div style={styles.root}>
      <TopBar status={status} lastUpdate={data?.observed_at} farmId={FARM_ID} />

      {/* 탭 네비게이션 */}
      <div style={styles.tabBar}>
        {TABS.map(tab => (
          <button
            key={tab.id}
            style={{
              ...styles.tabBtn,
              ...(activeTab === tab.id ? styles.tabActive : {}),
            }}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <main style={styles.main}>
        {/* HUD 관제 탭 — 풀스크린 SF 관제센터 */}
        {activeTab === 'hud' && (
          <div style={{ flex: 1, display: 'flex', minHeight: 0, overflow: 'hidden' }}>
            <HudDashboard onGoXai={() => setActiveTab('xai')} />
          </div>
        )}

        {/* XAI 분석 탭 — 어장 선택형 풀사이즈 심층 분석 */}
        {activeTab === 'xai' && (
          <div style={styles.padded}>
            <XaiAnalysisTab />
          </div>
        )}

        {/* What-if 시뮬레이션 탭 */}
        {activeTab === 'sim' && (
          <div style={styles.padded}>
            <SimulationTab />
          </div>
        )}

        {/* AI Q&A 탭 */}
        {activeTab === 'qa' && (
          <div style={styles.padded}>
            <div style={styles.qaLayout}>
              <div style={{ flex: 2 }}>
                <RAGPanel />
              </div>
              <div style={{ flex: 1 }}>
                <RagDocsPanel />
              </div>
            </div>
          </div>
        )}
      </main>

      <EdgeStatusBar data={data} />
    </div>
  );
}

const styles = {
  root: {
    height: '100vh', overflow: 'hidden',
    display: 'flex', flexDirection: 'column',
    background: '#050B18', color: 'rgba(255,255,255,0.85)',
    fontFamily: "'Pretendard', 'Noto Sans KR', system-ui, sans-serif",
  },
  tabBar: {
    display: 'flex', gap: 0, flexShrink: 0,
    borderBottom: '1px solid rgba(0,229,255,0.12)',
    background: 'rgba(5,11,24,0.98)',
  },
  tabBtn: {
    background: 'none', border: 'none', color: 'rgba(255,255,255,0.28)',
    padding: '11px 22px', cursor: 'pointer', fontSize: 11,
    fontWeight: 700, borderBottom: '2px solid transparent',
    transition: 'color .15s, border-color .15s',
    fontFamily: 'Courier New,monospace', letterSpacing: 1.2,
  },
  tabActive: {
    color: '#00E5FF', borderBottom: '2px solid #00E5FF',
    textShadow: '0 0 12px rgba(0,229,255,0.5)',
  },
  main: {
    flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0,
  },
  dashLayout: {
    flex: 1, display: 'flex', overflow: 'hidden', minHeight: 0,
  },
  dashLeft: {
    flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'hidden',
  },
  padded: {
    flex: 1, overflowY: 'auto', padding: '20px 24px',
    display: 'flex', flexDirection: 'column', gap: 20,
  },
  midRow:    { display: 'flex', gap: 20, padding: '0 24px', alignItems: 'flex-start' },
  bottomRow: { display: 'flex', gap: 20, padding: '0 24px' },
  xaiLayout: { display: 'flex', gap: 20, alignItems: 'flex-start' },
  mapLayout: { display: 'flex', gap: 20, flexDirection: 'column' },
  qaLayout:  { display: 'flex', gap: 20, alignItems: 'stretch', minHeight: 0 },
};
