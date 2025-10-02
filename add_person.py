import ZODB, ZODB.FileStorage,transaction
from BTrees.OOBTree import OOBTree
from models import Person

storage = ZODB.FileStorage.FileStorage("mydata.fs")
db = ZODB.DB(storage)
connection = db.open()
root = connection.root()
if "people" not in root:
    root["people"] = OOBTree()
people = root["people"]
new_key = f"p{len(people) +1}"

name = input("Nhập tên:")
age = int(input("Nhập tuổi:"))
people[new_key] = Person(name,age)
transaction.commit()

print(f"Đã thêm {name},{age} vào people với key {new_key}")

connection.close()
db.close()