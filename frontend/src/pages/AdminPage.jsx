import { useState } from 'react';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

const PRIORITY_COLOR = {
  '최우선': '#22c55e',
  '높음':   '#3b82f6',
  '중간':   '#f59e0b',
  '선택':   '#94a3b8',
  '보류':   '#475569',
};

export default function AdminPage() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [checkedAt, setCheckedAt] = useState(null);

  async function runCheck() {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/admin/api-status`);
      const data = await res.json();
      setItems(data);
      setCheckedAt(new Date().toLocaleTimeString('ko-KR'));
    } catch (e) {
      alert('백엔드 연결 실패: ' + e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={s.page}>
      <div style={s.header}>
        <div>
          <a href="#" style={s.backLink}>← 대시보드로</a>
          <div style={s.title}>API 키 상태 관리</div>
          <div style={s.sub}>
            {checkedAt ? `마지막 확인: ${checkedAt}` : '.env에 등록된 공공API 키를 실시간으로 검증합니다.'}
          </div>
        </div>
        <button style={loading ? s.btnDisabled : s.btn} onClick={runCheck} disabled={loading}>
          {loading ? '확인 중...' : '전체 API 체크'}
        </button>
      </div>

      {items.length === 0 && !loading && (
        <div style={s.empty}>버튼을 눌러 API 상태를 확인하세요.</div>
      )}

      {loading && (
        <div style={s.empty}>각 API에 실제 요청 중... 잠시만 기다려주세요.</div>
      )}

      <div style={s.grid}>
        {items.map((item) => (
          <ApiCard key={item.key} item={item} />
        ))}
      </div>
    </div>
  );
}

function ApiCard({ item }) {
  const ok = item.ok;
  const isPending = ok === null;
  const borderColor = isPending ? '#334155' : ok ? '#22c55e33' : '#ef444433';
  const statusColor = isPending ? '#64748b' : ok ? '#22c55e' : '#ef4444';
  const statusText  = isPending ? '⚙ 설정 필요' : ok ? '✓ 정상' : '✗ 실패';
  return (
    <div style={{ ...s.card, borderColor }}>
      <div style={s.cardTop}>
        <span style={{ ...s.badge, background: PRIORITY_COLOR[item.priority] ?? '#64748b' }}>
          {item.priority}
        </span>
        <span style={{ ...s.status, color: statusColor }}>
          {statusText}
        </span>
      </div>
      <div style={s.cardName}>{item.name}</div>
      <div style={s.cardProvider}>{item.provider}</div>
      <div style={s.cardDesc}>{item.desc}</div>
      <div style={s.cardMeta}>
        <span style={s.envVar}>{item.env_var}</span>
        {item.item_count !== undefined && ok && (
          <span style={s.metaVal}>응답 {item.item_count}건</span>
        )}
        {item.status_code && (
          <span style={s.metaVal}>HTTP {item.status_code}</span>
        )}
      </div>
      {(isPending || !ok) && item.message && (
        <div style={{ ...s.errMsg, background: isPending ? '#1e293b' : '#2d1212', color: isPending ? '#94a3b8' : '#fca5a5' }}>
          {item.message}
        </div>
      )}
    </div>
  );
}

const s = {
  page: {
    minHeight: '100vh', background: '#0a1628', color: '#e2e8f0',
    fontFamily: "'Pretendard', 'Noto Sans KR', system-ui, sans-serif",
    padding: '32px 24px',
  },
  header: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
    marginBottom: 32,
  },
  title: { fontSize: 24, fontWeight: 700, color: '#f8fafc', marginBottom: 6 },
  sub: { fontSize: 13, color: '#94a3b8' },
  btn: {
    padding: '10px 24px', background: '#3b82f6', color: '#fff',
    border: 'none', borderRadius: 8, fontSize: 14, fontWeight: 600,
    cursor: 'pointer',
  },
  btnDisabled: {
    padding: '10px 24px', background: '#334155', color: '#64748b',
    border: 'none', borderRadius: 8, fontSize: 14, fontWeight: 600,
    cursor: 'not-allowed',
  },
  empty: {
    textAlign: 'center', color: '#475569', fontSize: 14, padding: '60px 0',
  },
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
    gap: 16,
  },
  card: {
    background: '#0f1f3d', border: '1px solid #1e3a5f',
    borderRadius: 12, padding: 20,
    display: 'flex', flexDirection: 'column', gap: 8,
  },
  cardTop: { display: 'flex', justifyContent: 'space-between', alignItems: 'center' },
  badge: {
    fontSize: 11, fontWeight: 700, padding: '2px 8px',
    borderRadius: 4, color: '#fff',
  },
  status: { fontSize: 13, fontWeight: 700 },
  cardName: { fontSize: 15, fontWeight: 600, color: '#f1f5f9' },
  cardProvider: { fontSize: 12, color: '#64748b' },
  cardDesc: { fontSize: 13, color: '#94a3b8', lineHeight: 1.5 },
  cardMeta: { display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 4 },
  envVar: {
    fontSize: 11, fontFamily: 'monospace', background: '#1e3a5f',
    color: '#7dd3fc', padding: '2px 6px', borderRadius: 4,
  },
  metaVal: {
    fontSize: 11, color: '#64748b', padding: '2px 6px',
    background: '#1e293b', borderRadius: 4,
  },
  errMsg: {
    fontSize: 11, color: '#fca5a5', background: '#2d1212',
    padding: '6px 8px', borderRadius: 6, wordBreak: 'break-all',
    marginTop: 4,
  },
  backLink: {
    color: '#64748b', fontSize: 12, textDecoration: 'none',
    display: 'inline-block', marginBottom: 8,
  },
};
