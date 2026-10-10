import os
import sqlite3
from werkzeug.security import generate_password_hash

DATABASE = os.path.join(os.path.dirname(__file__), "order_system.db")


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # 1. 管理員資料表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS admin (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL
    );
    """)

    # 2. 客戶資料表 customer (客戶編號PK、名稱、電話、地址)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS customer (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        phone TEXT,
        address TEXT
    );
    """)

    # 3. 商品資料表 product (商品編號PK、名稱、單價、庫存、分類)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS product (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        price REAL NOT NULL,
        stock INTEGER NOT NULL DEFAULT 0,
        category TEXT
    );
    """)

    # 4. 訂單資料表 orders (訂單編號PK、客戶編號FK、訂單日期、狀態、業務人員)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER NOT NULL,
        order_date TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT '處理中',
        salesperson TEXT NOT NULL,
        FOREIGN KEY (customer_id) REFERENCES customer(id) ON DELETE RESTRICT
    );
    """)

    # 5. 訂單明細資料表 order_item (訂單編號FK、商品編號FK、數量、單價), 複合主鍵
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS order_item (
        order_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL,
        unit_price REAL NOT NULL,
        PRIMARY KEY (order_id, product_id),
        FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
        FOREIGN KEY (product_id) REFERENCES product(id) ON DELETE RESTRICT
    );
    """)

    conn.commit()
    seed_data(conn)
    conn.close()


def seed_data(conn):
    cursor = conn.cursor()

    # 建立預設管理員 (admin / admin123)
    cursor.execute("SELECT id FROM admin WHERE username = ?", ("admin",))
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO admin (username, password_hash) VALUES (?, ?)",
            ("admin", generate_password_hash("admin123")),
        )

    # 檢查是否已存在客戶資料
    cursor.execute("SELECT COUNT(*) FROM customer")
    if cursor.fetchone()[0] == 0:
        customers = [
            ("台灣積體電路股份有限公司", "03-5636688", "新竹科學園區研新一路9號"),
            ("鴻海精密工業股份有限公司", "02-22683466", "新北市土城區自由街2號"),
            ("聯發科技股份有限公司", "03-5788888", "新竹市東區篤行一路1號"),
            ("宏碁股份有限公司", "02-26961234", "新北市汐止區新台五路一段88號"),
            ("華碩電腦股份有限公司", "02-28943447", "台北市北投區立德路15號"),
        ]
        cursor.executemany(
            "INSERT INTO customer (name, phone, address) VALUES (?, ?, ?)",
            customers,
        )

    # 檢查是否已存在商品資料
    cursor.execute("SELECT COUNT(*) FROM product")
    if cursor.fetchone()[0] == 0:
        products = [
            ("旗艦級 AI 智慧筆記型電腦 16 吋", 45900, 45, "電腦設備"),
            ("4K HDR 超高解析電競螢幕 32 吋", 16800, 30, "顯示設備"),
            ("人體工學靜音無線機械鍵盤", 3280, 100, "周邊配件"),
            ("企業級高效雙頻 WiFi 7 路由器", 8800, 40, "網通設備"),
            ("主動降噪真無線藍牙耳機 Pro", 5490, 80, "影音設備"),
        ]
        cursor.executemany(
            "INSERT INTO product (name, price, stock, category) VALUES (?, ?, ?, ?)",
            products,
        )

    # 檢查是否已存在訂單資料
    cursor.execute("SELECT COUNT(*) FROM orders")
    if cursor.fetchone()[0] == 0:
        orders = [
            (1, "2026-10-01", "已完成", "陳冠宇"),
            (2, "2026-10-03", "已出貨", "林雅婷"),
            (3, "2026-10-06", "處理中", "張家豪"),
            (4, "2026-10-08", "處理中", "王怡君"),
            (5, "2026-10-09", "已取消", "陳冠宇"),
        ]
        cursor.executemany(
            "INSERT INTO orders (customer_id, order_date, status, salesperson) VALUES (?, ?, ?, ?)",
            orders,
        )

        # 插入訂單明細 (存入下單當時的歷史單價)
        order_items = [
            # 訂單 1: 筆電 x2 ($45900), 鍵盤 x5 ($3280)
            (1, 1, 2, 45900),
            (1, 3, 5, 3280),
            # 訂單 2: 電競螢幕 x3 ($16800), 路由器 x2 ($8800)
            (2, 2, 3, 16800),
            (2, 4, 2, 8800),
            # 訂單 3: 筆電 x1 ($45900), 耳機 x4 ($5490)
            (3, 1, 1, 45900),
            (3, 5, 4, 5490),
            # 訂單 4: 路由器 x1 ($8800), 鍵盤 x2 ($3280)
            (4, 4, 1, 8800),
            (4, 3, 2, 3280),
            # 訂單 5: 電競螢幕 x1 ($16800)
            (5, 2, 1, 16800),
        ]
        cursor.executemany(
            "INSERT INTO order_item (order_id, product_id, quantity, unit_price) VALUES (?, ?, ?, ?)",
            order_items,
        )

    conn.commit()


if __name__ == "__main__":
    init_db()
    print("Database initialized and seeded successfully.")
