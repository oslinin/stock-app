"""AGPL hygiene: optopsy is AGPL-licensed and lives ONLY in the
separate optopsy-worker process (own pyproject.toml, HTTP-only boundary
with the backend — no shared imports, no shared DB file). This backend
package must never import it."""

import ast
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1] / "app"


def _imports_optopsy(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(a.name.split(".")[0] == "optopsy" for a in node.names):
            return True
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "optopsy":
            return True
    return False


def test_backend_never_imports_optopsy():
    """AST, not a text/substring search — a comment or docstring that
    merely *mentions* "optopsy" (like config.py's own settings comments)
    must not trip this; only an actual import statement should."""
    hits = [
        str(path.relative_to(APP_ROOT.parent))
        for path in APP_ROOT.rglob("*.py")
        if _imports_optopsy(ast.parse(path.read_text(), filename=str(path)))
    ]
    assert hits == [], f"app/ must never import optopsy (AGPL isolation) — found in: {hits}"
