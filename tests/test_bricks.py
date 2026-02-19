"""Tests for control plane bricks."""

import os
import sys
import tempfile
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from control_plane.models import ContextPack
from control_plane.repo_context import RepoContext
from control_plane.cp_queue import CPQueue


def test_contextpack_to_dict_from_dict_roundtrip():
    cp = ContextPack(cp_id="test-123", mission="test mission")
    cp.files_to_read = ["file1.py", "file2.ts"]
    d = cp.to_dict()
    cp2 = ContextPack.from_dict(d)
    assert cp2.cp_id == cp.cp_id
    assert cp2.mission == cp.mission
    assert cp2.files_to_read == ["file1.py", "file2.ts"]
    print("✅ to_dict/from_dict roundtrip")


def test_contextpack_is_expired_after_120s():
    cp = ContextPack(cp_id="test-exp", mission="test")
    assert not cp.is_expired()
    cp.expires_at = datetime.utcnow() - timedelta(seconds=1)
    assert cp.is_expired()
    print("✅ is_expired works")


def test_contextpack_to_json_from_json():
    cp = ContextPack(cp_id="test-json", mission="json test")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
    try:
        cp.to_json(path)
        cp2 = ContextPack.from_json(path)
        assert cp2.cp_id == cp.cp_id
        print("✅ to_json/from_json works")
    finally:
        os.unlink(path)


def test_repo_context_finds_git_root():
    rc = RepoContext()
    assert rc.git_root
    assert ".git" in os.listdir(rc.git_root) or os.path.isdir(os.path.join(rc.git_root, ".git"))
    print("✅ git root found")


def test_repo_id_deterministic():
    rc = RepoContext()
    rc2 = RepoContext()
    assert rc.repo_id == rc2.repo_id
    print("✅ repo_id deterministic")


def test_repo_id_different_repos():
    rc1 = RepoContext("/tmp")
    rc2 = RepoContext("/media/jotah/SSD_denis")
    assert rc1.repo_id != rc2.repo_id
    print("✅ different repos have different IDs")


def test_repo_context_no_git_fallback():
    with tempfile.TemporaryDirectory() as tmpdir:
        rc = RepoContext(tmpdir)
        assert rc.git_root == tmpdir
    print("✅ no git fallback works")


def test_cpqueue_push_pop():
    q = CPQueue("/tmp/test_cpqueue.json")
    q._queue = []
    cp = ContextPack(cp_id="push-pop", mission="test")
    q.push(cp)
    cp2 = q.pop()
    assert cp2.cp_id == "push-pop"
    print("✅ push/pop works")


def test_cpqueue_max_5_purges_oldest():
    q = CPQueue("/tmp/test_cpqueue_max.json")
    q._queue = []
    for i in range(6):
        q.push(ContextPack(cp_id=f"cp-{i}", mission=f"test-{i}"))
    assert len(q._queue) == 5
    assert q._queue[0].cp_id == "cp-1"
    print("✅ max 5 purges oldest")


def test_cpqueue_persists_to_disk():
    q = CPQueue("/tmp/test_cpqueue_persist.json")
    q._queue = []
    q.push(ContextPack(cp_id="persist", mission="persist-test"))
    q2 = CPQueue("/tmp/test_cpqueue_persist.json")
    assert len(q2._queue) == 1
    assert q2._queue[0].cp_id == "persist"
    os.unlink("/tmp/test_cpqueue_persist.json")
    print("✅ persists to disk")


def test_cpqueue_purge_expired():
    q = CPQueue("/tmp/test_cpqueue_expire.json")
    q._queue = []
    cp = ContextPack(cp_id="expire", mission="test")
    cp.expires_at = datetime.utcnow() - timedelta(seconds=1)
    q.push(cp)
    q.push(ContextPack(cp_id="not-expire", mission="test2"))
    removed = q.purge_expired()
    assert removed == 1
    assert len(q._queue) == 1
    os.unlink("/tmp/test_cpqueue_expire.json")
    print("✅ purge_expired works")


if __name__ == "__main__":
    test_contextpack_to_dict_from_dict_roundtrip()
    test_contextpack_is_expired_after_120s()
    test_contextpack_to_json_from_json()
    test_repo_context_finds_git_root()
    test_repo_id_deterministic()
    test_repo_id_different_repos()
    test_repo_context_no_git_fallback()
    test_cpqueue_push_pop()
    test_cpqueue_max_5_purges_oldest()
    test_cpqueue_persists_to_disk()
    test_cpqueue_purge_expired()
    print("\n✅ All tests passed!")
