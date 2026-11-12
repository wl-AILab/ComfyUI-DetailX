"""Generate editor-format examples with explicit native VIDEO connections."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def node(identifier, kind, position, size, inputs, outputs, widgets):
    return {"id": identifier, "type": kind, "pos": position, "size": size, "flags": {},
            "order": identifier - 1, "mode": 0, "inputs": inputs,
            "outputs": [{"name": name, "type": dtype, "links": []} for name, dtype in outputs],
            "properties": {"Node name for S&R": kind}, "widgets_values": widgets}


def socket(name, dtype, widget=False):
    value = {"name": name, "type": dtype, "link": None}
    if widget:
        value["widget"] = {"name": name}
    return value


def workflow(full):
    nodes = [
        node(1, "LoadVideo", [40, 100], [300, 280], [], [("VIDEO", "VIDEO")], ["sample.mp4"]),
        node(2, "DetailXUploadVideo", [390, 100], [300, 120], [socket("video", "VIDEO")],
             [("upload_id", "STRING"), ("upload_session_json", "STRING")], ["example-upload-001"]),
        node(3, "DetailXQuote", [740, 100], [320, 330], [socket("upload_id", "STRING", True)],
             [("prepared", "DETAILX_PREPARED"), ("estimated_credits", "INT"), ("quote_json", "STRING")],
             ["", "", "example-generation-001", "4K", "preserve", "default", "default", "default", "default", "default"]),
        node(7, "PreviewAny", [740, 510], [420, 330], [socket("source", "*")], [("STRING", "STRING")], []),
    ]
    if full:
        nodes.extend([
            node(4, "DetailXSubmit", [1120, 100], [310, 150], [socket("prepared", "DETAILX_PREPARED")],
                 [("generation_id", "STRING"), ("generation_json", "STRING")], [False, 0]),
            node(5, "DetailXFetchVideo", [1480, 100], [310, 140], [socket("generation_id", "STRING", True)],
                 [("video", "VIDEO"), ("result_json", "STRING")], ["", 1800]),
            node(6, "SaveVideo", [1840, 100], [340, 340], [socket("video", "VIDEO")], [("video", "VIDEO")],
                 ["DetailX/enhanced", "auto", "auto"]),
            node(8, "PreviewAny", [1480, 510], [420, 330], [socket("source", "*")], [("STRING", "STRING")], []),
        ])
    by_id = {value["id"]: value for value in nodes}
    links = []

    def connect(origin, output, target, input_slot, dtype):
        identifier = len(links) + 1
        links.append([identifier, origin, output, target, input_slot, dtype])
        by_id[origin]["outputs"][output]["links"].append(identifier)
        by_id[target]["inputs"][input_slot]["link"] = identifier

    connect(1, 0, 2, 0, "VIDEO")
    connect(2, 0, 3, 0, "STRING")
    connect(3, 2, 7, 0, "STRING")
    if full:
        connect(3, 0, 4, 0, "DETAILX_PREPARED")
        connect(4, 0, 5, 0, "STRING")
        connect(5, 0, 6, 0, "VIDEO")
        connect(5, 1, 8, 0, "STRING")
    for value in nodes:
        for output in value["outputs"]:
            if not output["links"]:
                output["links"] = None
    return {"last_node_id": max(by_id), "last_link_id": len(links), "nodes": nodes, "links": links,
            "groups": [], "config": {}, "extra": {"ds": {"scale": 0.75 if full else 0.9, "offset": [20, 20]}},
            "version": 0.4}


if __name__ == "__main__":
    destination = ROOT / "workflows"
    destination.mkdir(exist_ok=True)
    for name, full in (("quote", False), ("upscale", True)):
        (destination / (name + ".json")).write_text(json.dumps(workflow(full), indent=2) + "\n", encoding="utf-8")
    print("Generated quote and upscale editor workflows")
