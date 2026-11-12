"""Validate files that must be present in a standalone registry repository."""
import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ("LICENSE", "README.md", "pyproject.toml", "requirements.txt", "__init__.py", "nodes.py",
            "_vendor/detailx_sdk/client.py", "example_api_workflow.json", "README.zh-CN.md",
            "workflows/quote.json", "workflows/upscale.json")


def check():
    for name in REQUIRED:
        if not (ROOT / name).is_file():
            raise SystemExit("Missing release file: " + name)
    metadata = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    if "REPLACE_" in metadata:
        raise SystemExit("Fill publisher and repository metadata before publishing")
    workflow = json.loads((ROOT / "example_api_workflow.json").read_text())
    for node in workflow.values():
        if node["class_type"] == "DetailXSubmit":
            assert node["inputs"]["confirm_charge"] is False
            assert node["inputs"]["max_precharge_credits"] == 0
    for path in (ROOT / "workflows").glob("*.json"):
        editor = json.loads(path.read_text())
        nodes = {node["id"]: node for node in editor["nodes"]}
        for node in nodes.values():
            if node["type"] == "DetailXSubmit":
                assert node["widgets_values"] == [False, 0], "Example must require explicit billing authorization"
        for link_id, origin, output, target, input_slot, _ in editor["links"]:
            assert link_id in nodes[origin]["outputs"][output]["links"]
            assert nodes[target]["inputs"][input_slot]["link"] == link_id
    for path in ROOT.rglob("*"):
        relative = path.relative_to(ROOT)
        if any(part in (".git", ".venv", "__pycache__", ".pytest_cache") for part in relative.parts):
            continue
        if not path.is_file():
            continue
        if path.name == ".env" or ".sqlite3" in path.name:
            raise SystemExit("Private runtime file in publication tree: " + str(relative))
        if path.suffix == ".py":
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(relative))
            for item in ast.walk(tree):
                if isinstance(item, ast.Call) and isinstance(item.func, ast.Name) and item.func.id in ("eval", "exec"):
                    raise SystemExit("Registry prohibits eval/exec: " + str(relative))
        if path.suffix in (".py", ".md", ".toml", ".json", ".yml", ".yaml", ".txt", ".example"):
            text = path.read_text(encoding="utf-8")
            if re.search(r"dxk_[A-Za-z0-9_-]{24,}|pat-[0-9a-f]{8}-[0-9a-f-]{27,}", text):
                raise SystemExit("Possible live credential in publication tree: " + str(relative))
    print("Release files, example billing defaults and source checks passed")


if __name__ == "__main__":
    check()
