import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("comfyui_detailx", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
package = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = package
spec.loader.exec_module(package)

# pytest names a hyphenated custom-node root "__init__" during package setup.
if not ROOT.name.isidentifier():
    sys.modules.setdefault("__init__", package)
