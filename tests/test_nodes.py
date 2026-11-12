import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("comfyui_detailx", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
package = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = package
spec.loader.exec_module(package)
nodes = sys.modules[spec.name + ".nodes"]


@pytest.fixture
def service(tmp_path):
    counts = {"quote": 0, "submit": 0}

    def respond(request):
        if request.url.path.endswith("/generation-estimates"):
            counts["quote"] += 1
            return httpx.Response(200, json={"credits": 10, "pricing_revision_id": 1})
        if request.method == "POST" and request.url.path.endswith("/generations"):
            counts["submit"] += 1
            return httpx.Response(202, json={"id": "generation-one", "status": "queued"})
        if request.method == "GET" and request.url.path.endswith("/generations/generation-one"):
            return httpx.Response(200, json={"id": "generation-one", "status": "processing"})
        raise AssertionError("Unexpected API call: " + request.url.path)

    def client():
        return nodes.DetailXClient("dxk_unit_test", base_url="https://detailx.invalid/api/v1", state_dir=tmp_path,
                                  transport=httpx.MockTransport(respond), sleep=lambda _: None)

    with patch.object(nodes, "client", client), patch.object(nodes, "progress", lambda _: None):
        yield counts


def prepare(request_id="generation-one", resolution="720p"):
    return nodes.DetailXQuote().run("upload-one", "", request_id, resolution, "preserve")["result"][0]


def test_confirmation_and_budget_reject_before_any_generation(service):
    prepared = prepare()
    with pytest.raises(Exception, match="confirm_charge"):
        nodes.DetailXSubmit().run(prepared, False, 10)
    with pytest.raises(Exception, match="max_precharge_credits"):
        nodes.DetailXSubmit().run(prepared, True, 9)
    assert service == {"quote": 1, "submit": 0}


def test_recreated_clients_reuse_one_paid_generation(service):
    prepared = prepare()
    first = nodes.DetailXSubmit().run(prepared, True, 10)
    repeated = nodes.DetailXSubmit().run(prepare(), True, 10)
    assert first["result"][0] == repeated["result"][0] == "generation-one"
    assert service == {"quote": 1, "submit": 1}


def test_changed_parameters_require_a_new_business_id(service):
    prepare()
    with pytest.raises(Exception):
        prepare(resolution="4K")
    assert service == {"quote": 1, "submit": 0}


def test_published_example_cannot_charge_without_editing():
    workflow = json.loads((ROOT / "example_api_workflow.json").read_text())
    submit = next(value for value in workflow.values() if value["class_type"] == "DetailXSubmit")
    assert submit["inputs"]["confirm_charge"] is False
    assert submit["inputs"]["max_precharge_credits"] == 0
