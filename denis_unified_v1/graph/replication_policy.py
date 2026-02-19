"""Replication policy for Neo4j operations."""

from enum import Enum


class ReplicationMode(str, Enum):
    """Replication modes for graph operations."""

    SINGLE_WRITER = "single-writer"
    MULTI_WRITER = "multi-writer"
    READ_ONLY = "read-only"


class ReplicationPolicy:
    """Policy for managing replication and consistency."""

    def __init__(self, mode: ReplicationMode = ReplicationMode.SINGLE_WRITER):
        self.mode = mode

    def can_write(self) -> bool:
        """Check if writes are allowed in current mode."""
        return self.mode in (ReplicationMode.SINGLE_WRITER, ReplicationMode.MULTI_WRITER)

    def can_read(self) -> bool:
        """Check if reads are allowed."""
        return True

    def is_single_writer(self) -> bool:
        """Check if single-writer mode is enabled."""
        return self.mode == ReplicationMode.SINGLE_WRITER


def get_replication_policy() -> ReplicationPolicy:
    """Get the current replication policy."""
    return ReplicationPolicy(mode=ReplicationMode.SINGLE_WRITER)
