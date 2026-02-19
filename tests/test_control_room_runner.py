import json
from pathlib import Path


def test_control_room_runner_writes_report_artifact(tmp_path, monkeypatch):
    monkeypatch.setenv("DENIS_ARTIFACTS_DIR", str(tmp_path))
    monkeypatch.setenv("ASYNC_ENABLED", "0")  # force sync-safe execution

    from control_room.runner import ControlRoomRunner

    runner = ControlRoomRunner()
    report = runner.execute(run_id="run_cr_1")
    assert report["run_id"] == "run_cr_1"
    assert "steps" in report and isinstance(report["steps"], list)
    assert report.get("state") in {"SUCCESS", "FAILED"}

    # Find report artifact (idempotent suffix included)
    candidates = list((Path(tmp_path) / "control_room" / "run_cr_1").glob("control_room_run_report__*.json"))
    assert candidates
    data = json.loads(candidates[0].read_text(encoding="utf-8"))
    assert data["payload"]["run_id"] == "run_cr_1"


def test_control_room_runner_retry_does_not_duplicate_step_artifact(tmp_path, monkeypatch):
    monkeypatch.setenv("DENIS_ARTIFACTS_DIR", str(tmp_path))
    monkeypatch.setenv("ASYNC_ENABLED", "0")

    from control_room.runner import ControlRoomRunner

    runner = ControlRoomRunner()
    runner.execute(run_id="run_cr_2")
    runner.execute(run_id="run_cr_2")  # retry same run_id

    out_dir = Path(tmp_path) / "control_room" / "run_cr_2"
    step_artifacts = list(out_dir.glob("step_snapshot_hass__*.json"))
    assert len(step_artifacts) == 1
