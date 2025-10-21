
import argparse
import json
import os
import threading
import time
from typing import Dict, List

import requests
from flask import Flask, jsonify, request
from flask_cors import CORS

import ZODB, ZODB.FileStorage, transaction
from BTrees.OOBTree import OOBTree

# -------------------------
# Config
# -------------------------
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
CLUSTER_STATE_FILE = os.path.join(DATA_DIR, "cluster_state.json")

# Default cluster mapping (edit if running across hosts)
DEFAULT_NODES = {
    "node_A": "http://127.0.0.1:5000",
    "node_B": "http://127.0.0.1:5001",
    "node_C": "http://127.0.0.1:5002",
}

# -------------------------
# Helpers: cluster state file
# -------------------------
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

# -------------------------
# Flask app + argparse
# -------------------------
parser = argparse.ArgumentParser()
parser.add_argument("--name", type=str, default="node_A", help="node name (node_A/node_B/node_C)")
parser.add_argument("--port", type=int, default=5000, help="port to run the flask app")
parser.add_argument("--nodes-file", type=str, default=None, help="optional json mapping file for nodes")
args = parser.parse_args()

NODE_NAME = args.name
PORT = args.port

# If user provided nodes-file, override DEFAULT_NODES
if args.nodes_file:
    with open(args.nodes_file, "r", encoding="utf-8") as f:
        nodes_map = json.load(f)
else:
    nodes_map = DEFAULT_NODES

# ensure NODE_NAME exists in nodes_map
if NODE_NAME not in nodes_map:
    raise SystemExit(f"NODE_NAME {NODE_NAME} not in nodes_map keys: {list(nodes_map.keys())}")

app = Flask(__name__)
CORS(app)

# -------------------------
# ZODB helpers: per-node .fs
# -------------------------
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

# initialize DB files for all nodes to make sure they exist
for n in nodes_map.keys():
    init_node_db_if_missing(n)

# each running process will open its own DB connection to its file
db, conn, root = open_db(NODE_NAME)

# ensure collections present
if "people" not in root:
    root["people"] = OOBTree()
if "versions" not in root:
    root["versions"] = OOBTree()
if "redo_stack" not in root:
    root["redo_stack"] = OOBTree()
transaction.commit()

# -------------------------
# Utility functions
# -------------------------
def get_local_people_list():
    """Read people from this node's ZODB root and return list of plain dicts."""
    out = []
    for k, p in root["people"].items():
        # person might be persistent object or dict
        if hasattr(p, "name") and hasattr(p, "age"):
            out.append({"id": k, "name": p.name, "age": p.age})
        elif isinstance(p, dict):
            out.append(p)
        else:
            # fallback: try repr
            out.append({"id": k, "repr": str(p)})
    return out

def replace_local_people_from_list(list_people: List[Dict]):
    """Replace this node's people with list_people (list of dicts with id,name,age)."""
    # clear and rewrite
    ppl = OOBTree()
    for p in list_people:
        pid = p.get("id")
        # store as plain dict to avoid dependency on models.Person across nodes
        ppl[pid] = {"id": pid, "name": p.get("name"), "age": int(p.get("age", 0))}
    root["people"] = ppl
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

# -------------------------
# Endpoints: Admin / debug
# -------------------------
@app.route("/whoami", methods=["GET"])
def whoami():
    state = read_cluster_state()
    return jsonify({
        "node": NODE_NAME,
        "url": nodes_map[NODE_NAME],
        "primary": state.get("primary"),
        "replication_status": state.get("replication_status", {})
    })

# -------------------------
# CRUD Endpoints
# - If this node is primary, writes will optionally trigger replication (background)
# - Reads return local data
# -------------------------
AUTO_REPLICATE_AFTER_WRITE = True  # set True to auto push after writes

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
    """Read from local node (replica read allowed)."""
    data = get_local_people_list()
    return jsonify({"source": NODE_NAME, "data": data})

