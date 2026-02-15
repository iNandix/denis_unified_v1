#!/usr/bin/env python3
"""Denis Sync Dashboard - Minimal GUI for repo sync management."""

import os
import subprocess
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import threading
import time

REPO_DIR = "/media/jotah/SSD_denis/home_jotah/denis_unified_v1"
PORT = 8899


def run_cmd(cmd, cwd=REPO_DIR):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=cwd)
    return result.stdout.strip(), result.returncode


def get_status():
    local, _ = run_cmd("git rev-parse HEAD")
    remote, _ = run_cmd("git rev-parse origin/main")
    branches, _ = run_cmd("git branch -r")

    synced = local == remote

    return {
        "synced": synced,
        "local": local[:8],
        "remote": remote[:8],
        "local_extra": not synced,
        "branches": [
            b.strip() for b in branches.split("\n") if b.strip() and "origin/" in b
        ],
    }


def get_pending():
    output, _ = run_cmd("git log origin/main..HEAD --oneline")
    ahead = len(output.split("\n")) if output else 0

    output, _ = run_cmd("git log HEAD..origin/main --oneline")
    behind = len(output.split("\n")) if output else 0

    return {"ahead": ahead, "behind": behind}


def sync():
    output, code = run_cmd("git fetch origin main")
    local, _ = run_cmd("git rev-parse HEAD")
    remote, _ = run_cmd("git rev-parse origin/main")

    if local != remote:
        output, code = run_cmd("git pull origin main")
        return {"status": "synced", "output": output[:500]}
    return {"status": "already_synced"}


def merge_branch(branch):
    output, code = run_cmd(f"git merge origin/{branch} --no-edit")
    return {"status": "merged" if code == 0 else "error", "output": output[:500]}


def push():
    output, code = run_cmd("git push origin main")
    return {"status": "pushed" if code == 0 else "error", "output": output[:500]}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(HTML.encode())
        elif self.path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(get_status()).encode())
        elif self.path == "/api/pending":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(get_pending()).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode()

        if self.path == "/api/sync":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(sync()).encode())
        elif self.path == "/api/push":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(push()).encode())
        elif self.path.startswith("/api/merge/"):
            branch = self.path.split("/")[-1]
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(merge_branch(branch)).encode())
        else:
            self.send_response(404)
            self.end_headers()


HTML = """<!DOCTYPE html>
<html>
<head>
    <title>Denis Sync Dashboard</title>
    <meta charset="utf-8">
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 800px; margin: 40px auto; padding: 20px; background: #1a1a2e; color: #eee; }
        h1 { color: #00d9ff; }
        .card { background: #16213e; border-radius: 12px; padding: 20px; margin: 20px 0; }
        .status { display: flex; justify-content: space-between; align-items: center; }
        .synced { color: #00ff88; }
        .not-synced { color: #ff6b6b; }
        button { background: #0f3460; color: #fff; border: none; padding: 12px 24px; border-radius: 8px; cursor: pointer; font-size: 16px; margin: 5px; }
        button:hover { background: #00d9ff; color: #000; }
        button.merge { background: #e94560; }
        button.merge:hover { background: #ff6b6b; }
        .branch { background: #0f3460; padding: 10px; margin: 5px 0; border-radius: 6px; }
        #log { background: #0a0a1a; padding: 15px; border-radius: 8px; font-family: monospace; font-size: 12px; max-height: 200px; overflow-y: auto; }
    </style>
</head>
<body>
    <h1>🧠 Denis Sync Dashboard</h1>
    
    <div class="card">
        <h2>📊 Estado</h2>
        <div class="status">
            <span id="status-text">Cargando...</span>
            <button onclick="sync()">🔄 Sync Now</button>
        </div>
        <p>Local: <code id="local"></code> | Remote: <code id="remote"></code></p>
    </div>
    
    <div class="card">
        <h2>🔀 Ramas Remotas</h2>
        <div id="branches"></div>
    </div>
    
    <div class="card">
        <h2>📝 Log</h2>
        <div id="log"></div>
    </div>
    
    <script>
        async function update() {
            const status = await fetch('/api/status').then(r => r.json());
            document.getElementById('status-text').innerHTML = status.synced ? 
                '<span class="synced">✅ Sincronizado</span>' : 
                '<span class="not-synced">⚠️ Cambios pendientes</span>';
            document.getElementById('local').textContent = status.local;
            document.getElementById('remote').textContent = status.remote;
            
            const branchesDiv = document.getElementById('branches');
            branchesDiv.innerHTML = status.branches.map(b => 
                '<div class="branch">' + b + ' <button class="merge" onclick="merge(\\''+b.replace('origin/','')+'\\')">Merge</button></div>'
            ).join('');
        }
        
        async function sync() {
            const log = document.getElementById('log');
            log.innerHTML = 'Sincronizando...\n' + log.innerHTML;
            const r = await fetch('/api/sync', {method: 'POST'}).then(r => r.json());
            log.innerHTML = new Date().toLocaleTimeString() + ' ' + r.status + '\\n' + log.innerHTML;
            update();
        }
        
        async function merge(branch) {
            const log = document.getElementById('log');
            log.innerHTML = 'Mergeando ' + branch + '...\n' + log.innerHTML;
            const r = await fetch('/api/merge/' + branch, {method: 'POST'}).then(r => r.json());
            log.innerHTML = new Date().toLocaleTimeString() + ' ' + r.status + '\\n' + log.innerHTML;
            update();
        }
        
        update();
        setInterval(update, 5000);
    </script>
</body>
</html>"""


def main():
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"🚀 Dashboard: http://localhost:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
