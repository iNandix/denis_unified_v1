"""SymbolExtractor — extrae funciones, clases y métodos de ficheros Python."""

import ast
import pathlib
from typing import List, Dict, Any


class SymbolExtractor:
    def extract(self, abs_path: str) -> List[Dict[str, Any]]:
        """
        Extrae símbolos (funciones, clases, métodos) de un ficheor .py.
        Retorna lista de dicts: {name, kind, path, lineno}.
        """
        try:
            source = pathlib.Path(abs_path).read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return [
                {
                    "name": pathlib.Path(abs_path).stem,
                    "kind": "module",
                    "path": abs_path,
                    "lineno": 0,
                }
            ]

        syms = []
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return [
                {
                    "name": pathlib.Path(abs_path).stem,
                    "kind": "module",
                    "path": abs_path,
                    "lineno": 0,
                }
            ]

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                syms.append(
                    {"name": node.name, "kind": "class", "path": abs_path, "lineno": node.lineno}
                )
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                syms.append(
                    {"name": node.name, "kind": "function", "path": abs_path, "lineno": node.lineno}
                )

        if not syms:
            syms.append(
                {
                    "name": pathlib.Path(abs_path).stem,
                    "kind": "module",
                    "path": abs_path,
                    "lineno": 0,
                }
            )
        return syms
