"""Control Plane — Standalone bricks."""

from control_plane.ai_consult import AIConsult, ConsultResult
from control_plane.approval_popup import (
    ApprovalPopup,
    load_cp_from_file,
    show_cp_approval,
)
from control_plane.cp_generator import CPGenerator
from control_plane.cp_queue import CPQueue, get_cp_queue
from control_plane.models import ContextPack
from control_plane.repo_context import RepoContext

try:
    from control_plane.agent_result_writer import (
        clear_agent_result,
        read_agent_result,
        write_agent_result,
    )
except ImportError:
    pass

__all__ = [
    "ContextPack",
    "RepoContext",
    "CPQueue",
    "get_cp_queue",
    "CPGenerator",
    "ApprovalPopup",
    "show_cp_approval",
    "load_cp_from_file",
    "AIConsult",
    "ConsultResult",
]
