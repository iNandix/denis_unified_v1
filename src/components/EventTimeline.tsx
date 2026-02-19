import React, { useEffect, useRef, useState, useCallback } from 'react';
import { ChatEvent, EventMessage } from '../types/events';
import { MultiverseCard } from './events/MultiverseCard';
import { ChunksCard } from './events/ChunksCard';
import { ScrapingCard } from './events/ScrapingCard';

interface EventTimelineProps {
  messages: EventMessage[];
  wsUrl?: string;
  onPickUniverse?: (universeId: string) => void;
  onApplyChunks?: (chunkIds: string[]) => void;
}

export const EventTimeline: React.FC<EventTimelineProps> = ({
  messages,
  wsUrl = 'ws://localhost:8084/ws',
  onPickUniverse,
  onApplyChunks,
}) => {
  const [wsConnected, setWsConnected] = useState(false);
  const [wsMode, setWsMode] = useState<'ws' | 'http'>('http');
  const [pendingEvents, setPendingEvents] = useState<ChatEvent[]>([]);
  const wsRef = useRef<WebSocket | null>(null);
  const eventIdSet = useRef<Set<string>>(new Set());

  const handleWsMessage = useCallback((event: MessageEvent) => {
    try {
      const data = JSON.parse(event.data);
      
      if (data.type === 'multiverse.start' || 
          data.type === 'multiverse.result' ||
          data.type === 'multiverse.score' ||
          data.type === 'multiverse.top2' ||
          data.type === 'multiverse.pick' ||
          data.type === 'chunks.search.result' ||
          data.type === 'chunks.apply' ||
          data.type === 'scraping.page' ||
          data.type === 'scraping.done') {
        
        const chatEvent = data as ChatEvent;
        
        if (!eventIdSet.current.has(chatEvent.event_id)) {
          eventIdSet.current.add(chatEvent.event_id);
          setPendingEvents((prev) => [...prev, chatEvent]);
        }
      }
    } catch (e) {
      console.error('Error parsing WS message:', e);
    }
  }, []);

  const connectWs = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    try {
      const ws = new WebSocket(wsUrl);
      
      ws.onopen = () => {
        setWsConnected(true);
        setWsMode('ws');
      };
      
      ws.onmessage = handleWsMessage;
      
      ws.onclose = () => {
        setWsConnected(false);
        setWsMode('http');
      };
      
      ws.onerror = () => {
        setWsConnected(false);
        setWsMode('http');
      };
      
      wsRef.current = ws;
    } catch (e) {
      console.error('WS connection failed:', e);
      setWsMode('http');
    }
  }, [wsUrl, handleWsMessage]);

  useEffect(() => {
    connectWs();
    
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [connectWs]);

  const renderEvent = (event: ChatEvent) => {
    switch (event.type) {
      case 'multiverse.start':
      case 'multiverse.result':
      case 'multiverse.score':
      case 'multiverse.top2':
      case 'multiverse.pick':
        return (
          <MultiverseCard
            key={event.event_id}
            event={event}
            onPickUniverse={onPickUniverse}
          />
        );
      
      case 'chunks.search.result':
      case 'chunks.apply':
        return (
          <ChunksCard
            key={event.event_id}
            event={event}
            onApplyChunks={onApplyChunks}
          />
        );
      
      case 'scraping.page':
      case 'scraping.done':
        return (
          <ScrapingCard
            key={event.event_id}
            event={event}
          />
        );
      
      default:
        return null;
    }
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2 text-xs text-gray-500 px-4">
        <span className={`w-2 h-2 rounded-full ${wsConnected ? 'bg-green-500' : 'bg-gray-300'}`} />
        <span>{wsMode === 'ws' ? '🟢 WS' : '⚪ HTTP'}</span>
        {pendingEvents.length > 0 && (
          <span className="ml-2 text-blue-600">
            {pendingEvents.length} eventos pendientes
          </span>
        )}
      </div>

      {messages.map((msg) => (
        <div key={msg.id} className="px-4">
          {msg.content && (
            <div className="p-3 bg-gray-50 rounded-lg mb-2">
              <div className="text-sm text-gray-700">{msg.content}</div>
            </div>
          )}
          
          {msg.events?.map((event) => renderEvent(event))}
        </div>
      ))}

      {pendingEvents.map((event) => renderEvent(event))}
    </div>
  );
};

export default EventTimeline;
