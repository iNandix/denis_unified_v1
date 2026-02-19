import React, { useState } from 'react';
import { ScrapingEvent } from '../types/events';

interface ScrapingCardProps {
  event: ScrapingEvent;
}

export const ScrapingCard: React.FC<ScrapingCardProps> = ({ event }) => {
  const [expanded, setExpanded] = useState(false);
  const { data, type } = event;

  const renderContent = () => {
    switch (type) {
      case 'scraping.page':
        return (
          <div>
            {data.status === 'scraping' && (
              <div className="flex items-center gap-2 text-gray-600">
                <div className="animate-spin h-4 w-4 border-2 border-green-500 border-t-transparent rounded-full" />
                <span>Extrayendo páginas...</span>
              </div>
            )}

            {data.pages && data.pages.length > 0 && (
              <div>
                <div className="text-sm text-gray-600 mb-2">
                  {data.pages.length} páginas extraídas
                  {data.total_pages && data.total_pages > data.pages.length && (
                    <span className="text-gray-400">
                      {' '}(de {data.total_pages})
                    </span>
                  )}
                </div>

                <details>
                  <summary 
                    className="text-sm text-gray-500 cursor-pointer mb-2"
                    onClick={(e) => {
                      e.preventDefault();
                      setExpanded(!expanded);
                    }}
                  >
                    {expanded ? '▼' : '▶'} Ver páginas ({data.pages.length})
                  </summary>
                  
                  <div className="max-h-60 overflow-y-auto">
                    {data.pages.map((page, idx) => (
                      <div
                        key={idx}
                        className="p-2 border border-gray-200 rounded mb-1"
                      >
                        <div className="flex justify-between items-start">
                          <a
                            href={page.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-blue-600 text-sm hover:underline truncate"
                          >
                            {page.title || page.url}
                          </a>
                          <span className="text-xs text-gray-400 ml-2">
                            {new Date(page.extracted_at).toLocaleTimeString()}
                          </span>
                        </div>
                        {page.content_preview && (
                          <div className="text-xs text-gray-500 mt-1 truncate">
                            {page.content_preview}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </details>
              </div>
            )}

            {data.summary && (
              <div className="mt-3 p-2 bg-gray-50 rounded">
                <div className="text-sm font-medium text-gray-700 mb-1">
                  Resumen:
                </div>
                <div className="text-sm text-gray-600">{data.summary}</div>
              </div>
            )}
          </div>
        );

      case 'scraping.done':
        return (
          <div>
            <div className="text-green-600 font-medium mb-2">
              ✓ Extracción completada
            </div>

            {data.total_pages && (
              <div className="text-sm text-gray-600">
                Total: {data.total_pages} páginas
              </div>
            )}

            {data.summary && (
              <div className="mt-2 p-2 bg-gray-50 rounded">
                <div className="text-sm font-medium text-gray-700 mb-1">
                  Resumen:
                </div>
                <div className="text-sm text-gray-600">{data.summary}</div>
              </div>
            )}
          </div>
        );

      default:
        return <div className="text-gray-500">Evento desconocido</div>;
    }
  };

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4 max-w-xl">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-lg">🕸️</span>
        <span className="font-semibold">Scraping</span>
        <span className="text-xs text-gray-500 ml-auto">
          {new Date(event.timestamp).toLocaleTimeString()}
        </span>
      </div>

      {renderContent()}
    </div>
  );
};

export default ScrapingCard;
