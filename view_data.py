import ZODB, ZODB.FileStorage
from models import Person 


storage = ZODB.FileStorage.FileStorage("mydata.fs")
db = ZODB.DB(storage)
connection = db.open()
root = connection.root()

print("Các key trong root:", list(root.keys()))

if "people" in root:
    for key, person in root["people"].items():
        print(f"{key}: {person.name}, {person.age}")

connection.close()
db.close()
