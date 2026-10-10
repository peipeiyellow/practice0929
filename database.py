import os
import sqlite3
import sys
from werkzeug.security import generate_password_hash

# 強制標準輸出為 UTF-8 編碼，防止 Windows 終端機產生中文亂碼
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

DATABASE = os.path.join(os.path.dirname(__file__), "orders.db")


def get_db(db_path=DATABASE):
    """取得資料庫連線並啟用外鍵約束"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path=DATABASE):
    """初始化建立 orders.db 與資料表"""
    conn = get_db(db_path)
    cursor = conn.cursor()

    cursor.execute("DROP TABLE IF EXISTS order_item;")
    cursor.execute("DROP TABLE IF EXISTS orders;")
    cursor.execute("DROP TABLE IF EXISTS product;")
    cursor.execute("DROP TABLE IF EXISTS customer;")
    cursor.execute("DROP TABLE IF EXISTS admin;")

    # 0. 管理員資料表 admin (含 role 角色欄位)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS admin (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'admin'
    );
    """)

    # 1. 客戶資料表 customer (客戶編號 PK、名稱、電話、地址、建檔日期)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS customer (
        customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        phone TEXT NOT NULL,
        address TEXT NOT NULL,
        created_date TEXT NOT NULL
    );
    """)

    # 2. 商品資料表 product (商品編號 PK、名稱、單價、庫存、分類)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS product (
        product_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        price REAL NOT NULL CHECK (price >= 0),
        stock INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0),
        category TEXT NOT NULL
    );
    """)

    # 3. 訂單資料表 orders (order_code 格式約束: SO+數字)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        order_id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_code TEXT UNIQUE NOT NULL CHECK (order_code GLOB 'SO[0-9]*' AND length(order_code) >= 3),
        customer_id INTEGER NOT NULL,
        order_date TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT '處理中',
        salesperson TEXT NOT NULL,
        FOREIGN KEY (customer_id) REFERENCES customer(customer_id) ON DELETE RESTRICT
    );
    """)

    # 4. 訂單明細資料表 order_item (數量嚴格正整數 CHECK)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS order_item (
        order_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL CHECK (quantity > 0 AND typeof(quantity) = 'integer'),
        unit_price REAL NOT NULL CHECK (unit_price >= 0),
        PRIMARY KEY (order_id, product_id),
        FOREIGN KEY (order_id) REFERENCES orders(order_id) ON DELETE CASCADE,
        FOREIGN KEY (product_id) REFERENCES product(product_id) ON DELETE RESTRICT
    );
    """)

    conn.commit()
    seed_data(conn)
    conn.close()


def seed_data(conn):
    """插入繁體中文測試資料與管理員帳號"""
    cursor = conn.cursor()

    # 0. 建立管理員 (雜湊儲存，不顯明碼)
    cursor.execute("SELECT id FROM admin WHERE username = ?", ("admin",))
    if not cursor.fetchone():
        default_pw = os.environ.get("ADMIN_PASSWORD", "admin123")
        cursor.execute(
            "INSERT INTO admin (username, password_hash, role) VALUES (?, ?, ?);",
            ("admin", generate_password_hash(default_pw), "admin"),
        )

    # 1. 客戶資料 5 筆
    cursor.execute("SELECT COUNT(*) FROM customer;")
    if cursor.fetchone()[0] == 0:
        customers = [
            ("台灣積體電路製造股份有限公司", "03-5636688", "新竹科學園區研新一路9號", "2026-01-15"),
            ("鴻海精密工業股份有限公司", "02-22683466", "新北市土城區自由街2號", "2026-02-20"),
            ("聯發科技股份有限公司", "03-5788888", "新竹市東區篤行一路1號", "2026-03-10"),
            ("宏碁股份有限公司", "02-26961234", "新北市汐止區新台五路一段88號", "2026-04-05"),
            ("華碩電腦股份有限公司", "02-28943447", "台北市北投區立德路15號", "2026-05-18"),
        ]
        cursor.executemany(
            "INSERT INTO customer (name, phone, address, created_date) VALUES (?, ?, ?, ?);",
            customers,
        )

    # 2. 商品資料 5 筆
    cursor.execute("SELECT COUNT(*) FROM product;")
    if cursor.fetchone()[0] == 0:
        products = [
            ("旗艦級 AI 智慧筆電 16吋", 45900.0, 50, "電腦設備"),
            ("4K HDR 電競曲面螢幕 32吋", 16800.0, 35, "顯示設備"),
            ("人體工學靜音機械鍵盤", 3280.0, 120, "周邊配件"),
            ("企業級雙頻 WiFi 7 路由器", 8800.0, 40, "網通設備"),
            ("主動降噪真無線藍牙耳機 Pro", 5490.0, 80, "影音設備"),
        ]
        cursor.executemany(
            "INSERT INTO product (name, price, stock, category) VALUES (?, ?, ?, ?);",
            products,
        )

    # 3. 訂單資料 5 筆 (SO+數字)
    cursor.execute("SELECT COUNT(*) FROM orders;")
    if cursor.fetchone()[0] == 0:
        orders = [
            ("SO0001", 1, "2026-10-01", "已完成", "陳冠宇"),
            ("SO0002", 2, "2026-10-03", "已出貨", "林雅婷"),
            ("SO0003", 3, "2026-10-05", "處理中", "張家豪"),
            ("SO0004", 4, "2026-10-07", "處理中", "王怡君"),
            ("SO0005", 5, "2026-10-09", "已取消", "陳冠宇"),
        ]
        cursor.executemany(
            "INSERT INTO orders (order_code, customer_id, order_date, status, salesperson) VALUES (?, ?, ?, ?, ?);",
            orders,
        )

        # 4. 訂單明細資料
        order_items = [
            (1, 1, 2, 45900.0),
            (1, 3, 5, 3280.0),
            (2, 2, 1, 16800.0),
            (2, 4, 2, 8800.0),
            (2, 5, 3, 5490.0),
            (3, 1, 1, 45900.0),
            (3, 5, 2, 5490.0),
            (4, 3, 3, 3280.0),
            (4, 4, 1, 8800.0),
            (5, 2, 2, 16800.0),
        ]
        cursor.executemany(
            "INSERT INTO order_item (order_id, product_id, quantity, unit_price) VALUES (?, ?, ?, ?);",
            order_items,
        )

    conn.commit()


if __name__ == "__main__":
    init_db()
    print("orders.db 資料庫初始化完成 (管理員密碼雜湊儲存)。")
