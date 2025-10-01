import ZODB, ZODB.FileStorage, transaction, persistent

# Tạo file database ZODB
storage = ZODB.FileStorage.FileStorage("mydata.fs")
db = ZODB.DB(storage)
connection = db.open()
root = connection.root()

# Tạo một object persistent
class Person(persistent.Persistent):
    def __init__(self, name, age):
        self.name = name
        self.age = age

# Lưu vào ZODB
root["person"] = Person("Alice", 25)
transaction.commit()  # lưu thay đổi

print("Saved:", root["person"].name, root["person"].age)

# Đóng kết nối
connection.close()
db.close()
