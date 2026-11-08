import ast
from pathlib import Path


def test_application_schemas_do_not_import_database_or_mappers() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "application"
    paths = [path for path in root.rglob("contracts/*.py") if path.stem != "mappers"]
    assert paths
    for path in paths:
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            elif isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            else:
                continue
            for module in modules:
                assert ".database" not in module, (path, module)
                assert not module.endswith(".mappers"), (path, module)
                assert not module.startswith("api."), (path, module)