@app.route("/people", methods=["POST"])
def add_person():
    """Add person to local DB. If this node is primary -> trigger replication to others."""
    payload = request.json or {}
    name = payload.get("name")
    age = int(payload.get("age", 0))
    # generate new key locally
    people = root["people"]
    new_key = f"p{len(people) + 1}"
    # store as simple dict to avoid pickling issues across different code versions
    people[new_key] = {"id": new_key, "name": name, "age": age}
    transaction.commit()

    # auto replicate if this node is primary
    if is_primary() and AUTO_REPLICATE_AFTER_WRITE:
        # prepare payload and background thread
        payload_list = get_local_people_list()
        threading.Thread(target=background_replicate, args=(payload_list,), daemon=True).start()

    return jsonify({"status": "ok", "id": new_key, "written_to": NODE_NAME})

@app.route("/people/<pid>", methods=["PUT"])
def update_person(pid):
    if pid not in root["people"]:
        return jsonify({"error": "Not found"}), 404
    data_json = request.json or {}
    p = root["people"][pid]
    # p may be dict or object-like
    if isinstance(p, dict):
        p["name"] = data_json.get("name", p.get("name"))
        p["age"] = int(data_json.get("age", p.get("age", 0)))
        root["people"][pid] = p
    else:
        # if persistent object with attributes
        setattr(p, "name", data_json.get("name", getattr(p, "name", "")))
        setattr(p, "age", int(data_json.get("age", getattr(p, "age", 0))))
    transaction.commit()

    if is_primary() and AUTO_REPLICATE_AFTER_WRITE:
        threading.Thread(target=background_replicate, args=(get_local_people_list(),), daemon=True).start()

    return jsonify({"status": "updated", "id": pid})

@app.route("/people/<pid>", methods=["DELETE"])
def delete_person(pid):
    if pid not in root["people"]:
        return jsonify({"error": "Not found"}), 404
    del root["people"][pid]
    transaction.commit()
    if is_primary() and AUTO_REPLICATE_AFTER_WRITE:
        threading.Thread(target=background_replicate, args=(get_local_people_list(),), daemon=True).start()
    return jsonify({"status": "deleted", "id": pid})

# -------------------------
# Endpoint for receiving replication payload
# Node receives list of people dicts and replaces local DB (simple approach)
# -------------------------
@app.route("/sync-data", methods=["POST"])
def sync_data():
    data = request.json or []
    # Replace local people with payload
    replace_local_people_from_list(data)
    # optionally reset replication status for this node to synced
    update_replication_status_for(NODE_NAME, "synced")
    return jsonify({"status": "synced", "node": NODE_NAME, "count": len(data)})

# -------------------------
# Manual replication endpoint: trigger from whoever wants to replicate (only primary allowed)
# -------------------------
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

# -------------------------
# Failover simulation endpoints
# - simulate-failure: mark current primary as 'error' and elect a backup (first synced)
# - restore-primary: set primary back to node_A (or to requested name)
# These update cluster_state file so all nodes see the new primary.
# -------------------------
@app.route("/simulate-failure", methods=["POST"])
def simulate_failure():
    state = read_cluster_state()
    current_primary = state.get("primary")
    # mark as error
    rs = state.get("replication_status", {})
    rs[current_primary] = "error"
    # choose a new primary: first node with status 'synced' (excluding failed)
    new_primary = None
    for n, status in rs.items():
        if n != current_primary and status == "synced":
            new_primary = n
            break
    if not new_primary:
        # no available backup
        write_cluster_state(state)
        return jsonify({"message": "No backup available"}), 500

    state["primary"] = new_primary
    state["replication_status"] = rs
    write_cluster_state(state)
    return jsonify({"message": f"Primary switched from {current_primary} -> {new_primary}", "primary": new_primary})

@app.route("/restore-primary", methods=["POST"])
def restore_primary():
    # restore primary to node_A by default or to query param name
    body = request.json or {}
    restore_to = body.get("node", "node_A")
    state = read_cluster_state()
    state["primary"] = restore_to
    # mark restored node as synced
    rs = state.get("replication_status", {})
    rs[restore_to] = "synced"
    state["replication_status"] = rs
    write_cluster_state(state)
    return jsonify({"message": f"Primary restored to {restore_to}"})

# -------------------------
# Clean shutdown handlers (close DB)
# -------------------------
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

# -------------------------
# Run server
# -------------------------
if __name__ == "__main__":
    print(f"Starting node {NODE_NAME} on port {PORT} -> url {nodes_map[NODE_NAME]}")
    print("Cluster state file:", CLUSTER_STATE_FILE)
    _ = read_cluster_state()
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)

