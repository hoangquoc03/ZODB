import os


files = ["mydata.fs", "mydata.fs.index", "mydata.fs.lock", "mydata.fs.tmp"]

for f in files:
    if os.path.exists(f):
        os.remove(f)
        print(f"Đã xóa {f}")
    else:
        print(f"Không tìm thấy {f}")

print("Database đã được reset.")
