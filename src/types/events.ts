export interface Universe {
  id: string;
  name: string;
  score: number;
  breakdown: {
    safety: number;
    relevance: number;
    code: number;
    latency: number;
    cost: number;
  };
  warnings?: {
    type: 'error' | 'warning';
    message: string;
  }[];
  preview?: string;
}

export interface MultiverseEvent {
  event_id: string;
  type: 'multiverse.start' | 'multiverse.result' | 'multiverse.score' | 'multiverse.top2' | 'multiverse.pick';
  timestamp: string;
  data: {
    universes?: Universe[];
    top2?: Universe[];
    selected?: string;
    status?: 'running' | 'complete' | 'error';
    message?: string;
  };
}

export interface ChunkCandidate {
  id: string;
  source: string;
  relevance: number;
  preview: string;
}

export interface ChunksEvent {
  event_id: string;
  type: 'chunks.search.result' | 'chunks.apply';
  timestamp: string;
  data: {
    candidates?: ChunkCandidate[];
    selected?: string[];
    merge_plan_summary?: string;
    status?: 'searching' | 'found' | 'applied';
  };
}

export interface ScrapedPage {
  url: string;
  title?: string;
  content_preview?: string;
  extracted_at: string;
}

export interface ScrapingEvent {
  event_id: string;
  type: 'scraping.page' | 'scraping.done';
  timestamp: string;
  data: {
    pages?: ScrapedPage[];
    total_pages?: number;
    summary?: string;
    status?: 'scraping' | 'complete';
  };
}

export type ChatEvent = MultiverseEvent | ChunksEvent | ScrapingEvent;

export interface EventMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  events?: ChatEvent[];
}
