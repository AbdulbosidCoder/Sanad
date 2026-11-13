"""The module map must stay truthful: these tests fail if it drifts from the code."""

from pathlib import Path

from app.modules import ALL_MODULES

MODULES_DIR = Path(__file__).resolve().parents[1] / "app" / "modules"
NAMES = {m.name for m in ALL_MODULES}


def test_every_module_directory_is_registered():
    dirs = {p.name for p in MODULES_DIR.iterdir() if p.is_dir() and not p.name.startswith("_")}
    assert dirs == NAMES


def test_every_module_has_readme_and_layers():
    for name in NAMES:
        for f in ("README.md", "module.py", "api.py", "service.py", "events.py"):
            assert (MODULES_DIR / name / f).is_file(), f"{name}/{f} missing"


def test_dependencies_exist_and_have_no_cycles():
    deps = {m.name: set(m.depends_on) for m in ALL_MODULES}
    for name, ds in deps.items():
        assert ds <= NAMES, f"{name} depends on unknown modules {ds - NAMES}"
        assert name not in ds

    visiting: set[str] = set()
    done: set[str] = set()

    def visit(n: str, path: list[str]) -> None:
        assert n not in visiting, "dependency cycle: " + " -> ".join([*path, n])
        if n in done:
            return
        visiting.add(n)
        for d in deps[n]:
            visit(d, [*path, n])
        visiting.discard(n)
        done.add(n)

    for n in deps:
        visit(n, [])


def test_listened_events_are_emitted_by_someone():
    emitted = {e for m in ALL_MODULES for e in m.emits}
    for m in ALL_MODULES:
        missing = set(m.listens_to) - emitted
        assert not missing, f"{m.name} listens to events nobody emits: {missing}"


async def test_modules_endpoint_lists_all(client):
    r = await client.get("/api/v1/system/modules")
    assert r.status_code == 200
    assert {m["name"] for m in r.json()["modules"]} == NAMES
