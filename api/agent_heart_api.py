from typing import Any, Dict

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from denis_agent_heart import get_denis_agent_heart

try:
    from metacognitive.hooks import heart_hook  # type: ignore
except Exception:
    def heart_hook(task: dict, result: dict) -> None:
        return


router = APIRouter()

@router.get("/agent/heart/status")
def heart_status() -> JSONResponse:
    try:
        heart = get_denis_agent_heart()
        status = heart.get_status() if hasattr(heart, "get_status") else {"status": "unknown"}
        return JSONResponse({"ok": True, "status": status})
    except Exception as e:
        return JSONResponse({"ok": True, "status": {"degraded": True, "error": str(e)}})

@router.post("/agent/heart/run")
async def heart_run(task: Dict[str, Any]) -> JSONResponse:
    # Fail-open: siempre devuelve JSON serializable.
    try:
        heart = get_denis_agent_heart()
        if hasattr(heart, "run_async"):
            result = await heart.run_async(task)
        else:
            result = heart.run(task)  # type: ignore
        try:
            heart_hook(task, result)
        except Exception:
            pass
        return JSONResponse({"ok": True, "result": result})
    except Exception as e:
        degraded = {"success": False, "error": str(e), "degraded": True, "task_echo": task}
        try:
            heart_hook(task, degraded)
        except Exception:
            pass
        return JSONResponse({"ok": True, "result": degraded})
