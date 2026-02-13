#!/usr/bin/env python3
"""CLI para Git-Graph Comparator.

Uso:
    python3 git_graph_check.py /path/to/project
    python3 git_graph_check.py /path/to/project --sync
    python3 git_graph_check.py /path/to/project --evolution EntityName
"""

import sys
import argparse
import json
from pathlib import Path

# Añadir sprint_orchestrator al path
sys.path.insert(0, str(Path(__file__).parent))

from git_graph_comparator import GitGraphComparator, compare_project_with_graph


def main():
    parser = argparse.ArgumentParser(
        description="Compara estado de Git contra el grafo Neo4j"
    )
    parser.add_argument("project", help="Ruta al proyecto")
    parser.add_argument(
        "--neo4j-uri",
        default="bolt://localhost:7687",
        help="URI de Neo4j (default: bolt://localhost:7687)",
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Sincronizar Git al grafo después de comparar",
    )
    parser.add_argument(
        "--evolution",
        metavar="ENTITY",
        help="Analizar evolución de una entidad específica",
    )
    parser.add_argument("--json", action="store_true", help="Output en formato JSON")
    parser.add_argument(
        "--commands", action="store_true", help="Mostrar comandos de sincronización"
    )

    args = parser.parse_args()

    project_path = Path(args.project).resolve()
    if not project_path.exists():
        print(f"❌ Error: Proyecto no encontrado: {project_path}")
        sys.exit(1)

    print(f"🔍 Analizando proyecto: {project_path}")
    print("=" * 70)

    comparator = GitGraphComparator(neo4j_uri=args.neo4j_uri)

    try:
        # Comparación principal
        result = comparator.compare_project(project_path)

        if args.json:
            print(json.dumps(result.to_dict(), indent=2))
            return

        # Mostrar resultados
        print(f"\n📊 Resumen:")
        print(f"  Archivos en Git: {result.total_files_in_git}")
        print(f"  Entidades en grafo: {result.total_entities_in_graph}")
        print(f"  Gaps detectados: {len(result.gaps)}")

        if result.summary:
            print(f"\n  Por tipo:")
            for key, val in result.summary.items():
                if val > 0 and not key.endswith("_severity"):
                    print(f"    - {key}: {val}")

            print(f"\n  Por severidad:")
            for sev in ["critical", "high", "medium", "low"]:
                count = result.summary.get(f"{sev}_severity", 0)
                if count > 0:
                    emoji = (
                        "🔴" if sev == "critical" else "🟠" if sev == "high" else "🟡"
                    )
                    print(f"    {emoji} {sev}: {count}")

        # Mostrar gaps
        if result.gaps:
            print(f"\n⚠️  Gaps encontrados (mostrando primeros 10):")
            for i, gap in enumerate(result.gaps[:10], 1):
                emoji = (
                    "🔴"
                    if gap.severity == "critical"
                    else "🟠"
                    if gap.severity == "high"
                    else "🟡"
                )
                print(f"\n  {i}. {emoji} [{gap.gap_type}] {gap.name}")
                print(f"      Tipo: {gap.entity_type} | File: {gap.file_path}")
                print(f"      Sugerencia: {gap.suggestion}")

            if len(result.gaps) > 10:
                print(f"\n  ... y {len(result.gaps) - 10} más")
        else:
            print("\n✅ No se encontraron gaps. ¡Git y grafo están sincronizados!")

        # Comandos de sincronización
        if args.commands and result.gaps:
            print(f"\n📝 Comandos recomendados:")
            commands = comparator.generate_sync_commands(result)
            for cmd in commands:
                print(f"  {cmd}")

        # Sincronizar Git al grafo
        if args.sync:
            print(f"\n🔄 Sincronizando Git al grafo...")
            stats = comparator.sync_git_to_graph(project_path)
            print(f"  Commits creados: {stats['commits_created']}")
            print(f"  Branches creados: {stats['branches_created']}")
            print(f"  Archivos vinculados: {stats['files_linked']}")
            print(f"  Relaciones creadas: {stats['relations_created']}")

        # Análisis de evolución
        if args.evolution:
            print(f"\n📈 Analizando evolución de: {args.evolution}")
            evolution = comparator.analyze_code_evolution(project_path, args.evolution)
            if "error" in evolution:
                print(f"  Error: {evolution['error']}")
            else:
                print(f"  Total commits: {evolution['total_commits']}")
                print(f"  Autores: {', '.join(evolution['authors'])}")
                print(f"  Último cambio: {evolution['latest_change']}")
                if evolution["frequently_changed_with"]:
                    print(f"  Cambiado frecuentemente con:")
                    for co in evolution["frequently_changed_with"][:5]:
                        print(f"    - {co['co_entity']}: {co['frequency']} veces")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
    finally:
        comparator.close()


if __name__ == "__main__":
    main()
