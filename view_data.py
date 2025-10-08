import ZODB, ZODB.FileStorage
from models import Person 

# Khởi tạo nơi lưu trữ (FileStorage)
storage = ZODB.FileStorage.FileStorage("mydata.fs")
# Tạo cơ sở dữ liệu
db = ZODB.DB(storage)
# Mở kết nối
connection = db.open()
root = connection.root()

print("Các key trong root:", list(root.keys()))

if "people" in root:
    for key, person in root["people"].items():
        print(f"{key}: {person.name}, {person.age}")
if "person" in root:
    p = root["person"]
    print(f"person: {p.name}, {p.age}")

connection.close()
db.close()
