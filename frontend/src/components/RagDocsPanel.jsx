/**
 * RagDocsPanel — RAG 내장 지식베이스 문서 목록
 *
 * /rag/docs 로 황백화 지식베이스 문서 목록을 받아 표시.
 * 클릭 시 /rag/docs/{id} 로 본문 미리보기.
 * (AI Q&A 탭에서 "AI가 무엇을 근거로 답하는지" 투명성 제공)
 */
import { useState, useEffect } from 'react';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

export default function RagDocsPanel() {
  const [docs, setDocs] = useState([]);
  const [openId, setOpenId] = useState(null);
  const [body, setBody] = useState('');
  const [err, setErr] = useState(null);

  useEffect(() => {
    fetch(`${API_BASE}/rag/docs`)
      .then(r => r.ok ? r.json() : Promise.reject(r.status))
      .then(setDocs)
      .catch(e => setErr(`목록 로드 실패: ${e}`));
  }, []);

  const toggle = async (id) => {
    if (openId === id) { setOpenId(null); setBody(''); return; }
    setOpenId(id); setBody('불러오는 중...');
    try {
      const r = await fetch(`${API_BASE}/rag/docs/${id}`);
      const d = await r.json();
      setBody(d.content ?? '(본문 없음)');
    } catch (e) { setBody(`로드 실패: ${e}`); }
  };

  return (
    <div style={st.card}>
      <div style={st.accentBar} />
      <div style={st.scanline} />
      <div style={st.inner}>
        <div style={st.titleRow}>
          <div style={st.titleDot} />
          <div style={st.title}>📚 지식베이스</div>
        </div>
        <div style={st.sub}>
          RAG 검색 근거 문서&nbsp;<span style={st.cnt}>{docs.length}</span>건
        </div>
        {err && <div style={st.err}>{err}</div>}
        <div style={st.list}>
          {docs.map(d => (
            <div key={d.id} style={{
              ...st.item,
              borderColor: openId === d.id ? 'rgba(0,229,255,0.28)' : 'rgba(255,255,255,0.06)',
            }}>
              <button style={st.itemHead} onClick={() => toggle(d.id)}>
                <span style={{ ...st.itemTitle, color: openId === d.id ? '#00E5FF' : 'rgba(255,255,255,0.7)' }}>
                  {d.title}
                </span>
                <span style={{ ...st.chevron, color: openId === d.id ? '#00E5FF' : 'rgba(255,255,255,0.2)' }}>
                  {openId === d.id ? '▾' : '▸'}
                </span>
              </button>
              <div style={st.tags}>
                {(d.tags ?? []).map((t, i) => <span key={i} style={st.tag}>#{t}</span>)}
              </div>
              {openId === d.id && <div style={st.body}>{body}</div>}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

const st = {
  card: {
    position: 'relative',
    background: 'rgba(8,20,37,0.72)', backdropFilter: 'blur(18px)',
    border: '1px solid rgba(0,229,255,0.14)',
    borderRadius: 10, height: '100%',
    display: 'flex', flexDirection: 'column', overflow: 'hidden',
  },
  accentBar: {
    height: 2, flexShrink: 0,
    background: 'linear-gradient(90deg, #8B5CF6, #00E5FF, transparent)',
  },
  scanline: {
    position: 'absolute', inset: 0, pointerEvents: 'none',
    background: 'repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,229,255,0.008) 2px,rgba(0,229,255,0.008) 3px)',
  },
  inner: { padding: '14px 16px', display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0, position: 'relative' },
  titleRow: { display: 'flex', alignItems: 'center', gap: 8, marginBottom: 3 },
  titleDot: { width: 6, height: 6, borderRadius: '50%', background: '#8B5CF6', boxShadow: '0 0 8px #8B5CF6', flexShrink: 0 },
  title: { color: '#8B5CF6', fontSize: 13, fontWeight: 800, textShadow: '0 0 12px rgba(139,92,246,0.4)' },
  sub: { color: 'rgba(255,255,255,0.22)', fontSize: 9, letterSpacing: 2, fontFamily: 'Courier New,monospace', marginBottom: 12 },
  cnt: { color: '#00E5FF' },
  err: { color: '#FF4D4F', fontSize: 11, marginBottom: 8, fontFamily: 'Courier New,monospace' },
  list: { display: 'flex', flexDirection: 'column', gap: 6, overflowY: 'auto', flex: 1 },
  item: {
    background: 'rgba(5,11,24,0.6)', border: '1px solid',
    borderRadius: 7, padding: '8px 12px', transition: 'border-color .2s',
  },
  itemHead: {
    width: '100%', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    background: 'none', border: 'none', cursor: 'pointer', padding: 0,
  },
  itemTitle: { fontSize: 12, fontWeight: 600, textAlign: 'left', transition: 'color .2s' },
  chevron:   { fontSize: 10, transition: 'color .2s', flexShrink: 0 },
  tags: { display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 6 },
  tag: {
    color: 'rgba(139,92,246,0.8)', background: 'rgba(139,92,246,0.08)',
    fontSize: 9, padding: '1px 7px', borderRadius: 3,
    border: '1px solid rgba(139,92,246,0.2)', fontFamily: 'Courier New,monospace',
  },
  body: {
    color: 'rgba(255,255,255,0.5)', fontSize: 11, lineHeight: 1.7, marginTop: 8,
    borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: 8,
    whiteSpace: 'pre-wrap', maxHeight: 160, overflowY: 'auto',
  },
};
