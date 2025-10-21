from ZEO import runzeo

if __name__ == "__main__":
    # Chạy ZEO server lắng nghe tại 8100, lưu DB trong file data.fs
    runzeo.main(["-a", "127.0.0.1:8100", "-f", "data.fs"])
