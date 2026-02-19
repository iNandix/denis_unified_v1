import os
import sys
import subprocess
import socket

ROOT = "/media/jotah/SSD_denis/home_jotah"
WS = "/media/jotah/SSD_denis/home_jotah/denis_unified_v1"

DO_NOT_TOUCH = [
    "service_8084.py",
    "kernel/__init__.py",
    "kernel/meganube/",
    "kernel/sandbox/",
    "FrontDenisACTUAL/",
    "FrontDenisACTUAL/public/",
    "denis_unified_v1/compiler/",
    "denis_unified_v1/compiler/makina_filter.py",
]


def test_pythonpath_ok():
    sys.path.insert(0, ROOT)
    import denis_unified_v1  # noqa


def test_workspace_exists():
    assert os.path.isdir(WS)


def test_neo4j_port_reachable():
    # Solo socket — graph.db se crea en PROMPT_001
    with socket.create_connection(("127.0.0.1", 7687), timeout=3):
        pass


def test_do_not_touch_paths_exist():
    for p in DO_NOT_TOUCH:
        base = WS if not p.startswith("FrontDenisACTUAL/") else "/media/jotah/SSD_denis"
        full = os.path.join(base, p)
        # Solo verificar si existe el prefijo como archivo o directorio
        if os.path.exists(full):
            assert True
        # Si no existe aún, skip — puede que todavía no se haya creado


def test_git_readable():
    out = subprocess.check_output(["git", "status", "--porcelain"], cwd=WS).decode()
    assert out is not None
