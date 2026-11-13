"""Modules talk to each other only through `service.py` / `events.py`,
and only to modules declared in `depends_on` (or whose events they listen to).
This keeps every module replaceable and makes a bug's blast radius predictable."""

import ast
from pathlib import Path

from app.modules import ALL_MODULES

MODULES_DIR = Path(__file__).resolve().parents[1] / "app" / "modules"
PUBLIC = {"service", "events"}
ALLOWED = {m.name: set(m.depends_on) for m in ALL_MODULES}
EMITTERS = {e: m.name for m in ALL_MODULES for e in m.emits}
for m in ALL_MODULES:
    ALLOWED[m.name] |= {EMITTERS[e] for e in m.listens_to}


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            out.append(node.module)
        elif isinstance(node, ast.Import):
            out.extend(a.name for a in node.names)
    return out


def test_cross_module_imports_respect_boundaries():
    problems: list[str] = []
    for owner in ALLOWED:
        for file in (MODULES_DIR / owner).rglob("*.py"):
            for mod in _imports(file):
                parts = mod.split(".")
                if parts[:2] != ["app", "modules"] or len(parts) < 3 or parts[2] == owner:
                    continue
                other = parts[2]
                where = f"{file.relative_to(MODULES_DIR)} imports {mod}"
                if other not in ALLOWED[owner]:
                    problems.append(f"{where}: '{other}' is not in depends_on of '{owner}'")
                elif len(parts) < 4 or parts[3] not in PUBLIC:
                    problems.append(f"{where}: only {other}.service / {other}.events are public")
    assert not problems, "\n".join(problems)
