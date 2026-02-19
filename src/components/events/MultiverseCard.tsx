import React from 'react';
import { MultiverseEvent, Universe } from '../types/events';

interface MultiverseCardProps {
  event: MultiverseEvent;
  onPickUniverse?: (universeId: string) => void;
}

export const MultiverseCard: React.FC<MultiverseCardProps> = ({ event, onPickUniverse }) => {
  const { data, type } = event;

  const renderBadge = (rank: number) => {
    const colors = {
      1: 'bg-yellow-500 text-black',
      2: 'bg-gray-400 text-black',
    };
    return (
      <span className={`px-2 py-0.5 text-xs font-bold rounded ${colors[rank as 1 | 2]}`}>
        TOP {rank}
      </span>
    );
  };

  const renderWarning = (warning: { type: string; message: string }, idx: number) => {
    const colors = {
      error: 'bg-red-100 border-red-500 text-red-700',
      warning: 'bg-orange-100 border-orange-500 text-orange-700',
    };
    return (
      <div key={idx} className={`p-2 text-sm border-l-4 ${colors[warning.type as 'error' | 'warning']}`}>
        {warning.message}
      </div>
    );
  };

  const renderScoreBreakdown = (breakdown: Universe['breakdown']) => {
    const metrics = [
      { key: 'safety', label: 'Seguridad', value: breakdown.safety },
      { key: 'relevance', label: 'Relevancia', value: breakdown.relevance },
      { key: 'code', label: 'Código', value: breakdown.code },
      { key: 'latency', label: 'Latencia', value: breakdown.latency },
      { key: 'cost', label: 'Costo', value: breakdown.cost },
    ];

    return (
      <div className="grid grid-cols-5 gap-2 mt-2">
        {metrics.map((m) => (
          <div key={m.key} className="text-center">
            <div className="text-xs text-gray-500">{m.label}</div>
            <div className="font-mono text-sm font-bold">{m.value.toFixed(1)}</div>
          </div>
        ))}
      </div>
    );
  };

  const renderUniverse = (universe: Universe, rank?: number) => {
    const isTop2 = rank !== undefined && rank <= 2;

    return (
      <div
        key={universe.id}
        className={`p-3 border rounded-lg mb-2 ${isTop2 ? 'border-yellow-400 bg-yellow-50' : 'border-gray-200'}`}
      >
        <div className="flex justify-between items-start mb-2">
          <div className="flex items-center gap-2">
            {rank && isTop2 && renderBadge(rank)}
            <span className="font-medium">{universe.name}</span>
          </div>
          <span className="font-mono font-bold text-lg">{universe.score.toFixed(2)}</span>
        </div>

        {universe.preview && (
          <div className="text600 mb-2-sm text-gray- truncate">{universe.preview}</div>
        )}

        {renderScoreBreakdown(universe.breakdown)}

        {universe.warnings && universe.warnings.length > 0 && (
          <div className="mt-2">
            {universe.warnings.map((w, i) => renderWarning(w, i))}
          </div>
        )}

        {onPickUniverse && isTop2 && (
          <button
            onClick={() => onPickUniverse(universe.id)}
            className="mt-2 px-3 py-1 text-sm bg-blue-600 text-white rounded hover:bg-blue-700"
          >
            Usar Universo #{rank}
          </button>
        )}
      </div>
    );
  };

  const renderContent = () => {
    switch (type) {
      case 'multiverse.start':
        return (
          <div className="flex items-center gap-2 text-gray-600">
            <div className="animate-spin h-4 w-4 border-2 border-blue-500 border-t-transparent rounded-full" />
            <span>Explorando multiverso...</span>
            {data.message && <span className="text-sm">{data.message}</span>}
          </div>
        );

      case 'multiverse.top2':
      case 'multiverse.result':
        const top2 = data.top2 || [];
        const others = (data.universities || []).filter(
          (u) => !top2.find((t) => t.id === u.id)
        );

        return (
          <div>
            <div className="text-sm font-medium text-gray-700 mb-2">
              Mejores universos:
            </div>
            {top2.map((u, idx) => renderUniverse(u, idx + 1))}

            {others.length > 0 && (
              <details className="mt-2">
                <summary className="text-sm text-gray-500 cursor-pointer">
                  Ver otros ({others.length})
                </summary>
                {others.map((u) => renderUniverse(u))}
              </details>
            )}
          </div>
        );

      case 'multiverse.pick':
        return (
          <div className="text-green-600 font-medium">
            ✓ Universo seleccionado: {data.selected}
          </div>
        );

      case 'multiverse.score':
        return (
          <div>
            {data.universities?.map((u) => renderUniverse(u))}
          </div>
        );

      default:
        return <div className="text-gray-500">Evento desconocido</div>;
    }
  };

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4 max-w-xl">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-lg">🌌</span>
        <span className="font-semibold">Multiverso</span>
        <span className="text-xs text-gray-500 ml-auto">
          {new Date(event.timestamp).toLocaleTimeString()}
        </span>
      </div>
      {renderContent()}
    </div>
  );
};

export default MultiverseCard;
