import os
from neo4j import GraphDatabase

uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
user = os.getenv("NEO4J_USER", "neo4j")
password = os.getenv("NEO4J_PASSWORD") or os.getenv("NEO4J_PASS")

if not password:
    raise SystemExit(
        "Missing Neo4j password. Set NEO4J_PASSWORD (or NEO4J_PASS) in your environment."
    )

print(f"Testing Neo4j connection to {uri}...")

try:
    driver = GraphDatabase.driver(uri, auth=(user, password))
    with driver.session() as session:
        result = session.run("RETURN 1 as test")
        print("✅ Neo4j connection SUCCESS")
        
        # Count tools in graph
        tools_count = session.run("MATCH (t:Tool) RETURN count(t) as count").single()["count"]
        print(f"✅ Tools in graph: {tools_count}")
        
        # List all nodes
        nodes_result = session.run("MATCH (n) RETURN labels(n) as labels, count(*) as count ORDER BY count DESC LIMIT 10")
        nodes = [dict(record) for record in nodes_result]
        print(f"✅ Nodes in database: {nodes}")
    
    driver.close()
except Exception as e:
    print(f"❌ Neo4j connection FAILED: {e}")
