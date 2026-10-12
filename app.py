import datetime
import os
import re
import sqlite3
from functools import wraps
from flask import (
    Flask,
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

# 確保 JSON API 輸出繁體中文而不轉譯為 \uXXXX 編碼
app.config["JSON_AS_ASCII"] = False
if hasattr(app, "json") and hasattr(app.json, "ensure_ascii"):
    app.json.ensure_ascii = False


@app.template_filter("comma")
def comma_filter(val):
    """金額與數值千分位格式化"""
    try:
        if val is None:
            return "0"
        return f"{float(val):,.0f}"
    except (ValueError, TypeError):
        return val


@app.template_filter("currency")
def currency_filter(val):
    """金額加上 NT$ 與千分位格式化"""
    try:
        if val is None:
            return "NT$ 0"
        return f"NT$ {float(val):,.0f}"
    except (ValueError, TypeError):
        return val



@app.after_request
def set_utf8_encoding(response):
    """確保所有 HTTP 回應標頭均明確指定 UTF-8，防止瀏覽器產生中文亂碼"""
    content_type = response.headers.get("Content-Type", "")
    if "text/html" in content_type and "charset" not in content_type:
        response.headers["Content-Type"] = "text/html; charset=utf-8"
    elif "application/json" in content_type and "charset" not in content_type:
        response.headers["Content-Type"] = "application/json; charset=utf-8"
    return response


def ensure_db():
    """確保 orders.db 資料庫檔案存在，若不存在則自動初始化建立"""
    if not os.path.exists(DB_PATH):
        init_database(DB_PATH)


# ==========================================
# 需求 2: 後台所有頁面需登入 (session) 且角色為管理員 (admin) 才能進入
# 採用全域請求攔截器 (before_request) + 專屬裝飾器 (admin_required) 雙層嚴格防護
# ==========================================
@app.before_request
def enforce_admin_authentication():
    """
    全域後台權限管制：
    任何未登入或角色非 admin 的請求，完全無法接觸後台任何頁面與資料，
    一律強制 302 重導向至 /login 登入頁面（API 則回傳 401 Unauthorized）。
    """
    # 僅允許登入頁、登出功能與靜態資源公開存取
    whitelist_endpoints = {"login", "logout", "static"}
    if request.endpoint in whitelist_endpoints or (request.path and request.path.startswith("/static")):
        return None

    # 嚴格檢查 Session：必須存在管理員帳號且角色必須為 'admin'
    is_logged_in = bool(session.get("admin"))
    is_admin_role = (session.get("role") == "admin")

    if not (is_logged_in and is_admin_role):
        # 若為 API 請求，回傳 401
        if request.path.startswith("/api/"):
            return jsonify({
                "status": "error",
                "message": "未授權：後台所有介面均需登入 (session) 且角色為管理員才能存取",
            }), 401
        # 網頁請求一律強制重導向至登入頁
        return redirect(url_for("login", next=request.url))


def admin_required(f):
    """個別路由裝飾器雙層保護"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("admin") or session.get("role") != "admin":
            return redirect(url_for("login", next=request.url))
        return f(*args, **kwargs)
    return decorated_function


# ==========================================
# 首頁總覽 (後台核心儀表板，需登入且角色為 admin)
# ==========================================
@app.route("/")
@app.route("/orders")
@admin_required
def index():
    """總覽儀表板面板：呈現各資料表與彙整統計 (全參數化查詢)"""
    ensure_db()
    conn = get_connection()
    cursor = conn.cursor()

    # 1. 客戶資料 (參數化)
    cursor.execute("""
    SELECT customer_id, name, phone, address, created_date 
    FROM customer 
    ORDER BY customer_id;
    """)
    customers = [dict(r) for r in cursor.fetchall()]

    # 2. 商品資料 (參數化)
    cursor.execute("""
    SELECT product_id, name, price, stock, category 
    FROM product 
    ORDER BY product_id;
    """)
    products = [dict(r) for r in cursor.fetchall()]

    # 3. 訂單主表資料 (參數化)
    cursor.execute("""
    SELECT o.order_id, o.order_code, o.customer_id, c.name AS customer_name, o.order_date, o.status, o.salesperson
    FROM orders o
    JOIN customer c ON o.customer_id = c.customer_id
    ORDER BY o.order_id;
    """)
    orders = [dict(r) for r in cursor.fetchall()]

    # 4. 訂單明細資料 (參數化)
    cursor.execute("""
    SELECT oi.order_id, o.order_code, oi.product_id, p.name AS product_name, oi.quantity, oi.unit_price, (oi.quantity * oi.unit_price) AS subtotal
    FROM order_item oi
    JOIN orders o ON oi.order_id = o.order_id
    JOIN product p ON oi.product_id = p.product_id
    ORDER BY oi.order_id, oi.product_id;
    """)
    order_items = [dict(r) for r in cursor.fetchall()]

    # 5. 彙整報表 (參數化)
    cursor.execute("""
    SELECT 
        o.order_id,
        o.order_code,
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
        is_admin=True,
    )


