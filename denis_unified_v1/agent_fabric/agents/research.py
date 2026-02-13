class ResearchAgent:
    def __init__(self, provider):
        self.provider = provider

    def execute(self, goal):
        # Simulate research
        return {
            'summary': f'Researched {goal}',
            'actions': [],
            'files_touched': [],
            'commands': [],
            'verify_targets': [],
            'risks': [],
            'external_refs': ['https://github.com/example']
        }
