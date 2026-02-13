from __future__ import annotations

try:
    # legacy existente en tu repo
    from featureflags import loadfeatureflags as load_feature_flags  # type: ignore
except Exception:
    # fallback mínimo
    import json, os
    from typing import Any, Dict, Optional

    class FeatureFlags(dict):
        def enabled(self, name: str, default: bool = False) -> bool:
            v = self.get(name, default)
            if isinstance(v, bool): return v
            if isinstance(v, (int, float)): return bool(v)
            if isinstance(v, str): return v.strip().lower() in ("1","true","yes","y","on","enabled")
            return bool(v)

        def as_dict(self) -> dict:
            return dict(self)

    def load_feature_flags(
        env_key: str = "DENIS_FEATURE_FLAGS",
        prefix: str = "DENIS_FF_",
        defaults: Optional[Dict[str, Any]] = None,
    ) -> FeatureFlags:
        flags: Dict[str, Any] = dict(defaults or {})
        raw = os.getenv(env_key, "").strip()
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    flags.update(parsed)
            except Exception:
                pass
        for k, v in os.environ.items():
            if k.startswith(prefix):
                name = k[len(prefix):].lower()
                if name:
                    flags[name] = v
        return FeatureFlags(flags)
