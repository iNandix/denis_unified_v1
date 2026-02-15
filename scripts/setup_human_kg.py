#!/usr/bin/env python3
"""
Setup Human Knowledge Graph schema in Neo4j.
Creates nodes, constraints, indices for user, group, person, pet, episode, claim, artifact.
"""

import os
from neo4j import GraphDatabase
from datetime import datetime

# Reuse Neo4j driver setup from existing code
NEO4J_URI = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

def create_schema():
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    with driver.session() as session:
        # Constraints (unique)
        constraints = [
            "CREATE CONSTRAINT user_id_unique IF NOT EXISTS FOR (u:User) REQUIRE u.user_id IS UNIQUE",
            "CREATE CONSTRAINT group_id_unique IF NOT EXISTS FOR (g:Group) REQUIRE g.group_id IS UNIQUE",
            "CREATE CONSTRAINT person_id_unique IF NOT EXISTS FOR (p:Person) REQUIRE p.person_id IS UNIQUE",
            "CREATE CONSTRAINT episode_id_unique IF NOT EXISTS FOR (e:Episode) REQUIRE e.episode_id IS UNIQUE",
            "CREATE CONSTRAINT claim_id_unique IF NOT EXISTS FOR (c:Claim) REQUIRE c.claim_id IS UNIQUE",
            "CREATE CONSTRAINT pet_id_unique IF NOT EXISTS FOR (pet:Pet) REQUIRE pet.pet_id IS UNIQUE",
            "CREATE CONSTRAINT artifact_id_unique IF NOT EXISTS FOR (a:Artifact) REQUIRE a.artifact_id IS UNIQUE"
        ]

        for constraint in constraints:
            session.run(constraint)
            print(f"Created constraint: {constraint}")

        # Indices (fulltext for search)
        indices = [
            "CREATE FULLTEXT INDEX person_search IF NOT EXISTS FOR (p:Person) ON EACH [p.name, p.aliases]",
            "CREATE FULLTEXT INDEX episode_search IF NOT EXISTS FOR (e:Episode) ON EACH [e.title, e.summary]",
            "CREATE FULLTEXT INDEX claim_search IF NOT EXISTS FOR (c:Claim) ON EACH [c.text]"
        ]

        for index in indices:
            session.run(index)
            print(f"Created index: {index}")

        print("Human Knowledge Graph schema setup complete.")

if __name__ == "__main__":
    create_schema()
