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

if "people" not in root:
    root["people"] = OOBTree()

@app.route("/people", methods=["GET"])
def get_people():
    """Lấy toàn bộ danh sách"""
    people = []
    for key, person in root["people"].items():
        people.append({"id": key, "name": person.name, "age": person.age})
    return jsonify(people)

@app.route("/people/<pid>", methods=["GET"])
def get_person(pid):
    """Xem chi tiết 1 person"""
    if pid not in root["people"]:
        return jsonify({"error": "Not found"}), 404
    p = root["people"][pid]
    return jsonify({"id": pid, "name": p.name, "age": p.age})

@app.route("/people", methods=["POST"])
def add_person():
    """Thêm mới"""
    data = request.json
    people = root["people"]
    new_key = f"p{len(people) + 1}"
    people[new_key] = Person(data["name"], int(data["age"]))
    transaction.commit()
    return jsonify({"status": "ok", "id": new_key})

@app.route("/people/<pid>", methods=["PUT"])
def update_person(pid):
    """Sửa person"""
    if pid not in root["people"]:
        return jsonify({"error": "Not found"}), 404
    data = request.json
    person = root["people"][pid]
    person.name = data.get("name", person.name)
    person.age = int(data.get("age", person.age))
    transaction.commit()
    return jsonify({"status": "updated"})

@app.route("/people/<pid>", methods=["DELETE"])
def delete_person(pid):
    """Xóa person"""
    if pid not in root["people"]:
        return jsonify({"error": "Not found"}), 404
    del root["people"][pid]
    transaction.commit()
    return jsonify({"status": "deleted"})

if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
