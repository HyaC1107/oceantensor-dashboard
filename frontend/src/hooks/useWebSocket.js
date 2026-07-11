import { useState, useEffect, useRef, useCallback } from 'react';

export function useWebSocket(url) {
  const [data, setData] = useState(null);
  const [status, setStatus] = useState('connecting');
  const [history, setHistory] = useState([]);
  const wsRef = useRef(null);
  const retryRef = useRef(null);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    wsRef.current = new WebSocket(url);

    wsRef.current.onopen = () => {
      setStatus('connected');
      clearTimeout(retryRef.current);
    };

    wsRef.current.onmessage = (e) => {
      const payload = JSON.parse(e.data);
      setData(payload);
      setHistory((prev) => {
        const next = [...prev, { ...payload, ts: Date.now() }];
        return next.slice(-60); // 최대 60개 유지 (5분치)
      });
    };

    wsRef.current.onerror = () => setStatus('error');

    wsRef.current.onclose = () => {
      setStatus('disconnected');
      retryRef.current = setTimeout(connect, 3000);
    };
  }, [url]);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(retryRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { data, status, history };
}
