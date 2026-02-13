"""ClickHouse integration for analytics and time-series data."""

import asyncio
import json
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
import os

try:
    import aiochclient
    import clickhouse_driver
except ImportError:
    aiochclient = None
    clickhouse_driver = None


@dataclass
class ClickHouseConfig:
    """ClickHouse connection configuration."""
    host: str = "localhost"
    port: int = 9000
    http_port: int = 8123
    database: str = "denis_analytics"
    user: str = "default"
    password: str = ""
    connection_timeout: int = 30
    read_timeout: int = 300


class ClickHouseManager:
    """ClickHouse database manager for analytics."""

    def __init__(self, config: ClickHouseConfig):
        self.config = config
        self._async_client = None
        self._sync_client = None
        self._initialized = False

    async def initialize(self):
        """Initialize ClickHouse connections and schema."""
        if not aiochclient or not clickhouse_driver:
            print("ClickHouse dependencies not available")
            return

        try:
            # Create async HTTP client for queries
            self._async_client = aiochclient.ChClient(
                url=f"http://{self.config.host}:{self.config.http_port}",
                database=self.config.database,
                user=self.config.user,
                password=self.config.password,
            )

            # Create sync client for schema operations
            self._sync_client = clickhouse_driver.Client(
                host=self.config.host,
                port=self.config.port,
                database=self.config.database,
                user=self.config.user,
                password=self.config.password,
            )

            await self._create_schema()
            self._initialized = True
            print("ClickHouse initialized successfully")

        except Exception as e:
            print(f"Failed to initialize ClickHouse: {e}")
            self._async_client = None
            self._sync_client = None

    async def _create_schema(self):
        """Create necessary database schema for analytics."""
        if not self._sync_client:
            return

        # Create tables for time-series analytics
        tables = [
            """
            CREATE TABLE IF NOT EXISTS metacognitive_events (
                timestamp DateTime,
                event_type String,
                session_id String,
                worker_id String,
                kind String,
                message String,
                payload String
            ) ENGINE = MergeTree()
            PARTITION BY toYYYYMM(timestamp)
            ORDER BY (timestamp, session_id)
            TTL timestamp + INTERVAL 90 DAY
            """,
            """
            CREATE TABLE IF NOT EXISTS performance_metrics (
                timestamp DateTime,
                metric_name String,
                value Float64,
                tags String,
                source String
            ) ENGINE = MergeTree()
            PARTITION BY toYYYYMM(timestamp)
            ORDER BY (timestamp, metric_name)
            TTL timestamp + INTERVAL 180 DAY
            """,
            """
            CREATE TABLE IF NOT EXISTS user_interactions (
                timestamp DateTime,
                user_id String,
                interaction_type String,
                content String,
                metadata String,
                response_time_ms UInt32
            ) ENGINE = MergeTree()
            PARTITION BY toYYYYMM(timestamp)
            ORDER BY (timestamp, user_id, interaction_type)
            TTL timestamp + INTERVAL 365 DAY
            """,
            """
            CREATE TABLE IF NOT EXISTS system_health (
                timestamp DateTime,
                component String,
                metric_name String,
                value Float64,
                status String,
                details String
            ) ENGINE = MergeTree()
            PARTITION BY toYYYYMM(timestamp)
            ORDER BY (timestamp, component, metric_name)
            TTL timestamp + INTERVAL 30 DAY
            """
        ]

        for table_sql in tables:
            try:
                self._sync_client.execute(table_sql)
            except Exception as e:
                print(f"Error creating table: {e}")

    async def store_event(self, event_data: Dict[str, Any]) -> bool:
        """Store metacognitive event in ClickHouse."""
        if not self._sync_client:
            return False

        try:
            self._sync_client.execute("""
                INSERT INTO metacognitive_events
                (timestamp, event_type, session_id, worker_id, kind, message, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                event_data.get('timestamp', '1970-01-01 00:00:00'),
                event_data.get('event_type', 'unknown'),
                event_data.get('session_id', ''),
                event_data.get('worker_id', ''),
                event_data.get('kind', ''),
                event_data.get('message', ''),
                json.dumps(event_data.get('payload', {}))
            ))
            return True
        except Exception as e:
            print(f"Error storing event: {e}")
            return False

    async def store_metric(self, metric_data: Dict[str, Any]) -> bool:
        """Store performance metric in ClickHouse."""
        if not self._sync_client:
            return False

        try:
            self._sync_client.execute("""
                INSERT INTO performance_metrics
                (timestamp, metric_name, value, tags, source)
                VALUES (?, ?, ?, ?, ?)
            """, (
                metric_data.get('timestamp', '1970-01-01 00:00:00'),
                metric_data.get('metric_name', ''),
                metric_data.get('value', 0.0),
                json.dumps(metric_data.get('tags', {})),
                metric_data.get('source', 'unknown')
            ))
            return True
        except Exception as e:
            print(f"Error storing metric: {e}")
            return False

    async def store_interaction(self, interaction_data: Dict[str, Any]) -> bool:
        """Store user interaction in ClickHouse."""
        if not self._sync_client:
            return False

        try:
            self._sync_client.execute("""
                INSERT INTO user_interactions
                (timestamp, user_id, interaction_type, content, metadata, response_time_ms)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                interaction_data.get('timestamp', '1970-01-01 00:00:00'),
                interaction_data.get('user_id', 'anonymous'),
                interaction_data.get('interaction_type', 'unknown'),
                interaction_data.get('content', ''),
                json.dumps(interaction_data.get('metadata', {})),
                interaction_data.get('response_time_ms', 0)
            ))
            return True
        except Exception as e:
            print(f"Error storing interaction: {e}")
            return False

    async def store_health_metric(self, health_data: Dict[str, Any]) -> bool:
        """Store system health metric in ClickHouse."""
        if not self._sync_client:
            return False

        try:
            self._sync_client.execute("""
                INSERT INTO system_health
                (timestamp, component, metric_name, value, status, details)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                health_data.get('timestamp', '1970-01-01 00:00:00'),
                health_data.get('component', 'unknown'),
                health_data.get('metric_name', ''),
                health_data.get('value', 0.0),
                health_data.get('status', 'unknown'),
                json.dumps(health_data.get('details', {}))
            ))
            return True
        except Exception as e:
            print(f"Error storing health metric: {e}")
            return False

    async def query_events(self, event_type: str = None, hours: int = 24) -> List[Dict[str, Any]]:
        """Query metacognitive events from ClickHouse."""
        if not self._async_client:
            return []

        try:
            query = f"""
                SELECT *
                FROM metacognitive_events
                WHERE timestamp >= now() - INTERVAL {hours} HOUR
                {{event_filter}}
                ORDER BY timestamp DESC
                LIMIT 1000
            """

            event_filter = ""
            if event_type:
                event_filter = f"AND event_type = '{event_type}'"

            query = query.replace("{event_filter}", event_filter)

            result = await self._async_client.fetch(query)
            return [dict(row) for row in result]

        except Exception as e:
            print(f"Error querying events: {e}")
            return []

    async def get_performance_analytics(self, metric_name: str = None, hours: int = 24) -> Dict[str, Any]:
        """Get performance analytics from ClickHouse."""
        if not self._async_client:
            return {}

        try:
            where_clause = f"timestamp >= now() - INTERVAL {hours} HOUR"
            if metric_name:
                where_clause += f" AND metric_name = '{metric_name}'"

            query = f"""
                SELECT
                    metric_name,
                    count(*) as count,
                    avg(value) as avg_value,
                    min(value) as min_value,
                    max(value) as max_value,
                    quantile(0.5)(value) as median_value,
                    quantile(0.95)(value) as p95_value
                FROM performance_metrics
                WHERE {where_clause}
                GROUP BY metric_name
                ORDER BY count DESC
                LIMIT 50
            """

            result = await self._async_client.fetch(query)
            analytics = {}

            for row in result:
                analytics[row['metric_name']] = {
                    'count': row['count'],
                    'avg_value': row['avg_value'],
                    'min_value': row['min_value'],
                    'max_value': row['max_value'],
                    'median_value': row['median_value'],
                    'p95_value': row['p95_value']
                }

            return {
                'analytics': analytics,
                'time_range_hours': hours,
                'total_metrics': len(analytics)
            }

        except Exception as e:
            print(f"Error getting performance analytics: {e}")
            return {}

    async def get_user_behavior_insights(self, hours: int = 168) -> Dict[str, Any]:  # 7 days
        """Get user behavior insights from ClickHouse."""
        if not self._async_client:
            return {}

        try:
            query = f"""
                SELECT
                    interaction_type,
                    count(*) as total_interactions,
                    avg(response_time_ms) as avg_response_time,
                    quantile(0.95)(response_time_ms) as p95_response_time,
                    count(distinct user_id) as unique_users
                FROM user_interactions
                WHERE timestamp >= now() - INTERVAL {hours} HOUR
                GROUP BY interaction_type
                ORDER BY total_interactions DESC
                LIMIT 20
            """

            result = await self._async_client.fetch(query)
            insights = {}

            for row in result:
                insights[row['interaction_type']] = {
                    'total_interactions': row['total_interactions'],
                    'avg_response_time': row['avg_response_time'],
                    'p95_response_time': row['p95_response_time'],
                    'unique_users': row['unique_users']
                }

            return {
                'behavior_insights': insights,
                'analysis_period_hours': hours
            }

        except Exception as e:
            print(f"Error getting user behavior insights: {e}")
            return {}

    async def health_check(self) -> Dict[str, Any]:
        """Perform ClickHouse health check."""
        if not self._sync_client:
            return {"healthy": False, "reason": "not_initialized"}

        try:
            result = self._sync_client.execute("SELECT 1")
            if result and result[0][0] == 1:
                return {"healthy": True}
            else:
                return {"healthy": False, "reason": "unexpected_result"}
        except Exception as e:
            return {"healthy": False, "reason": str(e)}


# Global ClickHouse instance
_clickhouse_instance = None

async def get_clickhouse_manager() -> ClickHouseManager:
    """Get global ClickHouse manager instance."""
    global _clickhouse_instance
    if _clickhouse_instance is None:
        config = ClickHouseConfig(
            host=os.getenv("CLICKHOUSE_HOST", "localhost"),
            port=int(os.getenv("CLICKHOUSE_PORT", "9000")),
            http_port=int(os.getenv("CLICKHOUSE_HTTP_PORT", "8123")),
            database=os.getenv("CLICKHOUSE_DB", "denis_analytics"),
            user=os.getenv("CLICKHOUSE_USER", "default"),
            password=os.getenv("CLICKHOUSE_PASSWORD", ""),
            connection_timeout=int(os.getenv("CLICKHOUSE_CONN_TIMEOUT", "30")),
            read_timeout=int(os.getenv("CLICKHOUSE_READ_TIMEOUT", "300"))
        )

        _clickhouse_instance = ClickHouseManager(config)
        await _clickhouse_instance.initialize()

    return _clickhouse_instance
