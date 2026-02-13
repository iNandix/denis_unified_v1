#!/usr/bin/env python3
"""IDE Graph Client for Neo4j integration."""

import os
from pathlib import Path
from neo4j import GraphDatabase


class IdeGraphClient:
    def __init__(self, uri: str, user: str, password: str, db: str):
        self.driver = GraphDatabase.driver(uri, auth=(user, password), database=db)

    def close(self):
        self.driver.close()

    def upsert_service(self, name: str, url: str, status: str = 'unknown'):
        with self.driver.session() as session:
            session.run(
                "MERGE (s:Service {name: $name}) SET s.url = $url, s.status = $status",
                name=name, url=url, status=status
            )

    def record_health(self, name: str, ok: bool, latency_ms: float, ts: str):
        with self.driver.session() as session:
            session.run(
                "MERGE (s:Service {name: $name}) "
                "MERGE (h:HealthCheck {ts: $ts}) "
                "SET h.ok = $ok, h.latency_ms = $latency_ms "
                "MERGE (s)-[:HEALTHCHECKED_BY]->(h)",
                name=name, ok=ok, latency_ms=latency_ms, ts=ts
            )

    def record_smoke(self, phase: str, ok: bool, duration_ms: float, artifact_path: str, ts: str):
        with self.driver.session() as session:
            session.run(
                "MERGE (p:Phase {name: $phase}) "
                "MERGE (r:SmokeRun {ts: $ts}) "
                "SET r.ok = $ok, r.duration_ms = $duration_ms, r.artifact_path = $artifact_path "
                "MERGE (p)-[:VERIFIED_BY]->(r)",
                phase=phase, ok=ok, duration_ms=duration_ms, artifact_path=artifact_path, ts=ts
            )

    def scan_workspace(self):
        repo_path = Path(__file__).resolve().parents[3]  # Assuming tools/ide_graph/ide_graph_client.py
        workspace_id = repo_path.name
        tech_stack = ['python']  # Basic
        if (repo_path / 'requirements.txt').exists():
            with open(repo_path / 'requirements.txt') as f:
                if 'neo4j' in f.read():
                    tech_stack.append('neo4j')

        files = []
        for root, dirs, filenames in os.walk(repo_path):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['__pycache__', '.git', 'artifacts']]
            for filename in filenames:
                if filename.endswith('.py'):
                    file_path = Path(root) / filename
                    rel_path = file_path.relative_to(repo_path)
                    with open(file_path) as f:
                        loc = sum(1 for _ in f)
                    complexity = 1  # Simple
                    files.append((str(rel_path), 'py', loc, complexity))

        repo_size = len(files)

        with self.driver.session() as session:
            session.run(
                "MERGE (w:Workspace {id: $id}) SET w.path = $path, w.tech_stack = $tech_stack, w.repo_size = $repo_size",
                id=workspace_id, path=str(repo_path), tech_stack=tech_stack, repo_size=repo_size
            )

            for file_path, type_, loc, complexity in files:
                session.run(
                    "MERGE (f:File {path: $path}) SET f.type = $type, f.loc = $loc, f.complexity = $complexity, f.hotness_score = 0 "
                    "MERGE (w:Workspace {id: $wid}) MERGE (w)-[:HAS_FILE]->(f)",
                    path=file_path, type=type_, loc=loc, complexity=complexity, wid=workspace_id
                )

            # Basic components
            components = [
                ('api', 'service'),
                ('sprint_orchestrator', 'orchestrator'),
                ('inference', 'engine'),
                ('cortex', 'worker'),
                ('memory', 'store'),
                ('contracts', 'rules'),
                ('gates', 'security'),
            ]
            for name, kind in components:
                session.run(
                    "MERGE (c:Component {name: $name}) SET c.kind = $kind "
                    "MERGE (w:Workspace {id: $wid}) MERGE (w)-[:HAS_COMPONENT]->(c)",
                    name=name, kind=kind, wid=workspace_id
                )

            # Phases
            phases = ['phase1', 'phase2', 'phase3', 'phase4', 'phase5', 'phase6', 'phase7', 'phase8', 'phase9', 'phase10', 'phase11']
            for phase in phases:
                session.run(
                    "MERGE (p:Phase {name: $name}) SET p.status = 'unknown' "
                    "MERGE (w:Workspace {id: $wid}) MERGE (w)-[:HAS_PHASE]->(p)",
                    name=phase, wid=workspace_id
                )

            # Services
            services = [
                ('unified', 'http://127.0.0.1:8085', 'http'),
                ('legacy', 'http://127.0.0.1:8084', 'http'),
            ]
            for name, url, type_ in services:
                session.run(
                    "MERGE (s:Service {name: $name}) SET s.url = $url, s.type = $type, s.status = 'unknown' "
                    "MERGE (w:Workspace {id: $wid}) MERGE (w)-[:HAS_SERVICE]->(s)",
                    name=name, url=url, type=type_, wid=workspace_id
                )

    def record_test_result(self, test_name: str, test_type: str, ok: bool, duration_ms: float, artifact_path: str, ts: str):
        with self.driver.session() as session:
            session.run(
                "MERGE (t:Test {name: $test_name}) SET t.type = $test_type, t.last_result = $ok, t.last_run_ts = $ts, t.artifact_path = $artifact_path",
                test_name=test_name, test_type=test_type, ok=ok, ts=ts, artifact_path=artifact_path
            )
            # Link to phase if applicable
            if 'phase' in test_name:
                phase = test_name.split('_')[0]
                session.run(
                    "MERGE (p:Phase {name: $phase}) MERGE (t:Test {name: $test_name}) MERGE (p)-[:VERIFIED_BY]->(t)",
                    phase=phase, test_name=test_name
                )

    def record_proposal(self, id: str, title: str, status: str, targets: list, external_urls: list, ts: str):
        with self.driver.session() as session:
            session.run(
                "MERGE (pr:Proposal {id: $id}) SET pr.title = $title, pr.status = $status, pr.created_ts = $ts",
                id=id, title=title, status=status, ts=ts
            )
            for target in targets:
                session.run(
                    "MERGE (c:Component {name: $target}) MERGE (pr:Proposal {id: $id}) MERGE (pr)-[:TARGETS]->(c)",
                    target=target, id=id
                )
            for url in external_urls:
                session.run(
                    "MERGE (e:ExternalResource {name: $name, url: $url}) MERGE (pr:Proposal {id: $id}) MERGE (pr)-[:REFERS_TO]->(e)",
                    name=url.split('/')[-1], url=url, id=id
                )

    def record_agent_run(self, trace_id, goal_text, profile, started_ts, finished_ts=None, ok=None):
        with self.driver.session() as session:
            session.run(
                "MERGE (r:AgentRun {trace_id: $trace_id}) SET r.goal_text = $goal_text, r.profile = $profile, r.started_ts = $started_ts, r.finished_ts = $finished_ts, r.ok = $ok",
                trace_id=trace_id, goal_text=goal_text, profile=profile, started_ts=started_ts, finished_ts=finished_ts, ok=ok
            )

    def record_agent_task(self, trace_id, task_id, role, summary, status):
        with self.driver.session() as session:
            session.run(
                "MERGE (r:AgentRun {trace_id: $trace_id}) MERGE (t:AgentTask {task_id: $task_id}) SET t.role = $role, t.summary = $summary, t.status = $status MERGE (r)-[:HAS_TASK]->(t)",
                trace_id=trace_id, task_id=task_id, role=role, summary=summary, status=status
            )

    def record_agent_result(self, trace_id, task_id, ok, files_touched, artifacts, external_refs):
        with self.driver.session() as session:
            session.run(
                "MERGE (t:AgentTask {task_id: $task_id}) MERGE (res:AgentResult {task_id: $task_id}) SET res.ok = $ok, res.files_touched = $files_touched, res.artifacts = $artifacts, res.external_refs = $external_refs MERGE (t)-[:PRODUCED]->(res)",
                task_id=task_id, ok=ok, files_touched=files_touched, artifacts=artifacts, external_refs=external_refs
            )
            # Link to Workspace
            session.run(
                "MERGE (w:Workspace {id: 'denis_unified_v1'}) MERGE (r:AgentRun {trace_id: $trace_id}) MERGE (w)-[:RAN]->(r)",
                trace_id=trace_id
            )


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--scan-workspace', action='store_true')
    args = parser.parse_args()
    if args.scan_workspace:
        client = IdeGraphClient(
            os.getenv('IDE_GRAPH_URI', 'bolt://127.0.0.1:7689'),
            os.getenv('IDE_GRAPH_USER', 'neo4j'),
            os.getenv('IDE_GRAPH_PASSWORD', 'denis-ide-graph'),
            os.getenv('IDE_GRAPH_DB', 'neo4j')
        )
        client.scan_workspace()
        client.close()
