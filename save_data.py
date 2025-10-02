import ZODB, ZODB.FileStorage, transaction
from BTrees.OOBTree import OOBTree
from models import Person


storage = ZODB.FileStorage.FileStorage("mydata.fs")
db = ZODB.DB(storage)
connection = db.open()
root = connection.root()


if "people" not in root:
    root["people"] = OOBTree()


root["people"]["p1"] = Person("Alice", 25)
root["people"]["p2"] = Person("Bob", 30)
root["people"]["p3"] = Person("Charlie", 22)

transaction.commit()
print("Đã lưu nhiều đối tượng vào BTree")

connection.close()
db.close()
