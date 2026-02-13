"""PostgreSQL integration for relational data and transactions."""

import asyncio
import json
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass
import os

try:
    import asyncpg
    import psycopg2
    from psycopg2.extras import RealDictCursor
    from psycopg2.pool import SimpleConnectionPool
except ImportError:
    asyncpg = None
    psycopg2 = None
    RealDictCursor = None
    SimpleConnectionPool = None


@dataclass
class PostgresConfig:
    """PostgreSQL connection configuration."""
    host: str = "localhost"
    port: int = 5432
    database: str = "denis_metacognitive"
    user: str = "denis"
    password: str = ""
    min_connections: int = 5
    max_connections: int = 20
    connection_timeout: int = 30
    command_timeout: int = 60


class PostgresManager:
    """PostgreSQL database manager with connection pooling."""

    def __init__(self, config: PostgresConfig):
        self.config = config
        self._sync_pool = None
        self._async_pool = None
        self._initialized = False

    async def initialize(self):
        """Initialize database connections and schema."""
        if not asyncpg or not psycopg2:
            print("PostgreSQL dependencies not available")
            return

        try:
            # Create async connection pool
            self._async_pool = await asyncpg.create_pool(
                host=self.config.host,
                port=self.config.port,
                database=self.config.database,
                user=self.config.user,
                password=self.config.password,
                min_size=self.config.min_connections,
                max_size=self.config.max_connections,
                command_timeout=self.config.command_timeout,
            )

            # Create sync connection pool
            dsn = f"host={self.config.host} port={self.config.port} dbname={self.config.database} user={self.config.user} password={self.config.password}"
            self._sync_pool = SimpleConnectionPool(
                minconn=self.config.min_connections,
                maxconn=self.config.max_connections,
                dsn=dsn
            )

            await self._create_schema()
            self._initialized = True
            print("PostgreSQL initialized successfully")

        except Exception as e:
            print(f"Failed to initialize PostgreSQL: {e}")
            self._async_pool = None
            self._sync_pool = None

    async def _create_schema(self):
        """Create necessary database schema."""
        if not self._async_pool:
            return

        async with self._async_pool.acquire() as conn:
            # Create tables for metacognitive data
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS metacognitive_sessions (
                    id SERIAL PRIMARY KEY,
                    session_id VARCHAR(255) UNIQUE NOT NULL,
                    prompt TEXT,
                    worker_count INTEGER DEFAULT 0,
                    project_count INTEGER DEFAULT 0,
                    status VARCHAR(50) DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS feedback_events (
                    id SERIAL PRIMARY KEY,
                    session_id VARCHAR(255),
                    type VARCHAR(100),
                    content TEXT,
                    metadata JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS performance_metrics (
                    id SERIAL PRIMARY KEY,
                    metric_name VARCHAR(255),
                    value FLOAT,
                    tags JSONB,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS capability_registry (
                    id SERIAL PRIMARY KEY,
                    capability_id VARCHAR(255) UNIQUE,
                    category VARCHAR(100),
                    status VARCHAR(50),
                    confidence FLOAT,
                    metadata JSONB,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create indexes for performance
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_session_id ON metacognitive_sessions(session_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_feedback_session ON feedback_events(session_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_metrics_name ON performance_metrics(metric_name)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_capabilities_category ON capability_registry(category)")

    async def store_session(self, session_data: Dict[str, Any]) -> bool:
        """Store session data in PostgreSQL."""
        if not self._async_pool:
            return False

        try:
            async with self._async_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO metacognitive_sessions
                    (session_id, prompt, worker_count, project_count, status)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (session_id) DO UPDATE SET
                        prompt = EXCLUDED.prompt,
                        worker_count = EXCLUDED.worker_count,
                        project_count = EXCLUDED.project_count,
                        status = EXCLUDED.status,
                        updated_at = CURRENT_TIMESTAMP
                """,
                session_data.get('session_id'),
                session_data.get('prompt'),
                session_data.get('worker_count', 0),
                session_data.get('project_count', 0),
                session_data.get('status', 'active')
                )
            return True
        except Exception as e:
            print(f"Error storing session: {e}")
            return False

    async def store_feedback(self, feedback_data: Dict[str, Any]) -> bool:
        """Store feedback event in PostgreSQL."""
        if not self._async_pool:
            return False

        try:
            async with self._async_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO feedback_events
                    (session_id, type, content, metadata)
                    VALUES ($1, $2, $3, $4)
                """,
                feedback_data.get('session_id'),
                feedback_data.get('type'),
                feedback_data.get('content'),
                json.dumps(feedback_data.get('metadata', {}))
                )
            return True
        except Exception as e:
            print(f"Error storing feedback: {e}")
            return False

    async def store_metric(self, metric_name: str, value: float, tags: Dict[str, Any] = None) -> bool:
        """Store performance metric in PostgreSQL."""
        if not self._async_pool:
            return False

        try:
            async with self._async_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO performance_metrics
                    (metric_name, value, tags)
                    VALUES ($1, $2, $3)
                """,
                metric_name,
                value,
                json.dumps(tags or {})
                )
            return True
        except Exception as e:
            print(f"Error storing metric: {e}")
            return False

    async def get_recent_sessions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent sessions from PostgreSQL."""
        if not self._async_pool:
            return []

        try:
            async with self._async_pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT * FROM metacognitive_sessions
                    ORDER BY created_at DESC
                    LIMIT $1
                """, limit)

                return [dict(row) for row in rows]
        except Exception as e:
            print(f"Error getting sessions: {e}")
            return []

    async def get_feedback_analysis(self, hours: int = 24) -> Dict[str, Any]:
        """Analyze feedback patterns from recent hours."""
        if not self._async_pool:
            return {}

        try:
            async with self._async_pool.acquire() as conn:
                # Get feedback counts by type
                type_counts = await conn.fetch("""
                    SELECT type, COUNT(*) as count
                    FROM feedback_events
                    WHERE created_at > CURRENT_TIMESTAMP - INTERVAL '%s hours'
                    GROUP BY type
                    ORDER BY count DESC
                """ % hours)

                # Get feedback timeline
                timeline = await conn.fetch("""
                    SELECT DATE_TRUNC('hour', created_at) as hour, COUNT(*) as count
                    FROM feedback_events
                    WHERE created_at > CURRENT_TIMESTAMP - INTERVAL '%s hours'
                    GROUP BY hour
                    ORDER BY hour
                """ % hours)

                return {
                    "feedback_types": {row['type']: row['count'] for row in type_counts},
                    "timeline": [{"hour": str(row['hour']), "count": row['count']} for row in timeline],
                    "analysis_period_hours": hours
                }
        except Exception as e:
            print(f"Error analyzing feedback: {e}")
            return {}

    async def health_check(self) -> Dict[str, Any]:
        """Perform PostgreSQL health check."""
        if not self._async_pool:
            return {"healthy": False, "reason": "not_initialized"}

        try:
            async with self._async_pool.acquire() as conn:
                result = await conn.fetchval("SELECT 1")
                if result == 1:
                    return {"healthy": True}
                else:
                    return {"healthy": False, "reason": "unexpected_result"}
        except Exception as e:
            return {"healthy": False, "reason": str(e)}

    def get_sync_connection(self):
        """Get synchronous connection from pool."""
        if self._sync_pool:
            return self._sync_pool.getconn()
        return None

    def release_sync_connection(self, conn):
        """Release synchronous connection back to pool."""
        if self._sync_pool and conn:
            self._sync_pool.putconn(conn)


# Global PostgreSQL instance
_postgres_instance = None

async def get_postgres_manager() -> PostgresManager:
    """Get global PostgreSQL manager instance."""
    global _postgres_instance
    if _postgres_instance is None:
        config = PostgresConfig(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            database=os.getenv("POSTGRES_DB", "denis_metacognitive"),
            user=os.getenv("POSTGRES_USER", "denis"),
            password=os.getenv("POSTGRES_PASSWORD", ""),
            min_connections=int(os.getenv("POSTGRES_MIN_CONN", "5")),
            max_connections=int(os.getenv("POSTGRES_MAX_CONN", "20")),
            connection_timeout=int(os.getenv("POSTGRES_CONN_TIMEOUT", "30")),
            command_timeout=int(os.getenv("POSTGRES_CMD_TIMEOUT", "60"))
        )

        _postgres_instance = PostgresManager(config)
        await _postgres_instance.initialize()

    return _postgres_instance
