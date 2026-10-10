import datetime
import os
import sqlite3
from functools import wraps
from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash
from create_db import DB_PATH, get_connection, init_database

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "orders_system_secret_key_2026")


def ensure_db():
    """確保 orders.db 資料庫檔案存在，若不存在則自動初始化建立"""
    if not os.path.exists(DB_PATH):
        init_database(DB_PATH)


def login_required(f):
    """管理員權限驗證裝飾器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("login", next=request.url))
        return f(*args, **kwargs)
    return decorated_function


# ==========================================
# 首頁與公開檢視
# ==========================================
@app.route("/")
@app.route("/orders")
def index():
    """首頁總覽面板：呈現各資料表與彙整統計"""
    ensure_db()
    conn = get_connection()
    cursor = conn.cursor()

    # 1. 客戶資料
    cursor.execute("""
    SELECT customer_id, name, phone, address, created_date 
    FROM customer 
    ORDER BY customer_id;
    """)
    customers = [dict(r) for r in cursor.fetchall()]

    # 2. 商品資料
    cursor.execute("""
    SELECT product_id, name, price, stock, category 
    FROM product 
    ORDER BY product_id;
    """)
    products = [dict(r) for r in cursor.fetchall()]

    # 3. 訂單主表資料
    cursor.execute("""
    SELECT o.order_id, o.customer_id, c.name AS customer_name, o.order_date, o.status, o.salesperson
    FROM orders o
    JOIN customer c ON o.customer_id = c.customer_id
    ORDER BY o.order_id;
    """)
    orders = [dict(r) for r in cursor.fetchall()]

    # 4. 訂單明細資料 (複合主鍵)
    cursor.execute("""
    SELECT oi.order_id, oi.product_id, p.name AS product_name, oi.quantity, oi.unit_price, (oi.quantity * oi.unit_price) AS subtotal
    FROM order_item oi
    JOIN product p ON oi.product_id = p.product_id
    ORDER BY oi.order_id, oi.product_id;
    """)
    order_items = [dict(r) for r in cursor.fetchall()]

    # 5. 彙整報表 (訂單 + 明細彙整)
    cursor.execute("""
    SELECT 
        o.order_id,
        c.name AS customer_name,
        o.order_date,
        o.salesperson,
        o.status,
        COUNT(oi.product_id) AS item_count,
        COALESCE(SUM(oi.quantity), 0) AS total_quantity,
        COALESCE(SUM(oi.quantity * oi.unit_price), 0) AS total_amount
    FROM orders o
    JOIN customer c ON o.customer_id = c.customer_id
    LEFT JOIN order_item oi ON o.order_id = oi.order_id
    GROUP BY o.order_id
    ORDER BY o.order_id;
    """)
    order_summary = [dict(r) for r in cursor.fetchall()]

    total_revenue = sum(r["total_amount"] for r in order_summary) if order_summary else 0
    total_qty = sum(r["total_quantity"] for r in order_summary) if order_summary else 0

    conn.close()

    return render_template(
        "index.html",
        customers=customers,
        products=products,
        orders=orders,
        order_items=order_items,
        order_summary=order_summary,
        total_revenue=total_revenue,
        total_qty=total_qty,
        is_admin=bool(session.get("admin")),
    )


# ==========================================
# 需求 5: 管理員登入與登出 (admin / admin123)
# ==========================================
@app.route("/login", methods=["GET", "POST"])
def login():
    ensure_db()
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, password_hash FROM admin WHERE username = ?", (username,))
        admin_row = cursor.fetchone()
        conn.close()

        if admin_row and check_password_hash(admin_row["password_hash"], password):
            session["admin"] = admin_row["username"]
            next_url = request.args.get("next") or url_for("index")
            return redirect(next_url)
        else:
            error = "帳號或密碼錯誤，請重新輸入 (預設帳密: admin / admin123)"

    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.pop("admin", None)
    return redirect(url_for("index"))


# ==========================================
# 需求 9: 訂單專屬頁面 /order/<id> 與出貨單 QRCode
# ==========================================
@app.route("/order/<int:order_id>")
def order_detail(order_id):
    ensure_db()
    conn = get_connection()
    cursor = conn.cursor()

    # 查詢訂單與客戶資訊
    cursor.execute("""
    SELECT o.order_id, o.customer_id, c.name AS customer_name, c.phone AS customer_phone,
           c.address AS customer_address, o.order_date, o.status, o.salesperson
    FROM orders o
    JOIN customer c ON o.customer_id = c.customer_id
    WHERE o.order_id = ?;
    """, (order_id,))
    order = cursor.fetchone()

    if not order:
        conn.close()
        return "找不到此訂單 (Order Not Found)", 404

    # 查詢該訂單之各明細 (unit_price 為下單當時之歷史單價)
    cursor.execute("""
    SELECT oi.product_id, p.name AS product_name, p.category, oi.quantity, oi.unit_price,
           (oi.quantity * oi.unit_price) AS subtotal
    FROM order_item oi
    JOIN product p ON oi.product_id = p.product_id
    WHERE oi.order_id = ?
    ORDER BY oi.product_id;
    """, (order_id,))
    items = [dict(r) for r in cursor.fetchall()]

    total_amount = sum(item["subtotal"] for item in items)
    total_qty = sum(item["quantity"] for item in items)

    conn.close()

    return render_template(
        "order_detail.html",
        order=dict(order),
        items=items,
        total_amount=total_amount,
        total_qty=total_qty,
        is_admin=bool(session.get("admin")),
    )


# ==========================================
# 需求 6 & 7: 新增訂單 (客戶下拉、多商品勾選、保存下單時單價)
# ==========================================
@app.route("/admin/orders/new", methods=["GET", "POST"])
@login_required
def order_new():
    ensure_db()
    conn = get_connection()
    cursor = conn.cursor()

    if request.method == "POST":
        customer_id = request.form.get("customer_id")
        order_date = request.form.get("order_date") or datetime.date.today().isoformat()
        salesperson = request.form.get("salesperson", "").strip() or "陳冠宇"
        status = request.form.get("status", "處理中")
        product_ids = request.form.getlist("product_ids")

        if not customer_id or not product_ids:
            cursor.execute("SELECT customer_id, name, phone FROM customer ORDER BY customer_id;")
            customers = [dict(r) for r in cursor.fetchall()]
            cursor.execute("SELECT product_id, name, price, stock, category FROM product ORDER BY product_id;")
            products = [dict(r) for r in cursor.fetchall()]
            conn.close()
            return render_template(
                "order_new.html",
                customers=customers,
                products=products,
                today_date=order_date,
                error="請選擇客戶並至少勾選一項商品！",
            )

        try:
            # 1. 建立訂單主檔 orders
            cursor.execute("""
            INSERT INTO orders (customer_id, order_date, status, salesperson)
            VALUES (?, ?, ?, ?);
            """, (customer_id, order_date, status, salesperson))
            order_id = cursor.lastrowid

            # 2. 插入 order_item (需求 7: 保存下單當下的商品單價)
            for pid in product_ids:
                qty_str = request.form.get(f"quantity_{pid}", "1")
                quantity = int(qty_str) if qty_str.isdigit() and int(qty_str) > 0 else 1

                # 讀取當前商品價格作為歷史成交單價
                cursor.execute("SELECT price, stock FROM product WHERE product_id = ?", (pid,))
                prod = cursor.fetchone()
                if prod:
                    current_price = prod["price"]
                    cursor.execute("""
                    INSERT INTO order_item (order_id, product_id, quantity, unit_price)
                    VALUES (?, ?, ?, ?);
                    """, (order_id, pid, quantity, current_price))

            conn.commit()
            conn.close()
            # 成功建立後導向出貨單專屬頁面
            return redirect(url_for("order_detail", order_id=order_id))
        except Exception as e:
            conn.rollback()
            conn.close()
            return f"建立訂單失敗: {str(e)}", 400

    # GET 請求
    cursor.execute("SELECT customer_id, name, phone FROM customer ORDER BY customer_id;")
    customers = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT product_id, name, price, stock, category FROM product ORDER BY product_id;")
    products = [dict(r) for r in cursor.fetchall()]
    conn.close()

    today_date = datetime.date.today().isoformat()
    return render_template("order_new.html", customers=customers, products=products, today_date=today_date)


# ==========================================
# 需求 8: 訂單狀態更新 (處理中 / 已出貨 / 已完成 / 已取消)
# ==========================================
@app.route("/admin/orders/update_status/<int:order_id>", methods=["POST"])
@login_required
def order_update_status(order_id):
    ensure_db()
    new_status = request.form.get("status")
    allowed = ["處理中", "已出貨", "已完成", "已取消"]
    if new_status in allowed:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE orders SET status = ? WHERE order_id = ?", (new_status, order_id))
        conn.commit()
        conn.close()

    # 返回原來源頁面 (列表或出貨單)
    return redirect(request.referrer or url_for("index"))


@app.route("/admin/orders/delete/<int:order_id>", methods=["POST"])
@login_required
def order_delete(order_id):
    ensure_db()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM orders WHERE order_id = ?", (order_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("index"))


# ==========================================
# 需求 5: 客戶維護 (CRUD)
# ==========================================
@app.route("/admin/customer/add", methods=["POST"])
@login_required
def customer_add():
    ensure_db()
    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip()
    address = request.form.get("address", "").strip()
    created_date = datetime.date.today().isoformat()

    if name:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO customer (name, phone, address, created_date) VALUES (?, ?, ?, ?)",
            (name, phone, address, created_date),
        )
        conn.commit()
        conn.close()
    return redirect(url_for("index"))


@app.route("/admin/customer/edit/<int:customer_id>", methods=["POST"])
@login_required
def customer_edit(customer_id):
    ensure_db()
    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip()
    address = request.form.get("address", "").strip()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE customer SET name = ?, phone = ?, address = ? WHERE customer_id = ?",
        (name, phone, address, customer_id),
    )
    conn.commit()
    conn.close()
    return redirect(url_for("index"))


@app.route("/admin/customer/delete/<int:customer_id>", methods=["POST"])
@login_required
def customer_delete(customer_id):
    ensure_db()
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM customer WHERE customer_id = ?", (customer_id,))
        conn.commit()
    except sqlite3.IntegrityError:
        # 有關聯外鍵訂單時阻擋刪除
        pass
    conn.close()
    return redirect(url_for("index"))


# ==========================================
# 需求 5 & 7: 商品維護 (改價驗證不影響歷史訂單)
# ==========================================
@app.route("/admin/product/add", methods=["POST"])
@login_required
def product_add():
    ensure_db()
    name = request.form.get("name", "").strip()
    price = float(request.form.get("price", 0))
    stock = int(request.form.get("stock", 0))
    category = request.form.get("category", "一般商品").strip()

    if name and price >= 0 and stock >= 0:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO product (name, price, stock, category) VALUES (?, ?, ?, ?)",
            (name, price, stock, category),
        )
        conn.commit()
        conn.close()
    return redirect(url_for("index"))


@app.route("/admin/product/edit/<int:product_id>", methods=["POST"])
@login_required
def product_edit(product_id):
    """
    修改商品資料 (包含改價)：
    注意：修改此處商品價格只會更新 product 表，
    不會更改 order_item 中的 unit_price (下單當時歷史單價)！
    """
    ensure_db()
    name = request.form.get("name", "").strip()
    price = float(request.form.get("price", 0))
    stock = int(request.form.get("stock", 0))
    category = request.form.get("category", "").strip()

    if name and price >= 0 and stock >= 0:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE product SET name = ?, price = ?, stock = ?, category = ? WHERE product_id = ?",
            (name, price, stock, category, product_id),
        )
        conn.commit()
        conn.close()
    return redirect(url_for("index"))


@app.route("/admin/product/delete/<int:product_id>", methods=["POST"])
@login_required
def product_delete(product_id):
    ensure_db()
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM product WHERE product_id = ?", (product_id,))
        conn.commit()
    except sqlite3.IntegrityError:
        # 有關聯明細時阻擋刪除
        pass
    conn.close()
    return redirect(url_for("index"))


# ==========================================
# API 檢查介面
# ==========================================
@app.route("/api/check")
def api_check():
    """提供 JSON API 供遠端自動化測試與檢驗"""
    ensure_db()
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT customer_id, name, phone, address, created_date FROM customer ORDER BY customer_id;")
    customers = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT product_id, name, price, stock, category FROM product ORDER BY product_id;")
    products = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT order_id, customer_id, order_date, status, salesperson FROM orders ORDER BY order_id;")
    orders = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT order_id, product_id, quantity, unit_price FROM order_item ORDER BY order_id, product_id;")
    order_items = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT id, username FROM admin ORDER BY id;")
    admins = [dict(r) for r in cursor.fetchall()]

    conn.close()

    return jsonify({
        "status": "success",
        "database": "orders.db",
        "counts": {
            "admins": len(admins),
            "customers": len(customers),
            "products": len(products),
            "orders": len(orders),
            "order_items": len(order_items),
        },
        "data": {
            "customers": customers,
            "products": products,
            "orders": orders,
            "order_items": order_items,
        },
    })


if __name__ == "__main__":
    ensure_db()
    app.run(debug=True, host="127.0.0.1", port=5000)
