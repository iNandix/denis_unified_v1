"""Sprint Orchestrator CLI."""

import argparse
import sys
from pathlib import Path

from .work_compiler import compile_work_from_artifacts


def main():
    parser = argparse.ArgumentParser(description="Sprint Orchestrator CLI")
    parser.add_argument(
        "--compile-work",
        action="store_true",
        help="Compile work plan from artifacts"
    )
    parser.add_argument(
        "--artifacts-root",
        type=Path,
        default=Path("artifacts"),
        help="Root directory for artifacts"
    )
    parser.add_argument(
        "--out-json",
        type=Path,
        default=Path("artifacts/orchestration/work_plan.json"),
        help="Output JSON file for work plan"
    )

    args = parser.parse_args()

    if args.compile_work:
        try:
            from .work_compiler import compile_work_from_artifacts, ArtifactNormalizer, RemediationRegistry
            # Debug
            normalizer = ArtifactNormalizer()
            registry = RemediationRegistry(args.artifacts_root.parent)
            print(f"Discovered smokes: {list(registry.smokes.keys())}")
            print(f"Known remediations: {list(registry.known_remediations.keys())}")
            
            # Scan artifacts
            artifacts_dir = args.artifacts_root
            signals = []
            if artifacts_dir.exists():
                for artifact_file in artifacts_dir.glob("*.json"):
                    sigs = normalizer.normalize_artifact(artifact_file)
                    signals.extend(sigs)
                    if sigs:
                        print(f"Signals from {artifact_file}: {[s['signal_id'] for s in sigs]}")
            
            print(f"Total signals: {len(signals)}")
            
            plan = compile_work_from_artifacts(args.artifacts_root, args.out_json)
            print(f"Work plan compiled: {len(plan['items'])} items, {len(plan['rejected_signals'])} rejected")
            print(f"Output: {args.out_json}")
            return 0
        except Exception as e:
            print(f"Error compiling work: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            return 1
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
