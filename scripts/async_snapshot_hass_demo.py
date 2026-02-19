#!/usr/bin/env python3

import json
import os
import time


def main() -> int:
    from denis_unified_v1.async_min.tasks import dispatch_snapshot_hass

    run_id = f"demo_{int(time.time())}"
    out = dispatch_snapshot_hass(run_id=run_id)
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

