#!/usr/bin/env python3
"""Context provider for IDE Graph."""

from .ide_graph_client import IdeGraphClient


class ContextProvider:
    def __init__(self, ide_graph_client: IdeGraphClient):
        self.client = ide_graph_client

    def get_relevant_context(self, query, file_path, profile):
        context = {
            'components': [],
            'tests': [],
            'proposals': [],
            'external_resources': []
        }
        with self.client.driver.session() as session:
            # Find components related to file_path
            result = session.run(
                "MATCH (f:File {path: $path})<-[:HAS_FILE]-(w)-[:HAS_COMPONENT]->(c) RETURN c.name",
                path=file_path
            )
            context['components'] = [r['c.name'] for r in result]

            # Find tests for related phases
            if 'phase' in file_path:
                phase = file_path.split('/')[0] if '/' in file_path else 'unknown'
                result = session.run(
                    "MATCH (p:Phase {name: $phase})-[:VERIFIED_BY]->(t:Test) RETURN t.name, t.last_result",
                    phase=phase
                )
                context['tests'] = [{'name': r['t.name'], 'result': r['t.last_result']} for r in result]

            # Find proposals targeting related components
            for comp in context['components']:
                result = session.run(
                    "MATCH (pr:Proposal)-[:TARGETS]->(c:Component {name: $comp}) RETURN pr.id, pr.title, pr.status",
                    comp=comp
                )
                context['proposals'].extend([{'id': r['pr.id'], 'title': r['pr.title'], 'status': r['pr.status']} for r in result])

            # Find external resources
            for comp in context['components']:
                result = session.run(
                    "MATCH (c:Component {name: $comp})-[:DEPENDS_ON]->(e:ExternalResource) RETURN e.url",
                    comp=comp
                )
                context['external_resources'].extend([r['e.url'] for r in result])

        return context

    def get_project_memory(self):
        memory = {
            'open_proposals': [],
            'hot_components': [],
            'failing_tests': [],
            'critical_services': []
        }
        with self.client.driver.session() as session:
            # Open proposals
            result = session.run(
                "MATCH (pr:Proposal {status: 'open'}) RETURN pr ORDER BY pr.created_ts DESC LIMIT 5"
            )
            memory['open_proposals'] = [dict(r['pr']) for r in result]

            # Failing tests
            result = session.run(
                "MATCH (t:Test) WHERE t.last_result = false RETURN t.name"
            )
            memory['failing_tests'] = [r['t.name'] for r in result]

            # Critical services (assuming status != 'ok')
            result = session.run(
                "MATCH (s:Service) WHERE s.status <> 'ok' RETURN s.name, s.status"
            )
            memory['critical_services'] = [{'name': r['s.name'], 'status': r['s.status']} for r in result]

            # Hot components (with most tests)
            result = session.run(
                "MATCH (c:Component)<-[:TARGETS]-(pr:Proposal) RETURN c.name, count(pr) as count ORDER BY count DESC LIMIT 5"
            )
            memory['hot_components'] = [r['c.name'] for r in result]

        return memory
