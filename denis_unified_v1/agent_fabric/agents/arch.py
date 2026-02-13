class ArchAgent:
    def __init__(self, provider):
        self.provider = provider

    def execute(self, goal):
        return {
            'summary': f'Architected for {goal}',
            'actions': [{'command': 'echo "design decisions"'}],
            'files_touched': [],
            'commands': [],
            'verify_targets': [],
            'risks': [],
            'external_refs': []
        }
