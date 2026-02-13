"""Control Plane Configuration - Read from environment."""

import os
from pathlib import Path
from typing import Optional


class ControlPlaneConfig:
    def __init__(self):
        self.github_token = os.getenv("GITHUB_TOKEN", "")
        self.github_repo = os.getenv("GITHUB_REPO", "denis_unified_v1")
        self.github_owner = os.getenv("GITHUB_OWNER", "jotah")
        self.mode = os.getenv("CONTROL_PLANE_MODE", "dev")
        self.require_boot_import = (
            os.getenv("CONTROL_PLANE_REQUIRE_BOOT_IMPORT", "true").lower() == "true"
        )
        self.require_status = (
            os.getenv("CONTROL_PLANE_REQUIRE_STATUS", "true").lower() == "true"
        )
        self.min_pass_ratio = float(os.getenv("CONTROL_PLANE_MIN_PASS_RATIO", "0.7"))
        self.base_dir = Path.cwd()

    @property
    def is_ci(self) -> bool:
        return self.mode == "ci"

    @property
    def is_strict(self) -> bool:
        return self.is_ci or os.getenv("CI", "").lower() == "true"

    def get_github_url(self) -> str:
        if self.github_token:
            return f"https://{self.github_token}@github.com/{self.github_owner}/{self.github_repo}"
        return f"https://github.com/{self.github_owner}/{self.github_repo}"

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "is_ci": self.is_ci,
            "is_strict": self.is_strict,
            "require_boot_import": self.require_boot_import,
            "require_status": self.require_status,
            "min_pass_ratio": self.min_pass_ratio,
            "github_repo": f"{self.github_owner}/{self.github_repo}",
        }


def get_control_plane_config() -> ControlPlaneConfig:
    return ControlPlaneConfig()
