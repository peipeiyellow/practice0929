from flask import Flask, render_template

app = Flask(__name__)

@app.route("/")
def hello_world():
    return render_template("index.html")

if __name__ == "__main__":
    # debug=True 可在開發階段啟用即時重載與除錯功能
    app.run(debug=True, host="127.0.0.1", port=5000)
