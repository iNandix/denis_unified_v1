import React, { useState } from 'react';
import { ChunksEvent } from '../types/events';

interface ChunksCardProps {
  event: ChunksEvent;
  onApplyChunks?: (chunkIds: string[]) => void;
}

export const ChunksCard: React.FC<ChunksCardProps> = ({ event, onApplyChunks }) => {
  const [expanded, setExpanded] = useState(true);
  const { data, type } = event;

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
  };

  const renderContent = () => {
    switch (type) {
      case 'chunks.search.result':
        return (
          <div>
            {data.status === 'searching' && (
              <div className="flex items-center gap-2 text-gray-600">
                <div className="animate-pulse">Buscando chunks...</div>
              </div>
            )}

            {data.candidates && data.candidates.length > 0 && (
              <div>
                <div className="text-sm text-gray-600 mb-2">
                  {data.candidates.length} candidatos encontrados
                </div>

                <details open={expanded}>
                  <summary 
                    className="text-sm text-gray-500 cursor-pointer mb-2"
                    onClick={(e) => {
                      e.preventDefault();
                      setExpanded(!expanded);
                    }}
                  >
                    {expanded ? '▼' : '▶'} Ver candidatos ({data.candidates.length})
                  </summary>
                  
                  <div className="max-h-60 overflow-y-auto">
                    {data.candidates.map((chunk) => (
                      <div
                        key={chunk.id}
                        className={`p-2 text-sm border rounded mb-1 ${
                          data.selected?.includes(chunk.id)
                            ? 'border-blue-500 bg-blue-50'
                            : 'border-gray-200'
                        }`}
                      >
                        <div className="flex justify-between items-start">
                          <span className="font-mono text-xs text-gray-500">{chunk.id}</span>
                          <span className="text-xs bg-gray-100 px-1 rounded">
                            {chunk.relevance.toFixed(2)}
                          </span>
                        </div>
                        <div className="text-gray-600 truncate mt-1">{chunk.preview}</div>
                      </div>
                    ))}
                  </div>
                </details>

                {data.selected && data.selected.length > 0 && (
                  <div className="mt-3 p-2 bg-blue-50 border border-blue-200 rounded">
                    <div className="text-sm font-medium text-blue-700">
                      Seleccionados: {data.selected.length} chunks
                    </div>
                  </div>
                )}
              </div>
            )}

            {data.merge_plan_summary && (
              <div className="mt-3">
                <div className="text-sm font-medium text-gray-700 mb-1">
                  Plan de merge:
                </div>
                <div className="p-2 bg-gray-50 rounded text-sm text-gray-600">
                  {data.merge_plan_summary}
                </div>
              </div>
            )}
          </div>
        );

      case 'chunks.apply':
        return (
          <div className="text-green-600 font-medium">
            ✓ Chunks aplicados
          </div>
        );

      default:
        return <div className="text-gray-500">Evento desconocido</div>;
    }
  };

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4 max-w-xl">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-lg">📦</span>
          <span className="font-semibold">Chunks</span>
          <span className="text-xs text-gray-500 ml-auto">
            {new Date(event.timestamp).toLocaleTimeString()}
          </span>
        </div>
      </div>

      {renderContent()}

      <div className="flex gap-2 mt-3 pt-3 border-t">
        {data.merge_plan_summary && (
          <button
            onClick={() => copyToClipboard(data.merge_plan_summary || '')}
            className="px-3 py-1 text-sm bg-gray-100 text-gray-700 rounded hover:bg-gray-200"
          >
            📋 Copiar plan
          </button>
        )}

        {data.selected && data.selected.length > 0 && (
          <button
            onClick={() => copyToClipboard(data.selected?.join(', ') || '')}
            className="px-3 py-1 text-sm bg-gray-100 text-gray-700 rounded hover:bg-gray-200"
          >
            📋 Copiar IDs
          </button>
        )}

        {onApplyChunks && data.selected && data.selected.length > 0 && (
          <button
            onClick={() => onApplyChunks(data.selected || [])}
            className="px-3 py-1 text-sm bg-blue-600 text-white rounded hover:bg-blue-700"
          >
            ✅ Aplicar
          </button>
        )}
      </div>
    </div>
  );
};

export default ChunksCard;
