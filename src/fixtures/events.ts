import { MultiverseEvent, ChunksEvent, ScrapingEvent, EventMessage } from '../types/events';

export const mockMultiverseResult: MultiverseEvent = {
  event_id: 'multiverse-001',
  type: 'multiverse.result',
  timestamp: new Date().toISOString(),
  data: {
    universes: [
      {
        id: 'universe-1',
        name: 'claude-sonnet',
        score: 0.92,
        breakdown: {
          safety: 0.95,
          relevance: 0.90,
          code: 0.93,
          latency: 0.88,
          cost: 0.85,
        },
        warnings: [],
        preview: 'Best for code generation with high safety...',
      },
      {
        id: 'universe-2',
        name: 'gpt-4',
        score: 0.88,
        breakdown: {
          safety: 0.85,
          relevance: 0.92,
          code: 0.90,
          latency: 0.82,
          cost: 0.78,
        },
        warnings: [
          {
            type: 'warning',
            message: 'Higher cost per token',
          },
        ],
        preview: 'Strong reasoning but higher latency...',
      },
      {
        id: 'universe-3',
        name: 'local-llama',
        score: 0.75,
        breakdown: {
          safety: 0.70,
          relevance: 0.78,
          code: 0.80,
          latency: 0.95,
          cost: 0.98,
        },
        warnings: [
          {
            type: 'error',
            message: 'Lower safety score - review required',
          },
        ],
        preview: 'Fast and cheap but needs review...',
      },
    ],
    top2: [
      {
        id: 'universe-1',
        name: 'claude-sonnet',
        score: 0.92,
        breakdown: {
          safety: 0.95,
          relevance: 0.90,
          code: 0.93,
          latency: 0.88,
          cost: 0.85,
        },
      },
      {
        id: 'universe-2',
        name: 'gpt-4',
        score: 0.88,
        breakdown: {
          safety: 0.85,
          relevance: 0.92,
          code: 0.90,
          latency: 0.82,
          cost: 0.78,
        },
      },
    ],
  },
};

export const mockChunksResult: ChunksEvent = {
  event_id: 'chunks-001',
  type: 'chunks.search.result',
  timestamp: new Date().toISOString(),
  data: {
    candidates: [
      {
        id: 'chunk-001',
        source: 'src/api/users.ts',
        relevance: 0.95,
        preview: 'export interface User { id: string; name: string; email: string; }',
      },
      {
        id: 'chunk-002',
        source: 'src/api/auth.ts',
        relevance: 0.88,
        preview: 'export const authenticate = async (token: string) => { ... }',
      },
      {
        id: 'chunk-003',
        source: 'src/types/index.ts',
        relevance: 0.75,
        preview: 'export type UserRole = "admin" | "user" | "guest";',
      },
    ],
    selected: ['chunk-001', 'chunk-002'],
    merge_plan_summary: 'Merge user authentication flow: combine User interface with authenticate function, ensuring proper type safety for token handling.',
  },
};

export const mockScrapingResult: ScrapingEvent = {
  event_id: 'scraping-001',
  type: 'scraping.page',
  timestamp: new Date().toISOString(),
  data: {
    pages: [
      {
        url: 'https://docs.example.com/api/auth',
        title: 'Authentication API',
        content_preview: 'The Authentication API provides methods for user login, logout, and token refresh...',
        extracted_at: new Date().toISOString(),
      },
      {
        url: 'https://docs.example.com/api/users',
        title: 'User Management',
        content_preview: 'User endpoints allow creating, reading, updating, and deleting user records...',
        extracted_at: new Date().toISOString(),
      },
      {
        url: 'https://docs.example.com/api/permissions',
        title: 'Permissions',
        content_preview: 'Fine-grained permission system for controlling access to resources...',
        extracted_at: new Date().toISOString(),
      },
    ],
    total_pages: 3,
    summary: 'Documentation for authentication, user management, and permissions APIs found.',
  },
};

export const mockMessages: EventMessage[] = [
  {
    id: 'msg-001',
    role: 'user',
    content: 'Crea un endpoint de autenticación',
    timestamp: new Date().toISOString(),
    events: [mockMultiverseResult],
  },
  {
    id: 'msg-002',
    role: 'assistant',
    content: 'Voy a buscar chunks relevantes del codebase...',
    timestamp: new Date().toISOString(),
    events: [mockChunksResult],
  },
  {
    id: 'msg-003',
    role: 'assistant',
    content: 'También puedo extraer documentación de参考...',
    timestamp: new Date().toISOString(),
    events: [mockScrapingResult],
  },
];
