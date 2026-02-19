import { useState, useEffect, useCallback, useRef } from 'react';
import { ChatEvent } from '../types/events';

interface UseEventBusOptions {
  wsUrl?: string;
  httpEndpoint?: string;
  onEvent?: (event: ChatEvent) => void;
  enabled?: boolean;
}

interface EventBusState {
  connected: boolean;
  mode: 'ws' | 'http' | 'offline';
  pendingEvents: ChatEvent[];
  error: string | null;
}

export const useEventBus = (options: UseEventBusOptions = {}) => {
  const {
    wsUrl = 'ws://localhost:8084/ws',
    httpEndpoint = 'http://localhost:8084/api/events',
    onEvent,
    enabled = true,
  } = options;

  const [state, setState] = useState<EventBusState>({
    connected: false,
    mode: 'offline',
    pendingEvents: [],
    error: null,
  });

  const wsRef = useRef<WebSocket | null>(null);
  const eventIdSet = useRef<Set<string>>(new Set());
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const connect = useCallback(() => {
    if (!enabled) {
      setState((s) => ({ ...s, mode: 'offline', connected: false }));
      return;
    }

    try {
      const ws = new WebSocket(wsUrl);
      
      ws.onopen = () => {
        setState((s) => ({ ...s, connected: true, mode: 'ws', error: null }));
      };
      
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (isChatEvent(data)) {
            if (!eventIdSet.current.has(data.event_id)) {
              eventIdSet.current.add(data.event_id);
              setState((s) => ({
                ...s,
                pendingEvents: [...s.pendingEvents, data],
              }));
              onEvent?.(data);
            }
          }
        } catch (e) {
          console.error('Error parsing WS message:', e);
        }
      };
      
      ws.onclose = () => {
        setState((s) => ({ ...s, connected: false, mode: 'http' }));
        
        reconnectTimeoutRef.current = setTimeout(() => {
          connect();
        }, 3000);
      };
      
      ws.onerror = () => {
        setState((s) => ({ ...s, connected: false, mode: 'http' }));
      };
      
      wsRef.current = ws;
    } catch (e) {
      setState((s) => ({
        ...s,
        connected: false,
        mode: 'http',
        error: 'WS connection failed, using HTTP fallback',
      }));
    }
  }, [wsUrl, enabled, onEvent]);

  const fetchEvents = useCallback(async () => {
    try {
      const response = await fetch(httpEndpoint);
      if (response.ok) {
        const events = await response.json();
        events.forEach((event: ChatEvent) => {
          if (!eventIdSet.current.has(event.event_id)) {
            eventIdSet.current.add(event.event_id);
            setState((s) => ({
              ...s,
              pendingEvents: [...s.pendingEvents, event],
            }));
            onEvent?.(event);
          }
        });
      }
    } catch (e) {
      console.error('HTTP fetch failed:', e);
    }
  }, [httpEndpoint, onEvent]);

  useEffect(() => {
    connect();
    
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, [connect]);

  const clearEvents = useCallback(() => {
    setState((s) => ({ ...s, pendingEvents: [] }));
    eventIdSet.current.clear();
  }, []);

  const sendEvent = useCallback(async (event: Partial<ChatEvent>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(event));
    } else {
      await fetch(httpEndpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(event),
      });
    }
  }, [httpEndpoint]);

  return {
    ...state,
    clearEvents,
    sendEvent,
    fetchEvents,
  };
};

function isChatEvent(data: unknown): data is ChatEvent {
  if (typeof data !== 'object' || data === null) return false;
  const obj = data as Record<string, unknown>;
  return (
    typeof obj.event_id === 'string' &&
    typeof obj.type === 'string' &&
    typeof obj.timestamp === 'string'
  );
}

export default useEventBus;
