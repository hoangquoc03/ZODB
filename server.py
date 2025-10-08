from flask import Flask, request, jsonify
import ZODB, ZODB.FileStorage, transaction
from BTrees.OOBTree import OOBTree
from models import Person
from flask_cors import CORS  

app = Flask(__name__)
CORS(app) 

# Kết nối ZODB
storage = ZODB.FileStorage.FileStorage("mydata.fs")
db = ZODB.DB(storage)
connection = db.open()
root = connection.root()

# Khởi tạo OOBTree cho people và versions
if "people" not in root:
    root["people"] = OOBTree()
if "versions" not in root:
    root["versions"] = OOBTree()
if "redo_stack" not in root:
    root["redo_stack"] = OOBTree()  # Lưu redo version cho mỗi person

# ---- Helper functions ----
def save_version(pid, person, clear_redo=True):
    if pid not in root["versions"]:
        root["versions"][pid] = []
    root["versions"][pid].append({"name": person.name, "age": person.age})
    # Chỉ xóa redo khi có thao tác update thực sự
    if clear_redo:
        root["redo_stack"][pid] = []
    transaction.commit()

def push_redo(pid, version):
    if pid not in root["redo_stack"]:
        root["redo_stack"][pid] = []
    root["redo_stack"][pid].append(version)
    transaction.commit()

# ---- CRUD + Versioning ----
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

    # Lưu bản hiện tại vào history trước khi sửa
    if pid not in root["versions"]:
        root["versions"][pid] = []
    root["versions"][pid].append({"name": person.name, "age": person.age})

    # Khi có update mới thì reset redo_stack
    root["redo_stack"][pid] = []

    # Thực hiện thay đổi
    person.name = data.get("name", person.name)
    person.age = int(data.get("age", person.age))

    # Lưu bản mới vào history
    root["versions"][pid].append({"name": person.name, "age": person.age})
    transaction.commit()

    return jsonify({"status": "updated", "current_version": {"name": person.name, "age": person.age}})

@app.route("/people", methods=["GET"])
def get_people():
    people = []
    for key, person in root["people"].items():
        people.append({"id": key, "name": person.name, "age": person.age})
    return jsonify(people)

@app.route("/people/<pid>", methods=["GET"])
def get_person(pid):
    if pid not in root["people"]:
        return jsonify({"error": "Not found"}), 404
    p = root["people"][pid]
    return jsonify({"id": pid, "name": p.name, "age": p.age})

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

# ---- Replication Status Notification ----
@app.route("/replication-status", methods=["GET"])
def replication_status():
    return jsonify(root.get("last_replication", {
        "node_A": "synced",
        "node_B": "pending",
        "node_C": "error",
    }))

@app.route("/people/<pid>/undo", methods=["GET","POST"])
def undo_person(pid):
    if pid not in root["people"] or pid not in root["versions"]:
        return jsonify({"error": "Not found"}), 404

    versions = root["versions"][pid]
    if len(versions) < 2:
        return jsonify({"error": "No undo"}), 400

    # Lấy bản hiện tại đưa vào redo stack
    current_version = versions.pop()
    if pid not in root["redo_stack"]:
        root["redo_stack"][pid] = []
    root["redo_stack"][pid].append(current_version)

    # Quay lại bản trước đó
    last_version = versions[-1]
    person = root["people"][pid]
    person.name = last_version["name"]
    person.age = last_version["age"]

    transaction.commit()
    return jsonify({"status": "undo", "current_version": last_version ,"history": versions})


@app.route("/people/<pid>/redo", methods=["GET","POST"])
def redo_person(pid):
    if pid not in root["people"] or pid not in root["redo_stack"]:
        return jsonify({"error": "No redo"}), 404

    if len(root["redo_stack"][pid]) == 0:
        return jsonify({"error": "Redo stack empty"}), 400

    # Lấy lại bản từ redo stack
    version = root["redo_stack"][pid].pop()
    person = root["people"][pid]
    person.name = version["name"]
    person.age = version["age"]

    # Sau khi redo, push vào history (không reset redo stack)
    root["versions"][pid].append({"name": person.name, "age": person.age})

    transaction.commit()
    return jsonify({"status": "redo", "current_version": version,"history": root["versions"][pid]})

@app.route("/replicate", methods=["POST"])
def replicate():
    data = request.json
    target_nodes = data.get("nodes", ["node_A", "node_B", "node_C"])
    result = {}
    for node in target_nodes:
        # Giả lập trạng thái random: synced hoặc error
        import random
        status = random.choice(["synced", "pending", "error"])
        result[node] = status
    root["last_replication"] = result
    transaction.commit()
    return jsonify({"status": "replication started", "nodes": result}) 


@app.route("/people/<pid>/history", methods=["GET"])
def person_history(pid):
    if pid not in root["versions"]:
        return jsonify({"error": "No history"}), 404
    return jsonify(root["versions"][pid])



if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
