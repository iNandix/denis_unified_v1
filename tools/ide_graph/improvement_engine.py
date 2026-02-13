#!/usr/bin/env python3
"""Improvement engine for IDE Graph."""

from datetime import datetime
from .ide_graph_client import IdeGraphClient


class ImprovementEngine:
    def __init__(self, ide_graph_client: IdeGraphClient):
        self.client = ide_graph_client

    def analyze_and_propose(self):
        proposals = []
        with self.client.driver.session() as session:
            # Failing tests
            result = session.run("MATCH (t:Test) WHERE t.last_result = false RETURN t.name")
            failing_tests = [r['t.name'] for r in result]
            if failing_tests:
                proposals.append({
                    'id': 'fix_failing_tests',
                    'title': 'Fix failing tests',
                    'status': 'open',
                    'targets': [],
                    'external_urls': []
                })

            # Components without tests
            result = session.run("MATCH (c:Component) WHERE NOT EXISTS((c)<-[:VERIFIED_BY]-(:Test)) RETURN c.name")
            untested = [r['c.name'] for r in result]
            if untested:
                proposals.append({
                    'id': 'add_tests',
                    'title': 'Add tests for untested components',
                    'status': 'open',
                    'targets': untested,
                    'external_urls': []
                })

            # Services not ok
            result = session.run("MATCH (s:Service) WHERE s.status <> 'ok' RETURN s.name")
            failing_services = [r['s.name'] for r in result]
            if failing_services:
                proposals.append({
                    'id': 'fix_services',
                    'title': 'Fix failing services',
                    'status': 'open',
                    'targets': [],
                    'external_urls': []
                })

            # Proposals without implementation
            result = session.run("MATCH (pr:Proposal {status: 'open'}) WHERE NOT EXISTS((pr)-[:TARGETS]->(:Component)) RETURN pr.id")
            open_no_targets = [r['pr.id'] for r in result]
            if open_no_targets:
                proposals.append({
                    'id': 'implement_proposals',
                    'title': 'Implement open proposals',
                    'status': 'open',
                    'targets': [],
                    'external_urls': []
                })

        return proposals

    def generate_proposal(self, id, title, targets, external):
        ts = datetime.now().isoformat()
        self.client.record_proposal(id, title, 'open', targets, external, ts)
