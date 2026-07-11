/**
 * AttentionMap — XAI Attention Map 시각화 컴포넌트
 *
 * /explain/{pred_id} API에서 받은 attention_map_json을
 * recharts BarChart로 렌더링. 상위 피처 강조 표시.
 */
import { useState, useEffect } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, Cell, Tooltip, ResponsiveContainer,
} from 'recharts';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

const FEATURE_KO = {
  din:              'DIN\n(용존무기질소)',
  water_temp:       '수온',
  np_ratio:         'N:P 비율',
  dissolved_oxygen: 'DO\n(용존산소)',
  salinity:         '염분',
  dip:              'DIP\n(용존무기인)',
  precipitation:    '강수량',
  chlorophyll_a:    '클로로필-a',
};

const STATUS_COLORS = {
  ABOVE_THRESHOLD: '#ef4444',
  BELOW_THRESHOLD: '#f59e0b',
  UNKNOWN:         '#64748b',
};

function weightToColor(weight, maxWeight) {
  const ratio = weight / (maxWeight || 1);
  if (ratio > 0.7) return '#ef4444';
  if (ratio > 0.4) return '#f97316';
  if (ratio > 0.2) return '#f59e0b';
  return '#22c55e';
}

const CustomTooltip = ({ active, payload }) => {
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload;
  return (
    <div style={styles.tooltip}>
      <div style={{ fontWeight: 700, color: '#e2e8f0', marginBottom: 4 }}>
        {d.name}
      </div>
      <div style={{ color: '#94a3b8', fontSize: 12 }}>
        가중치: <span style={{ color: '#f59e0b' }}>{(d.weight * 100).toFixed(1)}%</span>
      </div>
      {d.value !== null && d.value !== undefined && (
        <div style={{ color: '#94a3b8', fontSize: 12 }}>
          측정값: {d.value} / 임계치: {d.threshold}
        </div>
      )}
    </div>
  );
};

export default function AttentionMap({ predId }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [causes, setCauses] = useState([]);

  useEffect(() => {
    if (!predId) return;
    setLoading(true);
    setError(null);

    fetch(`${API_BASE}/explain/${predId}`)
      .then(r => r.ok ? r.json() : Promise.reject(r.status))
      .then(json => {
        const attn = json.attention_map_json;
        if (attn?.tokens && attn?.weights) {
          const maxW = Math.max(...attn.weights);
          const chartData = attn.tokens.map((tok, i) => ({
            name:   FEATURE_KO[tok] ?? tok,
            weight: attn.weights[i],
            color:  weightToColor(attn.weights[i], maxW),
            key:    tok,
          }));
          // 가중치 내림차순 정렬
          chartData.sort((a, b) => b.weight - a.weight);
          setData(chartData);
        }
        setCauses(json.top_causes || []);
      })
      .catch(e => setError(`API 오류: ${e}`))
      .finally(() => setLoading(false));
  }, [predId]);

  if (!predId) return (
    <div style={styles.card}>
      <div style={styles.title}>XAI Attention Map</div>
      <div style={styles.empty}>예측 실행 후 결과를 조회하세요.</div>
    </div>
  );

  return (
    <div style={styles.card}>
      <div style={styles.header}>
        <div style={styles.title}>XAI Attention Map</div>
        <div style={styles.subtitle}>예측 #{predId} 주요 기여 변수</div>
      </div>

      {loading && <div style={styles.loading}>분석 중...</div>}
      {error   && <div style={styles.errorText}>{error}</div>}

      {data && (
        <>
          {/* 바 차트 */}
          <ResponsiveContainer width="100%" height={200}>
            <BarChart
              data={data}
              layout="vertical"
              margin={{ left: 80, right: 20, top: 8, bottom: 8 }}
            >
              <XAxis type="number" domain={[0, 0.5]} tick={{ fill: '#64748b', fontSize: 10 }}
                     tickFormatter={v => `${(v * 100).toFixed(0)}%`} />
              <YAxis type="category" dataKey="name" tick={{ fill: '#94a3b8', fontSize: 11 }}
                     width={80} />
              <Tooltip content={<CustomTooltip />} />
              <Bar dataKey="weight" radius={[0, 4, 4, 0]}>
                {data.map((entry, i) => (
                  <Cell key={i} fill={entry.color} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>

          {/* 원인 분석 카드 */}
          {causes.length > 0 && (
            <div style={styles.causesSection}>
              <div style={styles.causesTitle}>상위 원인 분석</div>
              <div style={styles.causesGrid}>
                {causes.slice(0, 3).map((c, i) => (
                  <div key={i} style={styles.causeCard}>
                    <div style={styles.causeRank}>#{i + 1}</div>
                    <div style={styles.causeFeat}>{FEATURE_KO[c.feature] ?? c.feature}</div>
                    <div style={styles.causeVal}>
                      {c.value != null ? `${c.value}` : 'N/A'}
                    </div>
                    <div style={{
                      ...styles.causeStatus,
                      color: STATUS_COLORS[c.status] ?? '#64748b',
                    }}>
                      {c.status === 'ABOVE_THRESHOLD' ? '▲ 초과' :
                       c.status === 'BELOW_THRESHOLD' ? '▼ 이하' : '-'}
                    </div>
                    <div style={styles.causeImp}>
                      기여도 {(c.importance * 100).toFixed(1)}%
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

const styles = {
  card: {
    background: '#1e293b', borderRadius: 12, padding: '20px 24px',
    border: '1px solid #334155',
  },
  header:   { marginBottom: 16 },
  title:    { color: '#e2e8f0', fontSize: 15, fontWeight: 700 },
  subtitle: { color: '#64748b', fontSize: 12, marginTop: 2 },
  loading:  { color: '#64748b', textAlign: 'center', padding: 24 },
  errorText:{ color: '#ef4444', fontSize: 12, textAlign: 'center', padding: 8 },
  empty:    { color: '#64748b', textAlign: 'center', padding: 32, fontSize: 13 },
  tooltip: {
    background: '#0f172a', border: '1px solid #334155', borderRadius: 8,
    padding: '10px 14px',
  },
  causesSection: { marginTop: 16, borderTop: '1px solid #334155', paddingTop: 14 },
  causesTitle:   { color: '#94a3b8', fontSize: 12, marginBottom: 10 },
  causesGrid:    { display: 'flex', gap: 10 },
  causeCard: {
    flex: 1, background: '#0f172a', borderRadius: 8, padding: '10px 12px',
    textAlign: 'center', border: '1px solid #1e293b',
  },
  causeRank:   { color: '#475569', fontSize: 10, marginBottom: 4 },
  causeFeat:   { color: '#e2e8f0', fontSize: 12, fontWeight: 600, marginBottom: 4 },
  causeVal:    { color: '#f59e0b', fontSize: 16, fontWeight: 700, marginBottom: 2 },
  causeStatus: { fontSize: 11, fontWeight: 600, marginBottom: 4 },
  causeImp:    { color: '#64748b', fontSize: 10 },
};
