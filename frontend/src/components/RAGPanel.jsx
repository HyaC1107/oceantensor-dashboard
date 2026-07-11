/**
 * RAGPanel — 황백화 Q&A 채팅 패널
 *
 * /rag/query API를 통해 황백화 관련 질문에 답변.
 */
import { useState, useRef, useEffect } from 'react';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

const QUICK_QUESTIONS = [
  '황백화가 뭐예요?',
  'DIN 임계치가 얼마예요?',
  '황백화 대응 방법은?',
  'N:P 비율이 낮으면?',
];

function modeBadge(mode) {
  if (!mode) return null;
  if (mode.startsWith('llm-gemini')) return { t: 'Gemini', bg: 'rgba(0,255,136,0.1)',  c: '#00FF88' };
  if (mode.startsWith('llm-claude')) return { t: 'Claude', bg: 'rgba(139,92,246,0.1)', c: '#8B5CF6' };
  return { t: 'RAG', bg: 'rgba(0,229,255,0.08)', c: '#00E5FF' };
}

function ChatBubble({ msg }) {
  const isUser = msg.role === 'user';
  const badge = !isUser ? modeBadge(msg.mode) : null;
  return (
    <div style={{ ...styles.bubble, ...(isUser ? styles.bubbleUser : styles.bubbleBot) }}>
      {!isUser && (
        <div style={styles.botLabel}>
          AI ASSISTANT
          {badge && (
            <span style={{ marginLeft: 6, fontSize: 8, padding: '1px 7px', borderRadius: 3,
                           background: badge.bg, color: badge.c, fontFamily: 'Courier New,monospace',
                           letterSpacing: 1, border: `1px solid ${badge.c}30` }}>{badge.t}</span>
          )}
        </div>
      )}
      <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.7 }}>{msg.content}</div>
      {msg.sources?.length > 0 && (
        <div style={styles.sources}>
          {msg.sources.map((s, i) => (
            <span key={i} style={styles.sourceTag}>{s}</span>
          ))}
        </div>
      )}
    </div>
  );
}

