from flask import Flask, request, jsonify
import os, shutil, random
import ZODB, ZODB.FileStorage, transaction
from BTrees.OOBTree import OOBTree
from persistent import Persistent
from models import Person
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ============================
# --- Distributed Config ----
# ============================
DATA_DIR = "data"
NODES = ["node_A", "node_B", "node_C"]
PRIMARY_NODE = "node_A"
replication_status = {n: "synced" for n in NODES}

os.makedirs(DATA_DIR, exist_ok=True)

# ============================
# --- Helper: DB Management ---
# ============================
def get_db_path(node):
    return os.path.join(DATA_DIR, f"{node}.fs")

def open_db(node):
    path = get_db_path(node)
    storage = ZODB.FileStorage.FileStorage(path)
    db = ZODB.DB(storage)
    conn = db.open()
    root = conn.root()
    return db, conn, root

def ensure_node_init(node):
    path = get_db_path(node)
    if not os.path.exists(path):
        db, conn, root = open_db(node)
        root["people"] = OOBTree()
        root["versions"] = OOBTree()
        root["redo_stack"] = OOBTree()
        transaction.commit()
        conn.close()
        db.close()

for n in NODES:
    ensure_node_init(n)

# ============================
# --- Core DB (Primary Node) ---
# ============================
db, connection, root = open_db(PRIMARY_NODE)

if "people" not in root:
    root["people"] = OOBTree()
if "versions" not in root:
    root["versions"] = OOBTree()
if "redo_stack" not in root:
    root["redo_stack"] = OOBTree()

# ============================
# --- Helper functions ---
# ============================
def save_version(pid, person, clear_redo=True):
    if pid not in root["versions"]:
        root["versions"][pid] = []
    root["versions"][pid].append({"name": person.name, "age": person.age})
    if clear_redo:
        root["redo_stack"][pid] = []
    transaction.commit()

def push_redo(pid, version):
    if pid not in root["redo_stack"]:
        root["redo_stack"][pid] = []
    root["redo_stack"][pid].append(version)
    transaction.commit()

# ============================
# --- CRUD & Versioning ---
# ============================
@app.route("/people", methods=["POST"])
def add_person():
    data = request.json
    people = root["people"]
    new_key = f"p{len(people) + 1}"
    person = Person(data["name"], int(data["age"]))
    people[new_key] = person
    save_version(new_key, person)
    return jsonify({"status": "ok", "id": new_key})

@app.route("/people/<pid>", methods=["PUT"])
def update_person(pid):
    if pid not in root["people"]:
        return jsonify({"error": "Not found"}), 404
    data = request.json
    person = root["people"][pid]

    # Save current before update
    if pid not in root["versions"]:
        root["versions"][pid] = []
    root["versions"][pid].append({"name": person.name, "age": person.age})
    root["redo_stack"][pid] = []

    person.name = data.get("name", person.name)
    person.age = int(data.get("age", person.age))
    root["versions"][pid].append({"name": person.name, "age": person.age})
    transaction.commit()

    return jsonify({"status": "updated", "current_version": {"name": person.name, "age": person.age}})

@app.route("/people", methods=["GET"])
def get_people():
    people = []
    for key, person in root["people"].items():
        people.append({"id": key, "name": person.name, "age": person.age})
    return jsonify(people)

@app.route("/people/<pid>", methods=["DELETE"])
def delete_person(pid):
    if pid not in root["people"]:
        return jsonify({"error": "Not found"}), 404
    del root["people"][pid]
    if pid in root["versions"]:
        del root["versions"][pid]
    if pid in root["redo_stack"]:
        del root["redo_stack"][pid]
    transaction.commit()
    return jsonify({"status": "deleted"})

# ============================
# --- Undo / Redo ---
# ============================
@app.route("/people/<pid>/undo", methods=["POST"])
def undo_person(pid):
    if pid not in root["people"] or pid not in root["versions"]:
        return jsonify({"error": "Not found"}), 404

    versions = root["versions"][pid]
    if len(versions) < 2:
        return jsonify({"error": "No undo"}), 400

    current_version = versions.pop()
    root["redo_stack"][pid].append(current_version)

    last_version = versions[-1]
    person = root["people"][pid]
    person.name = last_version["name"]
    person.age = last_version["age"]
    transaction.commit()

    return jsonify({"status": "undo", "current_version": last_version, "history": versions})

@app.route("/people/<pid>/redo", methods=["POST"])
def redo_person(pid):
    if pid not in root["people"] or pid not in root["redo_stack"]:
        return jsonify({"error": "No redo"}), 404
    if len(root["redo_stack"][pid]) == 0:
        return jsonify({"error": "Redo stack empty"}), 400

    version = root["redo_stack"][pid].pop()
    person = root["people"][pid]
    person.name = version["name"]
    person.age = version["age"]
    root["versions"][pid].append({"name": person.name, "age": person.age})
    transaction.commit()

    return jsonify({"status": "redo", "current_version": version, "history": root["versions"][pid]})

@app.route("/people/<pid>/history", methods=["GET"])
def person_history(pid):
    if pid not in root["versions"]:
        return jsonify({"error": "No history"}), 404
    return jsonify(root["versions"][pid])

# ============================
# --- Replication Realistic ---
# ============================
@app.route("/run-replication", methods=["POST"])
def run_replication():
    global replication_status
    source = get_db_path(PRIMARY_NODE)
    for node in NODES:
        if node == PRIMARY_NODE:
            continue
        try:
            replication_status[node] = "pending"
            shutil.copy2(source, get_db_path(node))
            replication_status[node] = "synced"
        except Exception as e:
            replication_status[node] = "error"
            print(f"Error replicating to {node}: {e}")
    root["last_replication"] = replication_status
    transaction.commit()
    return jsonify(replication_status)

@app.route("/replication-status", methods=["GET"])
def replication_status_api():
    return jsonify(root.get("last_replication", replication_status))

# --- Simulate Failover ---
@app.route("/simulate-failure", methods=["POST"])
def simulate_failure():
    global PRIMARY_NODE
    replication_status[PRIMARY_NODE] = "error"
    for node in NODES:
        if node != PRIMARY_NODE and replication_status[node] == "synced":
            PRIMARY_NODE = node
            return jsonify({"message": f"Primary node switched to {PRIMARY_NODE}"})
    return jsonify({"message": "No backup available"}), 500

@app.route("/restore-primary", methods=["POST"])
def restore_primary():
    global PRIMARY_NODE
    PRIMARY_NODE = "node_A"
    replication_status["node_A"] = "synced"
    return jsonify({"message": "Primary restored to node_A"})

if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
