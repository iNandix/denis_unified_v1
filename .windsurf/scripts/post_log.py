#!/usr/bin/env python3
"""Post-cascade response logging."""

import os
from datetime import datetime

def main():
    response = os.getenv('WINDSURF_RESPONSE', '')
    log_file = '.windsurf/logs/cascade_responses.log'

    with open(log_file, 'a') as f:
        timestamp = datetime.now().isoformat()
        f.write(f"[{timestamp}] {response}\n")

if __name__ == "__main__":
    main()