# ==========================================
# 需求：後台營運儀表板 (/admin 與 /admin/dashboard)
# 1. 上方四張 KPI 卡：累計營收、有效訂單數、平均客單價、客戶數 (排除已取消訂單)
# 2. 每月營收趨勢：Chart.js 折線圖 (排除已取消訂單)
# 3. 訂單狀態分布：Chart.js 環圈圖
# 4. 熱銷商品 Top 5：商品名稱、售出數量、營收 (排除已取消訂單)
# 5. 客戶消費排行 Top 5：客戶名稱、訂單數、消費金額 (排除已取消訂單)
# 6. 金額千分位、Bootstrap 卡片排版、手機端單欄響應式顯示
# ==========================================
@app.route("/admin")
@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    """營運儀表板：多維度營運指標與圖表分析 (全參數化查詢，嚴格排除 '已取消' 之訂單)"""
    ensure_db()
    conn = get_connection()
    cursor = conn.cursor()

    # ----------------------------------------------------
    # 1. 上方四張 KPI 卡片 (狀態為 '已取消' 之訂單不列入計算)
    # ----------------------------------------------------
    cursor.execute("""
    SELECT 
        COUNT(DISTINCT o.order_id) AS valid_orders_count,
        COALESCE(SUM(oi.quantity * oi.unit_price), 0) AS total_revenue,
        COUNT(DISTINCT o.customer_id) AS valid_customers_count
    FROM orders o
    JOIN order_item oi ON o.order_id = oi.order_id
    WHERE o.status != '已取消';
    """)
    kpi_row = dict(cursor.fetchone())
    total_revenue = float(kpi_row["total_revenue"])
    valid_orders_count = int(kpi_row["valid_orders_count"])
    valid_customers_count = int(kpi_row["valid_customers_count"])
    avg_order_value = (total_revenue / valid_orders_count) if valid_orders_count > 0 else 0.0

    # 查詢建檔客戶總數
    cursor.execute("SELECT COUNT(*) AS total_customers FROM customer;")
    total_customers = cursor.fetchone()["total_customers"]

    # 查詢訂單總筆數與已取消筆數 (供統計對比提示)
    cursor.execute("SELECT COUNT(*) AS total_orders FROM orders;")
    total_orders_count = cursor.fetchone()["total_orders"]
    cursor.execute("SELECT COUNT(*) AS cancelled_count FROM orders WHERE status = '已取消';")
    cancelled_orders_count = cursor.fetchone()["cancelled_count"]

    kpi = {
        "total_revenue": total_revenue,
        "valid_orders_count": valid_orders_count,
        "avg_order_value": avg_order_value,
        "valid_customers_count": valid_customers_count,
        "total_customers": total_customers,
    }

    # ----------------------------------------------------
    # 2. 每月營收趨勢：折線圖 (Chart.js，排除 '已取消' 之訂單)
    # ----------------------------------------------------
    cursor.execute("""
    SELECT 
        substr(o.order_date, 1, 7) AS month,
        COALESCE(SUM(oi.quantity * oi.unit_price), 0) AS revenue,
        COUNT(DISTINCT o.order_id) AS order_count
    FROM orders o
    JOIN order_item oi ON o.order_id = oi.order_id
    WHERE o.status != '已取消'
    GROUP BY substr(o.order_date, 1, 7)
    ORDER BY month ASC;
    """)
    monthly_rows = [dict(r) for r in cursor.fetchall()]
    monthly_dict = {r["month"]: float(r["revenue"]) for r in monthly_rows}

    # 建立平滑連續的最近 6 個月份時間軸 (確保折線圖具有完整的趨勢時間軸感)
    latest_month = max(monthly_dict.keys()) if monthly_dict else datetime.date.today().strftime("%Y-%m")
    try:
        y, m = map(int, latest_month.split("-"))
    except ValueError:
        today = datetime.date.today()
        y, m = today.year, today.month

    timeline_months = []
    for i in range(5, -1, -1):
        curr_m = m - i
        curr_y = y
        while curr_m <= 0:
            curr_m += 12
            curr_y -= 1
        timeline_months.append(f"{curr_y:04d}-{curr_m:02d}")

    for k in sorted(monthly_dict.keys()):
        if k not in timeline_months:
            timeline_months.append(k)
    timeline_months = sorted(list(set(timeline_months)))

    trend_labels = timeline_months
    trend_revenues = [monthly_dict.get(m_str, 0.0) for m_str in timeline_months]
    max_monthly_revenue = max(trend_revenues) if trend_revenues else 0.0

    # ----------------------------------------------------
    # 3. 訂單狀態分布：環圈圖 (Chart.js)
    # ----------------------------------------------------
    cursor.execute("""
    SELECT status, COUNT(*) AS count
    FROM orders
    GROUP BY status
    ORDER BY 
        CASE status
            WHEN '已完成' THEN 1
            WHEN '已出貨' THEN 2
            WHEN '處理中' THEN 3
            WHEN '已取消' THEN 4
            ELSE 5
        END;
    """)
    status_distribution = [dict(r) for r in cursor.fetchall()]
    status_labels = [r["status"] for r in status_distribution]
    status_counts = [r["count"] for r in status_distribution]

    # ----------------------------------------------------
    # 4. 熱銷商品 Top 5 (商品名稱、售出數量、營收，排除 '已取消' 之訂單)
    # ----------------------------------------------------
    cursor.execute("""
    SELECT 
        p.product_id,
        p.name AS product_name,
        p.category,
        p.price,
        COALESCE(SUM(oi.quantity), 0) AS total_sold,
        COALESCE(SUM(oi.quantity * oi.unit_price), 0) AS total_revenue
    FROM product p
    JOIN order_item oi ON p.product_id = oi.product_id
    JOIN orders o ON oi.order_id = o.order_id
    WHERE o.status != '已取消'
    GROUP BY p.product_id, p.name
    ORDER BY total_sold DESC, total_revenue DESC
    LIMIT 5;
    """)
    top_products = [dict(r) for r in cursor.fetchall()]

    # ----------------------------------------------------
    # 5. 客戶消費排行 Top 5 (客戶名稱、訂單數、消費金額，排除 '已取消' 之訂單)
    # ----------------------------------------------------
    cursor.execute("""
    SELECT 
        c.customer_id,
        c.name AS customer_name,
        c.phone,
        COUNT(DISTINCT o.order_id) AS order_count,
        COALESCE(SUM(oi.quantity * oi.unit_price), 0) AS total_spent
    FROM customer c
    JOIN orders o ON c.customer_id = o.customer_id
    JOIN order_item oi ON o.order_id = oi.order_id
    WHERE o.status != '已取消'
    GROUP BY c.customer_id, c.name
    ORDER BY total_spent DESC, order_count DESC
    LIMIT 5;
    """)
    top_customers = [dict(r) for r in cursor.fetchall()]

    conn.close()

    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    return render_template(
        "admin_dashboard.html",
        kpi=kpi,
        total_orders_count=total_orders_count,
        cancelled_orders_count=cancelled_orders_count,
        trend_labels=trend_labels,
        trend_revenues=trend_revenues,
        max_monthly_revenue=max_monthly_revenue,
        status_distribution=status_distribution,
        status_labels=status_labels,
        status_counts=status_counts,
        top_products=top_products,
        top_customers=top_customers,
        current_time=current_time,
    )



