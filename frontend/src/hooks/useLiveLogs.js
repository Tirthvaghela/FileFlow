import { useCallback, useEffect, useRef, useState } from "react";
import { getLogs, wsUrl } from "../services/api.js";

export function useLiveLogs(limit = 50) {
  const [logs, setLogs] = useState([]);
  const [connected, setConnected] = useState(false);

  const refresh = useCallback(() => {
    getLogs(limit)
      .then(setLogs)
      .catch(() => {});
  }, [limit]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    let socket;
    let retryTimer;
    let cancelled = false;

    function connect() {
      socket = new WebSocket(wsUrl());
      socket.onopen = () => setConnected(true);
      socket.onclose = () => {
        setConnected(false);
        if (!cancelled) retryTimer = setTimeout(connect, 3000);
      };
      socket.onerror = () => socket.close();
      socket.onmessage = (event) => {
        try {
          const entry = JSON.parse(event.data);
          setLogs((prev) => [entry, ...prev].slice(0, limit));
        } catch {
          // ignore malformed payloads
        }
      };
    }

    connect();
    return () => {
      cancelled = true;
      clearTimeout(retryTimer);
      socket?.close();
    };
  }, [limit]);

  return { logs, connected, refresh };
}
