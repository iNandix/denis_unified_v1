class CodingAgent:
    def __init__(self, provider):
        self.provider = provider

    def execute(self, goal):
        return {
            'summary': f'Coded for {goal}',
            'actions': [{'command': 'echo "code implemented"'}],
            'files_touched': ['new_code.py'],
            'commands': ['ruff new_code.py'],
            'verify_targets': ['pytest test_new.py'],
            'risks': ['needs testing'],
            'external_refs': []
        }
