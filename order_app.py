import sys
from app import app, ensure_db

# 強制標準輸出為 UTF-8 編碼，防止 Windows 終端機中文亂碼
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

if __name__ == "__main__":
    ensure_db()
    print("=" * 60)
    print("  📦 SQLite 企業訂單管理系統已啟動")
    print("  監聽連接埠：Port 5000")
    print("  網址：http://127.0.0.1:5000/")
    print("=" * 60)
    app.run(debug=True, host="127.0.0.1", port=5000)
