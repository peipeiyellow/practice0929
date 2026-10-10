import sys
from flask import Flask, render_template

# 強制標準輸出為 UTF-8 編碼，防止 Windows 終端機中文亂碼
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

app = Flask(__name__)


@app.after_request
def set_utf8_encoding(response):
    """確保 HTTP 回應標頭指定 UTF-8，防止瀏覽器中文亂碼"""
    content_type = response.headers.get("Content-Type", "")
    if "text/html" in content_type and "charset" not in content_type:
        response.headers["Content-Type"] = "text/html; charset=utf-8"
    return response


@app.route("/")
def hello_world():
    """Hello World 一頁式網頁 (Port 8899)"""
    return render_template("hello.html")


if __name__ == "__main__":
    print("=" * 60)
    print("  🌐 Hello World 一頁式網頁伺服器已啟動")
    print("  網址：http://127.0.0.1:8899/")
    print("=" * 60)
    app.run(debug=True, host="127.0.0.1", port=8899)
