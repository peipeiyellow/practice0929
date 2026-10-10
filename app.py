import os
import sqlite3
from flask import Flask, render_template, jsonify
from create_db import DB_PATH, get_connection, init_database

app = Flask(__name__)


def ensure_db():
    """確保 orders.db 資料庫檔案存在，若不存在則自動初始化建立"""
    if not os.path.exists(DB_PATH):
        init_database(DB_PATH)


@app.route("/")
@app.route("/orders")
def index():
    """首頁 / 訂單展示頁面"""
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

    # 3. 訂單資料
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
        SUM(oi.quantity) AS total_quantity,
        SUM(oi.quantity * oi.unit_price) AS total_amount
    FROM orders o
    JOIN customer c ON o.customer_id = c.customer_id
    JOIN order_item oi ON o.order_id = oi.order_id
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
    )


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

    conn.close()

    return jsonify({
        "status": "success",
        "database": "orders.db",
        "counts": {
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
