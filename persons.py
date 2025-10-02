import ZODB, ZODB.FileStorage, transaction, persistent
from BTrees.OOBTree import OOBTree

class Person(persistent.Persistent):
    def __init__(self, name, age):
        self.name = name
        self.age = age

# Tạo file lưu trữ
storage = ZODB.FileStorage.FileStorage("mydata.fs")
db = ZODB.DB(storage)
connection = db.open()
root = connection.root()

# Nếu chưa có BTree thì tạo mới (đè cái list cũ đi)
if not isinstance(root.get("people"), OOBTree):
    root["people"] = OOBTree()

# Thêm dữ liệu vào BTree
root["people"]["p1"] = Person("Alice", 25)
root["people"]["p2"] = Person("Bob", 30)
root["people"]["p3"] = Person("Charlie", 22)

transaction.commit()
print("Đã lưu nhiều đối tượng vào BTree")

# Đọc lại dữ liệu
for key, person in root["people"].items():
    print(f"{key}: {person.name}, {person.age}")

connection.close()
db.close()
