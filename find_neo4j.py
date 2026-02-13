import sys
sys.path.insert(0, '/media/jotah/SSD_denis/home_jotah/denis_unified_v1')

from cortex.neo4j_config_resolver import ensure_neo4j_env_auto
import json

result = ensure_neo4j_env_auto()
print(json.dumps(result, indent=2))