# ==========================================
# 需求 1: 管理員登入 (Werkzeug 雜湊比對，不存明碼)
# ==========================================
@app.route("/login", methods=["GET", "POST"])
def login():
    ensure_db()
    # 已登入且角色為 admin 者直接進入後台
    if session.get("admin") and session.get("role") == "admin":
        return redirect(url_for("index"))

    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        conn = get_connection()
        cursor = conn.cursor()
        # 需求 3: 參數化查詢 (? 佔位符)
        cursor.execute("SELECT id, username, password_hash, role FROM admin WHERE username = ?", (username,))
        admin_row = cursor.fetchone()
        conn.close()

        # 需求 1: 使用 werkzeug check_password_hash 驗證雜湊，不出現明碼比對
        if admin_row and check_password_hash(admin_row["password_hash"], password):
            # 需求 2: 嚴格驗證角色是否為 admin
            if admin_row["role"] != "admin":
                error = "權限不足：您的帳號並非管理員 (admin) 角色"
            else:
                session["admin"] = admin_row["username"]
                session["role"] = admin_row["role"]
                next_url = request.args.get("next")
                if not next_url or "/login" in next_url:
                    next_url = url_for("index")
                return redirect(next_url)
        else:
            error = "帳號或密碼錯誤，請重新輸入"

    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ==========================================
