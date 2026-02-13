import json
import time
from pathlib import Path
from typing import Dict, List, Any

class EvolutionMemory:
    def __init__(self, log_file: str = "artifacts/evolution_store/decisions.jsonl"):
        self.log_file = Path(log_file)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def record_decision(self, decision: Dict[str, Any]) -> Dict[str, Any]:
        try:
            entry = {
                "timestamp": time.time(),
                "decision": decision
            }
            with open(self.log_file, 'a', encoding='utf-8') as f:
                json.dump(entry, f, ensure_ascii=False)
                f.write('\n')
            return {"recorded": True}
        except Exception as e:
            return {"recorded": False, "error": str(e)}

    def get_recent(self, n: int = 10) -> List[Dict[str, Any]]:
        try:
            if not self.log_file.exists():
                return []
            with open(self.log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            recent = []
            for line in reversed(lines[-n:]):
                try:
                    recent.append(json.loads(line.strip()))
                except:
                    pass
            return recent[::-1]  # reverse back to chronological
        except Exception:
            return []
