import json
import os
import time
from pathlib import Path
from typing import Dict, List, Any

class VersionControl:
    def __init__(self, store_dir: str = "artifacts/evolution_store"):
        self.store_dir = Path(store_dir)
        self.store_dir.mkdir(parents=True, exist_ok=True)

    def snapshot(self, label: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            timestamp = int(time.time())
            filename = f"{label}_{timestamp}.json"
            filepath = self.store_dir / filename
            
            data = {
                "label": label,
                "timestamp": timestamp,
                "payload": payload
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            return {
                "id": f"{label}_{timestamp}",
                "path": str(filepath),
                "ok": True
            }
        except Exception as e:
            return {
                "id": None,
                "path": None,
                "ok": False,
                "error": str(e)
            }

    def list_snapshots(self) -> List[str]:
        try:
            return [f.stem for f in self.store_dir.glob("*.json")]
        except Exception:
            return []

    def load(self, snapshot_id: str) -> Dict[str, Any]:
        try:
            filepath = self.store_dir / f"{snapshot_id}.json"
            if not filepath.exists():
                return {"error": "snapshot not found"}
            
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            return data
        except Exception as e:
            return {"error": str(e)}