# 需求 2 & 9: 訂單出貨單 QRCode 專屬頁面 (需登入且角色為 admin)
# ==========================================
@app.route("/order/<order_ref>")
@admin_required
def order_detail(order_ref):
    """
    專屬出貨單頁面：
    支援以 order_code (如 SO0001) 或 order_id 查詢 (全參數化查詢)
    """
    ensure_db()
    conn = get_connection()
    cursor = conn.cursor()

    # 需求 3: 參數化查詢
    cursor.execute("""
    SELECT o.order_id, o.order_code, o.customer_id, c.name AS customer_name, c.phone AS customer_phone,
           c.address AS customer_address, o.order_date, o.status, o.salesperson
    FROM orders o
    JOIN customer c ON o.customer_id = c.customer_id
    WHERE o.order_code = ? OR o.order_id = ?;
    """, (str(order_ref), str(order_ref)))
    order = cursor.fetchone()

    if not order:
        conn.close()
        return "找不到此訂單 (Order Not Found)", 404

    # 查詢該訂單之各明細 (unit_price 保存下單當時成交價)
    cursor.execute("""
    SELECT oi.product_id, p.name AS product_name, p.category, oi.quantity, oi.unit_price,
           (oi.quantity * oi.unit_price) AS subtotal
    FROM order_item oi
    JOIN product p ON oi.product_id = p.product_id
    WHERE oi.order_id = ?
    ORDER BY oi.product_id;
    """, (order["order_id"],))
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
        is_admin=bool(session.get("admin") and session.get("role") == "admin"),
    )


# ==========================================
# 需求 4, 5, 6, 7: 新增訂單 (下拉選單、SO+數字 格式驗證、數量正整數三層阻擋)
# ==========================================
@app.route("/admin/orders/new", methods=["GET", "POST"])
@admin_required
def order_new():
    ensure_db()
    conn = get_connection()
    cursor = conn.cursor()

    if request.method == "POST":
        order_code = request.form.get("order_code", "").strip().upper()
        customer_id = request.form.get("customer_id")
        order_date = request.form.get("order_date") or datetime.date.today().isoformat()
        salesperson = request.form.get("salesperson", "").strip() or "陳冠宇"
        status = request.form.get("status", "處理中")

        # 取得下拉選單所選的多筆商品與數量
        product_ids = request.form.getlist("product_id")
        quantities = request.form.getlist("quantity")

        # ----------------------------------------------------
        # 需求 4 格式驗證: 訂單編號必須為 SO+數字 (第 2 層：後端驗證)
        # ----------------------------------------------------
        if not re.match(r"^SO\d+$", order_code):
            conn.close()
            return "【格式錯誤】訂單編號必須為 SO+數字 (例如 SO0006)", 400

        # 檢查訂單編號是否已重複 (需求 3 參數化)
        cursor.execute("SELECT order_id FROM orders WHERE order_code = ?", (order_code,))
        if cursor.fetchone():
            conn.close()
            return f"【代碼衝突】訂單編號 {order_code} 已存在，請使用不同編號", 400

        if not customer_id or not product_ids:
            conn.close()
            return "請選擇客戶並至少加入一項商品", 400

        # ----------------------------------------------------
        # 需求 5 數量驗證: 必須為正整數 (第 2 層：後端驗證，排除小數、0、負數)
        # ----------------------------------------------------
        validated_items = []
        for pid_str, qty_str in zip(product_ids, quantities):
            if not pid_str:
                continue

            qty_clean = str(qty_str).strip()
            # 拒絕小數點、負號、非數字
            if not qty_clean.isdigit() or "." in qty_clean:
                conn.close()
                return "【數量錯誤】商品數量必須為大於 0 的正整數（不可為小數或包含非數字字元）", 400

            try:
                qty_int = int(qty_clean)
                if qty_int <= 0:
                    conn.close()
                    return "【數量錯誤】商品數量必須大於 0", 400
            except (ValueError, TypeError):
                conn.close()
                return "【數量錯誤】數量格式無效", 400

            validated_items.append((int(pid_str), qty_int))

        if not validated_items:
            conn.close()
            return "訂單未包含任何有效商品項目", 400

        try:
            # 1. 寫入 orders 主檔 (需求 3 參數化查詢)
            cursor.execute("""
            INSERT INTO orders (order_code, customer_id, order_date, status, salesperson)
            VALUES (?, ?, ?, ?, ?);
            """, (order_code, customer_id, order_date, status, salesperson))
            order_id = cursor.lastrowid

            # 2. 寫入 order_item 明細檔 (需求 5 第 3 層：資料庫 CHECK 正整數約束)
            #    需求 7: 儲存當下商品之單價快照
            for pid, quantity in validated_items:
                cursor.execute("SELECT price FROM product WHERE product_id = ?", (pid,))
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
            return redirect(url_for("order_detail", order_ref=order_code))
        except sqlite3.IntegrityError as err:
            conn.rollback()
            conn.close()
            return f"資料庫約束衝突 (CHECK 約束或複合主鍵阻擋): {str(err)}", 400
        except Exception as e:
            conn.rollback()
            conn.close()
            return f"建立訂單失敗: {str(e)}", 400

    # GET 請求：準備下拉選單資料
    cursor.execute("SELECT customer_id, name, phone FROM customer ORDER BY customer_id;")
    customers = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT product_id, name, price, stock, category FROM product ORDER BY product_id;")
    products = [dict(r) for r in cursor.fetchall()]

    # 計算預設建議之下一筆 SO 編號 (如 SO0006)
    cursor.execute("SELECT order_code FROM orders ORDER BY order_id DESC LIMIT 1;")
    last_row = cursor.fetchone()
    next_code = "SO0001"
    if last_row and last_row["order_code"]:
        m = re.search(r"\d+", last_row["order_code"])
        if m:
            next_num = int(m.group(0)) + 1
            next_code = f"SO{next_num:04d}"

    conn.close()
    today_date = datetime.date.today().isoformat()
    return render_template(
        "order_new.html",
        customers=customers,
        products=products,
        today_date=today_date,
        next_code=next_code,
    )


