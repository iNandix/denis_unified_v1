from typing import Dict, List

class ProviderRegistry:
    def __init__(self):
        self.providers: Dict[str, List[str]] = {
            'free_local': ['denis_agent', 'llama_node1', 'llama_node2'],
            'free_remote': ['openrouter_free'],
            'premium': ['vllm']
        }

    def get_provider(self, agent_type: str) -> str:
        if agent_type == 'manager':
            return 'denis_agent'  # small model
        elif agent_type == 'research':
            return 'openrouter_free'  # for external search
        elif agent_type == 'coding':
            return 'llama_node1'  # best local for coding
        elif agent_type == 'qa':
            return 'denis_agent'  # for testing
        elif agent_type == 'ops':
            return 'denis_agent'  # for ops
        elif agent_type == 'neo4j':
            return 'denis_agent'  # for graph
        else:
            return 'denis_agent'
