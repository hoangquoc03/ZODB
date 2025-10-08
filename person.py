import ZODB, ZODB.FileStorage, transaction, persistent

from models import Person 

# Khởi tạo nơi lưu trữ
storage = ZODB.FileStorage.FileStorage("mydata.fs")
# Tạo cơ sở dữ liệu
db = ZODB.DB(storage)
# Mở kết nối và truy cập root
connection = db.open()
root = connection.root()

# Lưu vào ZODB
root["person"] = Person("hquoc", 120)
transaction.commit()  # lưu thay đổi

print("Saved:", root["person"].name, root["person"].age)

# Đóng kết nối
connection.close()
db.close()
 