# ==========================================
# 需求 8: 訂單狀態即時更新 (列表直接操作)
# ==========================================
@app.route("/admin/orders/update_status/<int:order_id>", methods=["POST"])
@admin_required
def order_update_status(order_id):
    ensure_db()
    new_status = request.form.get("status")
    allowed = ["處理中", "已出貨", "已完成", "已取消"]
    if new_status in allowed:
        conn = get_connection()
        cursor = conn.cursor()
        # 需求 3: 參數化查詢
        cursor.execute("UPDATE orders SET status = ? WHERE order_id = ?", (new_status, order_id))
        conn.commit()
        conn.close()

    return redirect(request.referrer or url_for("index"))


@app.route("/admin/orders/delete/<int:order_id>", methods=["POST"])
@admin_required
def order_delete(order_id):
    ensure_db()
    conn = get_connection()
    cursor = conn.cursor()
    # 需求 3: 參數化查詢
    cursor.execute("DELETE FROM orders WHERE order_id = ?", (order_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("index"))


# ==========================================
# 後台維護：客戶 CRUD (全參數化)
# ==========================================
@app.route("/admin/customer/add", methods=["POST"])
@admin_required
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
@admin_required
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
@admin_required
def customer_delete(customer_id):
    ensure_db()
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM customer WHERE customer_id = ?", (customer_id,))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()
    return redirect(url_for("index"))


# ==========================================
# 後台維護：商品 CRUD (全參數化，改價不影響歷史訂單)
# ==========================================
@app.route("/admin/product/add", methods=["POST"])
@admin_required
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
@admin_required
def product_edit(product_id):
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
@admin_required
def product_delete(product_id):
    ensure_db()
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM product WHERE product_id = ?", (product_id,))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()
    return redirect(url_for("index"))


# ==========================================
# JSON API 檢測介面 (全參數化)
# ==========================================
@app.route("/api/check")
def api_check():
    ensure_db()
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT customer_id, name, phone, address, created_date FROM customer ORDER BY customer_id;")
    customers = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT product_id, name, price, stock, category FROM product ORDER BY product_id;")
    products = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT order_id, order_code, customer_id, order_date, status, salesperson FROM orders ORDER BY order_id;")
    orders = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT order_id, product_id, quantity, unit_price FROM order_item ORDER BY order_id, product_id;")
    order_items = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT id, username, role FROM admin ORDER BY id;")
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
            "admins": admins,
            "customers": customers,
            "products": products,
            "orders": orders,
            "order_items": order_items,
        },
    })


if __name__ == "__main__":
    ensure_db()
    print("=" * 60)
    print("  📦 SQLite 企業訂單管理系統已啟動")
    print("  監聽連接埠：Port 5000")
    print("  網址：http://127.0.0.1:5000/")
    print("=" * 60)
    app.run(debug=True, host="127.0.0.1", port=5000)
