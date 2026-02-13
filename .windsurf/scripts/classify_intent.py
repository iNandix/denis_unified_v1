#!/usr/bin/env python3
"""Classify user intent from prompt for auditing."""

import json
import sys
from datetime import datetime

def classify_prompt(prompt):
    tags = []
    lower_prompt = prompt.lower()
    if 'contracts' in lower_prompt or 'approval' in lower_prompt:
        tags.append('contracts')
    if 'code' in lower_prompt or 'script' in lower_prompt or 'python' in lower_prompt:
        tags.append('code')
    if 'docs' in lower_prompt or 'documentation' in lower_prompt:
        tags.append('docs')
    if 'graph' in lower_prompt or 'neo4j' in lower_prompt:
        tags.append('graph')
    if 'ops' in lower_prompt or 'run' in lower_prompt or 'command' in lower_prompt:
        tags.append('ops')
    return tags

def main():
    tool_info = json.load(sys.stdin)
    prompt = tool_info.get('prompt', '')

    tags = classify_prompt(prompt)

    entry = {
        "timestamp": datetime.now().isoformat(),
        "action": "user_prompt",
        "tags": tags,
        "prompt_summary": prompt[:100] + '...' if len(prompt) > 100 else prompt,
        "trajectory_id": tool_info.get('trajectory_id', ''),
        "execution_id": tool_info.get('execution_id', '')
    }

    with open('.windsurf/logs/intent.jsonl', 'a') as f:
        f.write(json.dumps(entry) + '\n')

if __name__ == "__main__":
    main()
