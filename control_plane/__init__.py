"""Control Plane — Standalone bricks."""

from control_plane.ai_consult import AIConsult, ConsultResult
from control_plane.approval_popup import (
    show_post_brief_popup,
    show_phase_complete_popup,
    show_sprint_close_popup,
    show_upload_cp_popup,
    ControlPlaneAuthority,
    get_control_plane_authority,
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
    "show_post_brief_popup",
    "show_phase_complete_popup",
    "show_sprint_close_popup",
    "show_upload_cp_popup",
    "ControlPlaneAuthority",
    "get_control_plane_authority",
    "AIConsult",
    "ConsultResult",
]
