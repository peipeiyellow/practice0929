import os
import sqlite3
import unicodedata

DB_PATH = os.path.join(os.path.dirname(__file__), "orders.db")


def get_str_width(text):
    """計算包含全形/中文字元的字串顯示寬度"""
    width = 0
    for ch in str(text):
        if unicodedata.east_asian_width(ch) in ("F", "W"):
            width += 2
        else:
            width += 1
    return width


def pad_str(text, width, align="left"):
    """根據字串顯示寬度補齊空白"""
    s = str(text)
    curr_w = get_str_width(s)
    diff = max(0, width - curr_w)
    if align == "right":
        return " " * diff + s
    elif align == "center":
        left = diff // 2
        right = diff - left
        return " " * left + s + " " * right
    else:
        return s + " " * diff


def print_table(title, headers, rows, alignments=None):
    """印出排版整齊的 ASCII 表格"""
    print(f"\n{'=' * 6} 【{title}】 (共 {len(rows)} 筆) {'=' * 6}")
    if not rows:
        print("(無資料)")
        return

    num_cols = len(headers)
    if alignments is None:
        alignments = ["left"] * num_cols

    # 計算每欄最小所需寬度
    col_widths = [get_str_width(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            w = get_str_width(val)
            if w > col_widths[i]:
                col_widths[i] = w

    # 加上內距 (padding)
    col_widths = [w + 2 for w in col_widths]

    # 分隔線
    top_sep = "+" + "+".join("-" * w for w in col_widths) + "+"
    print(top_sep)

    # 標題列
    header_line = "|" + "|".join(
        pad_str(f" {headers[i]} ", col_widths[i], "center")
        for i in range(num_cols)
    ) + "|"
    print(header_line)

    mid_sep = "+" + "+".join("=" * w for w in col_widths) + "+"
    print(mid_sep)

    # 資料列
    for row in rows:
        row_line = "|" + "|".join(
            pad_str(f" {row[i]} ", col_widths[i], alignments[i])
            for i in range(num_cols)
        ) + "|"
        print(row_line)

    bottom_sep = "+" + "+".join("-" * w for w in col_widths) + "+"
    print(bottom_sep)


def check_database(db_path=DB_PATH):
    """查詢並列印 orders.db 各資料表內容"""
    if not os.path.exists(db_path):
        print(f"[錯誤] 資料庫檔案不存在: {db_path}，請先執行 create_db.py 建立資料庫。")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("\n" + "#" * 60)
    print(f"       SQLite 資料庫內容驗證工具: {os.path.basename(db_path)}")
    print("#" * 60)

    # 0. 驗證 admin 表
    cursor.execute("SELECT id, username, password_hash FROM admin ORDER BY id;")
    admin_rows = [
        [r["id"], r["username"], r["password_hash"][:20] + "... (已安全雜湊)"]
        for r in cursor.fetchall()
    ]
    print_table(
        "0. 管理員資料表 (admin)",
        ["編號 (PK)", "使用者帳號", "密碼雜湊值 (PBKDF2-SHA256)"],
        admin_rows,
        alignments=["center", "center", "left"],
    )

    # 1. 驗證 customer 表
    cursor.execute("""
    SELECT customer_id, name, phone, address, created_date 
    FROM customer 
    ORDER BY customer_id;
    """)
    cust_rows = [
        [r["customer_id"], r["name"], r["phone"], r["address"], r["created_date"]]
        for r in cursor.fetchall()
    ]
    print_table(
        "1. 客戶資料表 (customer)",
        ["客戶編號 (PK)", "名稱", "電話", "地址", "建檔日期"],
        cust_rows,
        alignments=["center", "left", "left", "left", "center"],
    )

    # 2. 驗證 product 表
    cursor.execute("""
    SELECT product_id, name, price, stock, category 
    FROM product 
    ORDER BY product_id;
    """)
    prod_rows = [
        [r["product_id"], r["name"], f"${r['price']:,.0f}", r["stock"], r["category"]]
        for r in cursor.fetchall()
    ]
    print_table(
        "2. 商品資料表 (product)",
        ["商品編號 (PK)", "名稱", "單價", "庫存", "分類"],
        prod_rows,
        alignments=["center", "left", "right", "right", "center"],
    )

    # 3. 驗證 orders 表
    cursor.execute("""
    SELECT o.order_id, o.customer_id, c.name AS cust_name, o.order_date, o.status, o.salesperson
    FROM orders o
    JOIN customer c ON o.customer_id = c.customer_id
    ORDER BY o.order_id;
    """)
    order_rows = [
        [r["order_id"], f"{r['customer_id']} ({r['cust_name']})", r["order_date"], r["status"], r["salesperson"]]
        for r in cursor.fetchall()
    ]
    print_table(
        "3. 訂單資料表 (orders)",
        ["訂單編號 (PK)", "客戶 (FK)", "訂單日期", "狀態", "業務人員"],
        order_rows,
        alignments=["center", "left", "center", "center", "center"],
    )

    # 4. 驗證 order_item 表 (複合主鍵: order_id + product_id)
    cursor.execute("""
    SELECT oi.order_id, oi.product_id, p.name AS prod_name, oi.quantity, oi.unit_price, (oi.quantity * oi.unit_price) AS subtotal
    FROM order_item oi
    JOIN product p ON oi.product_id = p.product_id
    ORDER BY oi.order_id, oi.product_id;
    """)
    item_rows = [
        [
            r["order_id"],
            r["product_id"],
            r["prod_name"],
            r["quantity"],
            f"${r['unit_price']:,.0f}",
            f"${r['subtotal']:,.0f}",
        ]
        for r in cursor.fetchall()
    ]
    print_table(
        "4. 訂單明細資料表 (order_item) - 複合主鍵: [訂單編號, 商品編號]",
        ["訂單編號 (FK)", "商品編號 (FK)", "商品名稱", "數量", "歷史單價", "小計金額"],
        item_rows,
        alignments=["center", "center", "left", "right", "right", "right"],
    )

    # 5. 彙整關聯報表 (多項商品案例展示與訂單總額)
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
    summary_rows = [
        [
            r["order_id"],
            r["customer_name"],
            r["order_date"],
            r["salesperson"],
            r["status"],
            f"{r['item_count']} 項",
            r["total_quantity"],
            f"${r['total_amount']:,.0f}",
        ]
        for r in cursor.fetchall()
    ]
    print_table(
        "★ 訂單與明細彙整驗證 (含多項商品案例與訂單總計)",
        ["訂單編號", "客戶名稱", "下單日期", "業務員", "狀態", "商品品項數", "總件數", "訂單總額"],
        summary_rows,
        alignments=["center", "left", "center", "center", "center", "center", "right", "right"],
    )

    conn.close()
    print("\n[OK] 所有資料表內容讀取與驗證完成！\n")


if __name__ == "__main__":
    check_database()
