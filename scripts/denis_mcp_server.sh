#!/bin/bash
# Denis MCP Server launcher
# Sets up the environment correctly before launching the Python script

export PYTHONPATH="/media/jotah/SSD_denis/denis_unified_v1:$PYTHONPATH"
exec /media/jotah/SSD_denis/.venv_oceanai/bin/python3 "$@"
