#!/usr/bin/env python3
"""Post-cascade response logging."""

import json
import sys
from datetime import datetime

def main():
    tool_info = json.load(sys.stdin)
    response = tool_info.get('response', '')
    files_touched = tool_info.get('files_touched', [])
    timestamp = datetime.now().isoformat()
    summary = response[:100] + '...' if len(response) > 100 else response
    files_str = ', '.join(files_touched) if files_touched else 'none'
    with open('.windsurf/logs/cascade_responses.log', 'a') as f:
        f.write(f"[{timestamp}] {summary} files: {files_str}\n")

if __name__ == "__main__":
    main()
