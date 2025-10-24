# server.py
import argparse
import json
import os
import threading
import time
from typing import Dict, List, Optional

import requests
from flask import Flask, jsonify, request
from flask_cors import CORS

import ZODB, ZODB.FileStorage, transaction
from BTrees.OOBTree import OOBTree


DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
CLUSTER_STATE_FILE = os.path.join(DATA_DIR, "cluster_state.json")

DEFAULT_NODES = {
    "node_A": "http://127.0.0.1:5000",
    "node_B": "http://127.0.0.1:5001",
    "node_C": "http://127.0.0.1:5002",
}


def read_cluster_state() -> Dict:
    """Return cluster state: {'primary': 'node_A', 'replication_status': {..}}"""
    if not os.path.exists(CLUSTER_STATE_FILE):
        # initialize
        initial = {
            "primary": "node_A",
            "replication_status": {k: "synced" for k in DEFAULT_NODES.keys()}
        }
        write_cluster_state(initial)
        return initial
    with open(CLUSTER_STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def write_cluster_state(state: Dict):
    with open(CLUSTER_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

parser = argparse.ArgumentParser()
parser.add_argument("--name", type=str, default="node_A", help="node name (node_A/node_B/node_C)")
parser.add_argument("--port", type=int, default=5000, help="port to run the flask app")
parser.add_argument("--nodes-file", type=str, default=None, help="optional json mapping file for nodes")
args = parser.parse_args()

NODE_NAME = args.name
PORT = args.port


if args.nodes_file:
    with open(args.nodes_file, "r", encoding="utf-8") as f:
        nodes_map = json.load(f)
else:
    nodes_map = DEFAULT_NODES


if NODE_NAME not in nodes_map:
    raise SystemExit(f"NODE_NAME {NODE_NAME} not in nodes_map keys: {list(nodes_map.keys())}")

app = Flask(__name__)
CORS(app)


def get_fs_path(node_name: str) -> str:
    return os.path.join(DATA_DIR, f"{node_name}.fs")

def open_db(node_name: str):
    """Open the ZODB DB for given node_name and return (db, conn, root). Caller should close conn/db when done."""
    path = get_fs_path(node_name)
    storage = ZODB.FileStorage.FileStorage(path)
    db = ZODB.DB(storage)
    conn = db.open()
    root = conn.root()
    return db, conn, root

def init_node_db_if_missing(node_name: str):
    """Ensure the node's fs exists and has required collections."""
    path = get_fs_path(node_name)
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        db, conn, root = open_db(node_name)
        if "people" not in root:
            root["people"] = OOBTree()
        if "versions" not in root:
            root["versions"] = OOBTree()
        if "redo_stack" not in root:
            root["redo_stack"] = OOBTree()
        transaction.commit()
        conn.close()
        db.close()


for n in nodes_map.keys():
    init_node_db_if_missing(n)


db, conn, root = open_db(NODE_NAME)


if "people" not in root:
    root["people"] = OOBTree()
if "versions" not in root:
    root["versions"] = OOBTree()
if "redo_stack" not in root:
    root["redo_stack"] = OOBTree()
transaction.commit()


def get_local_people_list():
    """Read people from this node's ZODB root and return list of plain dicts."""
    out = []
    for k, p in root["people"].items():

        if hasattr(p, "name") and hasattr(p, "age"):
            out.append({"id": k, "name": p.name, "age": p.age})
        elif isinstance(p, dict):
            out.append(p)
        else:

            out.append({"id": k, "repr": str(p)})
    return out

def replace_local_people_from_list(list_people: List[Dict]):

    ppl = OOBTree()
    versions = root.get("versions", OOBTree())
    redo_stack = root.get("redo_stack", OOBTree())


    for p in list_people:
        pid = p.get("id")
        ppl[pid] = {"id": pid, "name": p.get("name"), "age": int(p.get("age", 0))}

        versions[pid] = [ppl[pid].copy()]
        redo_stack[pid] = []


    for existing_pid in list(root.get("versions", {}).keys()):
        if existing_pid not in ppl:
            versions.pop(existing_pid, None)
            redo_stack.pop(existing_pid, None)

    root["people"] = ppl
    root["versions"] = versions
    root["redo_stack"] = redo_stack
    transaction.commit()

def is_primary() -> bool:
    state = read_cluster_state()
    return state.get("primary") == NODE_NAME

def update_replication_status_for(node_name: str, status: str):
    state = read_cluster_state()
    rs = state.get("replication_status", {})
    rs[node_name] = status
    state["replication_status"] = rs
    write_cluster_state(state)

def _ensure_history_structures():
    """Đảm bảo tất cả các cấu trúc ZODB tồn tại."""
    if "people" not in root:
        root["people"] = {}
    if "versions" not in root:
        root["versions"] = {}
    if "redo_stack" not in root:
        root["redo_stack"] = {}
    if "deleted_people" not in root:
        root["deleted_people"] = {}

def push_version(pid: str, snapshot: Optional[Dict]):

    _ensure_history_structures()
    versions = root["versions"]
    if pid not in versions:
        versions[pid] = []
    versions[pid].append(None if snapshot is None else snapshot.copy())
    transaction.commit()

def clear_redo(pid: str):
    _ensure_history_structures()
    redo = root["redo_stack"]
    redo[pid] = []
    transaction.commit()

def push_redo(pid: str, snapshot: Optional[Dict]):
    _ensure_history_structures()
    redo = root["redo_stack"]
    if pid not in redo:
        redo[pid] = []
    redo[pid].append(None if snapshot is None else snapshot.copy())
    transaction.commit()

def pop_redo(pid: str) -> Optional[Dict]:
    _ensure_history_structures()
    redo = root["redo_stack"]
    if pid not in redo or len(redo[pid]) == 0:
        return None
    item = redo[pid].pop()
    transaction.commit()
    return item

def pop_version(pid: str) -> Optional[Dict]:
    _ensure_history_structures()
    versions = root["versions"]
    if pid not in versions or len(versions[pid]) <= 1:
        # if only one (or zero) version, cannot pop to previous
        return None
    # pop latest and return it
    latest = versions[pid].pop()
    transaction.commit()
    return latest

def get_history_list(pid: str) -> List[Dict]:
    _ensure_history_structures()
    versions = root["versions"]
    if pid not in versions:
        return []
    # return copies to avoid exposing persistent objects
    out = []
    for v in versions[pid]:
        out.append(None if v is None else v.copy())
    return out


@app.route("/whoami", methods=["GET"])
def whoami():
    state = read_cluster_state()
    return jsonify({
        "node": NODE_NAME,
        "url": nodes_map[NODE_NAME],
        "primary": state.get("primary"),
        "replication_status": state.get("replication_status", {})
    })


AUTO_REPLICATE_AFTER_WRITE = False  

def background_replicate(payload):
    """Send payload (list of dicts) to all replicas (not including primary)."""
    state = read_cluster_state()
    primary = state.get("primary")
    for node, url in nodes_map.items():
        if node == primary:
            continue
        try:
            update_replication_status_for(node, "pending")
            resp = requests.post(f"{url}/sync-data", json=payload, timeout=5)
            if resp.status_code == 200:
                update_replication_status_for(node, "synced")
            else:
                update_replication_status_for(node, "error")
        except Exception as e:
            update_replication_status_for(node, "error")
            app.logger.warning(f"Replicate -> error to {node}: {e}")

@app.route("/people", methods=["GET"])
def get_people():
    """Read all people, including deleted ones."""
    _ensure_history_structures()

    all_people = []

    # --- Người chưa xóa ---
    for pid, p in root["people"].items():
        item = p.copy() if isinstance(p, dict) else {
            "id": pid,
            "name": getattr(p, "name", ""),
            "age": getattr(p, "age", 0)
        }
        item["is_deleted"] = False
        all_people.append(item)

    # --- Người đã xóa ---
    if "deleted_people" in root:
        for pid, p in root["deleted_people"].items():
            item = p.copy() if isinstance(p, dict) else {
                "id": pid,
                "name": getattr(p, "name", ""),
                "age": getattr(p, "age", 0)
            }
            item["is_deleted"] = True
            all_people.append(item)

    # --- Trả về thông tin node ---
    state = read_cluster_state()
    role = "Primary" if state.get("primary") == NODE_NAME else "Replica"

    return jsonify({
        "source": NODE_NAME,
        "data": all_people,
        "role": role,
        "primary": state.get("primary")
    })


@app.route("/people", methods=["POST"])
def add_person():
    payload = request.json or {}
    name = payload.get("name")
    age = int(payload.get("age", 0))
    people = root["people"]
    new_key = f"p{len(people) + 1}"
    new_obj = {"id": new_key, "name": name, "age": age}
    people[new_key] = new_obj
    transaction.commit()

    _ensure_history_structures()
    root["versions"][new_key] = [new_obj.copy()]
    root["redo_stack"][new_key] = []
    transaction.commit()

    if is_primary() and AUTO_REPLICATE_AFTER_WRITE:
        payload_list = get_local_people_list()
        threading.Thread(target=background_replicate, args=(payload_list,), daemon=True).start()

    return jsonify({"status": "ok", "id": new_key, "written_to": NODE_NAME})

@app.route("/people/<pid>", methods=["PUT"])
def update_person(pid):
    if pid not in root["people"]:
        return jsonify({"error": "Not found"}), 404
    data_json = request.json or {}
    p = root["people"][pid]
    # take snapshot of current before change
    prev_snapshot = p.copy() if isinstance(p, dict) else {"id": pid, "name": getattr(p, "name", ""), "age": getattr(p, "age", 0)}
    # apply changes
    if isinstance(p, dict):
        p["name"] = data_json.get("name", p.get("name"))
        p["age"] = int(data_json.get("age", p.get("age", 0)))
        root["people"][pid] = p
    else:
        setattr(p, "name", data_json.get("name", getattr(p, "name", "")))
        setattr(p, "age", int(data_json.get("age", getattr(p, "age", 0))))
    transaction.commit()

    # push previous snapshot to versions (we keep versions as snapshots in chronological order)
    _ensure_history_structures()
    # if versions not exist, initialize with previous and current
    if pid not in root["versions"]:
        root["versions"][pid] = [prev_snapshot.copy(), (root["people"][pid] if isinstance(root["people"][pid], dict) else {"id": pid, "name": getattr(root["people"][pid], "name", ""), "age": getattr(root["people"][pid], "age", 0)})]
    else:

        current_state = root["people"][pid] if isinstance(root["people"][pid], dict) else {"id": pid, "name": getattr(root["people"][pid], "name", ""), "age": getattr(root["people"][pid], "age", 0)}
        root["versions"][pid].append(current_state.copy())

    root["redo_stack"][pid] = []
    transaction.commit()

    if is_primary() and AUTO_REPLICATE_AFTER_WRITE:
        threading.Thread(target=background_replicate, args=(get_local_people_list(),), daemon=True).start()

    return jsonify({"status": "updated", "id": pid})

@app.route("/people/<pid>", methods=["DELETE"])
def delete_person(pid):
    """Xóa mềm 1 bản ghi, có thể Undo lại."""
    _ensure_history_structures()

    if pid not in root["people"]:
        return jsonify({"error": "Not found"}), 404

    # Snapshot trước khi xóa
    prev_snapshot = root["people"][pid].copy() if isinstance(root["people"][pid], dict) else {
        "id": pid,
        "name": getattr(root["people"][pid], "name", ""),
        "age": getattr(root["people"][pid], "age", 0)
    }

    # Lưu lịch sử (để undo được)
    if pid not in root["versions"]:
        root["versions"][pid] = []
    root["versions"][pid].append(prev_snapshot)
    root["redo_stack"][pid] = []  # clear redo

    # Đánh dấu soft delete
    prev_snapshot["is_deleted"] = True
    root["deleted_people"][pid] = prev_snapshot

    # Xóa khỏi danh sách hiển thị chính
    del root["people"][pid]

    transaction.commit()

    # replication tự động
    if is_primary() and AUTO_REPLICATE_AFTER_WRITE:
        threading.Thread(
            target=background_replicate,
            args=(get_local_people_list(),),
            daemon=True
        ).start()

    return jsonify({"status": "deleted", "id": pid})


@app.route("/people/<pid>/history", methods=["GET"])
def get_person_history(pid):
    hist = get_history_list(pid)

    out = []
    for v in hist:
        out.append({"state": None} if v is None else v)
    return jsonify(out)

@app.route("/people/<pid>/undo", methods=["POST"])
def undo_person(pid):
    """Hoàn tác hành động cuối cùng (Undo)."""
    _ensure_history_structures()

    versions = root["versions"]
    redo = root["redo_stack"]

    if pid not in versions or len(versions[pid]) == 0:
        return jsonify({"error": "No previous version to undo"}), 400

    # Lấy bản mới nhất và bản trước đó
    latest = versions[pid].pop()
    prev = versions[pid][-1] if len(versions[pid]) > 0 else None

    # Đẩy vào redo stack
    redo.setdefault(pid, []).append(latest)

    # --- Undo logic ---
    if latest.get("is_deleted", False):
        # Trường hợp undo xóa → khôi phục
        latest["is_deleted"] = False
        root["people"][pid] = latest.copy()
        root["deleted_people"].pop(pid, None)
    elif prev is None:
        # Không có phiên bản cũ → xóa hẳn
        root["people"].pop(pid, None)
        root["deleted_people"].pop(pid, None)
    else:
        if prev.get("is_deleted", False):
            # Phiên bản trước là bản bị xóa → khôi phục lại
            prev["is_deleted"] = False
            root["people"][pid] = prev.copy()
            root["deleted_people"].pop(pid, None)
        else:
            # Bình thường → quay lại bản trước
            root["people"][pid] = prev.copy()

    transaction.commit()

    # Trả về kèm lịch sử để React không crash
    hist = get_history_list(pid)
    return jsonify({
        "status": "undone",
        "id": pid,
        "history": hist
    })




@app.route("/people/<pid>/redo", methods=["POST"])
def redo_person(pid):
    _ensure_history_structures()
    redo = root["redo_stack"]
    if pid not in redo or len(redo[pid]) == 0:
        return jsonify({"error": "No redo available"}), 400

    item = redo[pid].pop()  # item is the state we previously undid (could be None)

    if pid not in root["versions"]:
        root["versions"][pid] = []
    root["versions"][pid].append(item if item is None else item.copy())


    if item is None:
        root["people"].pop(pid, None)
    else:
        root["people"][pid] = item.copy()

    transaction.commit()
    return jsonify({"status": "redone", "id": pid, "history": get_history_list(pid)})

@app.route("/sync-data", methods=["POST"])
def sync_data():
    data = request.json or []
    # Replace local people with payload and reset versions/redo for replaced pids
    replace_local_people_from_list(data)
    update_replication_status_for(NODE_NAME, "synced")
    return jsonify({"status": "synced", "node": NODE_NAME, "count": len(data)})


@app.route("/run-replication", methods=["POST"])
def run_replication():
    state = read_cluster_state()
    primary = state.get("primary")
    if NODE_NAME != primary:
        return jsonify({"error": "Only primary can run replication", "primary": primary}), 403

    payload = get_local_people_list()
    # replicate synchronously (will update cluster_state statuses)
    for node, url in nodes_map.items():
        if node == primary:
            continue
        try:
            update_replication_status_for(node, "pending")
            r = requests.post(f"{url}/sync-data", json=payload, timeout=5)
            if r.status_code == 200:
                update_replication_status_for(node, "synced")
            else:
                update_replication_status_for(node, "error")
        except Exception as e:
            update_replication_status_for(node, "error")
            app.logger.warning(f"run_replication error to {node}: {e}")

    state = read_cluster_state()
    return jsonify(state.get("replication_status", {}))

@app.route("/replication-status", methods=["GET"])
def replication_status():
    state = read_cluster_state()
    return jsonify(state.get("replication_status", {}))

@app.route("/simulate-failure", methods=["POST"])
def simulate_failure():
    state = read_cluster_state()
    current_primary = state.get("primary")
    # mark as error
    rs = state.get("replication_status", {})
    rs[current_primary] = "error"

    new_primary = None
    for n, status in rs.items():
        if n != current_primary and status == "synced":
            new_primary = n
            break
    if not new_primary:
        write_cluster_state(state)
        return jsonify({"message": "No backup available"}), 500

    state["primary"] = new_primary
    state["replication_status"] = rs
    write_cluster_state(state)
    return jsonify({"message": f"Node chính chuyển từ {current_primary} -> {new_primary}", "primary": new_primary})

@app.route("/restore-primary", methods=["POST"])
def restore_primary():
    body = request.json or {}
    restore_to = body.get("node", "node_A")
    state = read_cluster_state()
    state["primary"] = restore_to
    rs = state.get("replication_status", {})
    rs[restore_to] = "synced"
    state["replication_status"] = rs
    write_cluster_state(state)
    return jsonify({"message": f"Node chính đã được khôi phục thành {restore_to}"})


import atexit
def cleanup():
    try:
        conn.close()
    except Exception:
        pass
    try:
        db.close()
    except Exception:
        pass

atexit.register(cleanup)


if __name__ == "__main__":
    print(f"Starting node {NODE_NAME} on port {PORT} -> url {nodes_map[NODE_NAME]}")
    print("Cluster state file:", CLUSTER_STATE_FILE)
    _ = read_cluster_state()
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)