export default function RAGPanel() {
  const [messages, setMessages] = useState([
    {
      role: 'bot',
      content: '안녕하세요! 황백화 조기경보 AI입니다.\n황백화 관련 질문이 있으시면 언제든지 물어보세요.',
      sources: [],
    },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const sendQuery = async (query) => {
    if (!query.trim() || loading) return;
    const q = query.trim();
    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: q, sources: [] }]);
    setLoading(true);

    try {
      const res = await fetch(`${API_BASE}/rag/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: q, top_k: 3 }),
      });
      if (!res.ok) throw new Error(`${res.status}`);
      const data = await res.json();
      setMessages(prev => [...prev, {
        role: 'bot',
        content: data.answer,
        sources: data.sources || [],
        mode: data.mode,
      }]);
    } catch (e) {
      setMessages(prev => [...prev, {
        role: 'bot',
        content: `오류가 발생했습니다: ${e.message}`,
        sources: [],
      }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={styles.card}>
      <div style={styles.accentBar} />
      <div style={styles.scanline} />
      <div style={styles.header}>
        <div style={styles.titleRow}>
          <div style={styles.titleDot} />
          <div style={styles.title}>💬 AI Q&amp;A</div>
        </div>
        <div style={styles.subtitle}>RAG · 황백화 지식베이스 검색</div>
      </div>

      {/* 빠른 질문 */}
      <div style={styles.quickRow}>
        {QUICK_QUESTIONS.map((q, i) => (
          <button key={i} style={styles.quickBtn} onClick={() => sendQuery(q)}>{q}</button>
        ))}
      </div>

      {/* 메시지 영역 */}
      <div style={styles.messages}>
        {messages.map((msg, i) => <ChatBubble key={i} msg={msg} />)}
        {loading && (
          <div style={styles.typing}>◆ ◆ ◆</div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* 입력 */}
      <div style={styles.inputRow}>
        <input
          style={styles.input}
          placeholder="황백화에 대해 질문하세요..."
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && !e.shiftKey && sendQuery(input)}
          disabled={loading}
        />
        <button
          style={{ ...styles.sendBtn, opacity: loading ? 0.4 : 1 }}
          onClick={() => sendQuery(input)}
          disabled={loading}
        >SEND</button>
      </div>
    </div>
  );
}

const styles = {
  card: {
    position: 'relative',
    background: 'rgba(8,20,37,0.72)', backdropFilter: 'blur(18px)',
    border: '1px solid rgba(0,229,255,0.14)',
    borderRadius: 10, display: 'flex', flexDirection: 'column',
    height: '100%', overflow: 'hidden',
  },
  accentBar: {
    height: 2, flexShrink: 0,
    background: 'linear-gradient(90deg, #00E5FF, #8B5CF6, transparent)',
  },
  scanline: {
    position: 'absolute', inset: 0, pointerEvents: 'none',
    background: 'repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,229,255,0.008) 2px,rgba(0,229,255,0.008) 3px)',
  },
  header:   { padding: '12px 18px 0', marginBottom: 8, position: 'relative' },
  titleRow: { display: 'flex', alignItems: 'center', gap: 8, marginBottom: 2 },
  titleDot: { width: 6, height: 6, borderRadius: '50%', background: '#00E5FF', boxShadow: '0 0 8px #00E5FF', flexShrink: 0 },
  title:    { color: '#00E5FF', fontSize: 13, fontWeight: 800, textShadow: '0 0 12px rgba(0,229,255,0.4)' },
  subtitle: { color: 'rgba(255,255,255,0.22)', fontSize: 9, letterSpacing: 2, fontFamily: 'Courier New,monospace' },
  quickRow: { display: 'flex', gap: 5, flexWrap: 'wrap', margin: '0 16px 10px', position: 'relative' },
  quickBtn: {
    background: 'rgba(0,229,255,0.05)', border: '1px solid rgba(0,229,255,0.18)',
    borderRadius: 4, color: 'rgba(0,229,255,0.7)', fontSize: 10, padding: '4px 10px',
    cursor: 'pointer', fontFamily: "'Pretendard','Noto Sans KR',sans-serif",
  },
  messages: {
    flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column',
    gap: 10, padding: '0 14px', minHeight: 0,
  },
  bubble: { borderRadius: 8, padding: '10px 14px', maxWidth: '92%', fontSize: 13, lineHeight: 1.6 },
  bubbleUser: {
    background: 'rgba(0,229,255,0.1)', color: 'rgba(255,255,255,0.9)',
    alignSelf: 'flex-end', border: '1px solid rgba(0,229,255,0.25)',
  },
  bubbleBot: {
    background: 'rgba(5,11,24,0.85)', color: 'rgba(255,255,255,0.8)',
    alignSelf: 'flex-start', border: '1px solid rgba(255,255,255,0.06)',
  },
  botLabel: {
    color: 'rgba(0,229,255,0.45)', fontSize: 8, marginBottom: 5,
    fontFamily: 'Courier New,monospace', letterSpacing: 2, display: 'flex', alignItems: 'center',
  },
  sources: { display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 8 },
  sourceTag: {
    background: 'rgba(0,229,255,0.08)', color: 'rgba(0,229,255,0.6)', fontSize: 9,
    padding: '2px 7px', borderRadius: 3, border: '1px solid rgba(0,229,255,0.15)',
    fontFamily: 'Courier New,monospace',
  },
  typing: {
    padding: '8px 14px', color: 'rgba(0,229,255,0.4)', fontSize: 11,
    alignSelf: 'flex-start', fontFamily: 'Courier New,monospace', letterSpacing: 4,
  },
  inputRow: { display: 'flex', gap: 8, margin: '10px 14px 14px', position: 'relative' },
  input: {
    flex: 1, background: 'rgba(5,11,24,0.8)', border: '1px solid rgba(0,229,255,0.2)',
    borderRadius: 6, padding: '9px 13px', color: 'rgba(255,255,255,0.85)', fontSize: 13,
    outline: 'none',
  },
  sendBtn: {
    background: 'rgba(0,229,255,0.12)', border: '1px solid rgba(0,229,255,0.35)',
    borderRadius: 6, color: '#00E5FF', padding: '9px 18px', fontWeight: 700,
    cursor: 'pointer', fontSize: 10, fontFamily: 'Courier New,monospace', letterSpacing: 2,
  },
};
