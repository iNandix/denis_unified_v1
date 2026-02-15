import json
import shutil
import subprocess
from pathlib import Path
import tempfile

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "ingest_identity_core.py"
SCHEMA = REPO_ROOT / "docs/identity/identity_schema.yaml"
REPORT = REPO_ROOT / "reports/persona_canonical_report.json"
INDEX = REPO_ROOT / "reports/persona_canonical.index.json"
INVENTORY = REPO_ROOT / "docs/identity/inventory/identity_inventory.machine.json"


def run_ingest(tmpdir: Path, inventory_path: Path, expect_ok: bool = True):
    out = tmpdir / "graph_seed.json"
    snapshot = tmpdir / "graph_seed.prev.json"
    drift = tmpdir / "drift_report.json"
    cmd = [
        "python3",
        str(SCRIPT),
        "--schema",
        str(tmpdir / SCHEMA.name),
        "--report",
        str(tmpdir / REPORT.name),
        "--index",
        str(tmpdir / INDEX.name),
        "--inventory",
        str(inventory_path),
        "--out",
        str(out),
        "--snapshot",
        str(snapshot),
        "--drift-report-out",
        str(drift),
        "--dry-run",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if expect_ok:
        assert proc.returncode == 0, proc.stderr or proc.stdout
        assert out.exists()
        assert snapshot.exists()
        return out, snapshot, drift, proc
    else:
        assert proc.returncode != 0
        assert "CONSTITUTIONAL_DRIFT_DETECTED" in (proc.stdout + proc.stderr)
        assert drift.exists()
        return out, snapshot, drift, proc


def test_drift_report_on_missing_mitigation():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        # copy artifacts into temp dir
        for src in (SCHEMA, REPORT, INDEX, INVENTORY):
            shutil.copy(src, tmp / src.name)
        inv_path = tmp / INVENTORY.name
        # first run: baseline snapshot
        run_ingest(tmp, inv_path, expect_ok=True)

        # mutate inventory: drop system:action_authorizer from first bypass mitigations
        data = json.loads(inv_path.read_text())
        for byp in data.get("bypass_surfaces", []):
            if byp.get("mitigations"):
                byp["mitigations"] = [m for m in byp["mitigations"] if m != "system:action_authorizer"]
                break
        inv_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

        # second run: expect drift detection
        out, snapshot, drift, proc = run_ingest(tmp, inv_path, expect_ok=False)
        report = json.loads(drift.read_text())
        assert report.get("doc_type") == "constitutional_drift_report"
        assert report.get("removed", {}).get("bypass_mitigations")
        missing_entries = report["removed"]["bypass_mitigations"][0]
        assert "system:action_authorizer" in missing_entries.get("missing", [])


if __name__ == "__main__":
    pytest.main([__file__])
