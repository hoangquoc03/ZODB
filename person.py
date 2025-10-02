import ZODB, ZODB.FileStorage, transaction, persistent

from models import Person 

# Tạo file database ZODB
storage = ZODB.FileStorage.FileStorage("mydata.fs")
db = ZODB.DB(storage)
connection = db.open()
root = connection.root()

# Lưu vào ZODB
root["person"] = Person("hquoc", 120)
transaction.commit()  # lưu thay đổi

print("Saved:", root["person"].name, root["person"].age)

# Đóng kết nối
connection.close()
db.close()
 