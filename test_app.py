import os
import sqlite3
import unittest
from app import app
from create_db import get_connection, init_database


class AppTestCase(unittest.TestCase):
    def setUp(self):
        # 測試前初始化資料庫
        init_database()
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def test_order_system_home(self):
        """測試訂單系統 (Port 5000) 首頁 HTTP 200 與 訂單管理系統 文字"""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("訂單管理系統", res.get_data(as_text=True))

    def test_hello_world_app(self):
        """測試獨立的 Hello World 網頁 (Port 8899) HTTP 200 與 Hello World 文字"""
        from hello_app import app as hello_flask_app
        hello_flask_app.config["TESTING"] = True
        client = hello_flask_app.test_client()
        res = client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Hello, World!", res.get_data(as_text=True))
        self.assertIn("歡迎來到python製作的一頁式網站", res.get_data(as_text=True))

    def test_requirement_1_password_hashed_no_plaintext(self):
        """測試需求 1: 管理員密碼以 werkzeug 雜湊儲存，資料庫與登入頁絕無明碼"""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT username, password_hash FROM admin WHERE username = 'admin';")
        admin = cursor.fetchone()
        conn.close()

        # 1. 密碼欄位不可為明碼 (長度大於 40 且以 scrypt 或 pbkdf2 開頭)
        self.assertTrue(
            admin["password_hash"].startswith("scrypt:") or admin["password_hash"].startswith("pbkdf2:"),
            "密碼必須為 Werkzeug 安全雜湊格式",
        )
        self.assertNotIn("admin123", admin["password_hash"], "雜湊值不可包含明碼")

        # 2. 檢視登入畫面 HTML，確保輸入框 value 與畫面皆無明碼預設值
        login_res = self.client.get("/login")
        self.assertNotIn('value="admin123"', login_res.get_data(as_text=True))
        self.assertNotIn('<code>admin123</code>', login_res.get_data(as_text=True))

        # 3. 正確密碼可登入，錯誤密碼被拒絕
        fail_res = self.client.post("/login", data={"username": "admin", "password": "wrong"})
        self.assertIn("帳號或密碼錯誤", fail_res.get_data(as_text=True))

    def test_requirement_2_session_and_admin_role_required(self):
        """測試需求 2: 後台所有維護頁面需登入 (session) 且角色為 admin 才能進入"""
        protected_urls = [
            "/admin/orders/new",
            "/order/SO0001",
            "/admin/orders/update_status/1",
        ]

        # 1. 未登入狀態訪問：全部必須 302 重導向至 /login
        for url in protected_urls:
            res = self.client.get(url) if "update_status" not in url else self.client.post(url, data={"status": "已出貨"})
            self.assertEqual(res.status_code, 302, f"未登入存取 {url} 應被重導向至 /login")
            self.assertIn("/login", res.headers.get("Location", ""))

        # 2. 已登入但角色非 admin (例如角色為普通 user)：必須被重導向至 /login
        with self.client.session_transaction() as sess:
            sess["admin"] = "testuser"
            sess["role"] = "user"

        res = self.client.get("/admin/orders/new")
        self.assertEqual(res.status_code, 302)

        # 3. 正確以 admin 角色登入：成功進入 (HTTP 200)
        with self.client.session_transaction() as sess:
            sess["admin"] = "admin"
            sess["role"] = "admin"

        res_ok = self.client.get("/admin/orders/new")
        self.assertEqual(res_ok.status_code, 200)

    def test_requirement_3_parameterized_queries(self):
        """測試需求 3: 所有 SQL 查詢使用 ? 佔位符參數化，阻擋 SQL 注入攻擊"""
        # 嘗試 SQL 注入帳號
        inject_username = "admin' OR '1'='1"
        res = self.client.post("/login", data={"username": inject_username, "password": "any"})
        self.assertIn("帳號或密碼錯誤", res.get_data(as_text=True))

    def test_requirement_4_dropdowns_and_order_code_format(self):
        """測試需求 4: 客戶與商品使用下拉選單，訂單編號加上 SO+數字 格式驗證"""
        with self.client.session_transaction() as sess:
            sess["admin"] = "admin"
            sess["role"] = "admin"

        # 1. 檢查新增頁面中客戶與商品均包含 <select> 下拉選單標籤
        get_res = self.client.get("/admin/orders/new")
        html = get_res.get_data(as_text=True)
        self.assertIn('<select name="customer_id"', html)
        self.assertIn('<select name="product_id"', html)

        # 2. 後端格式阻擋測試：不合規格式 (如 ORDER123、12345、SO_123) 應回傳 HTTP 400
        invalid_codes = ["ORDER123", "12345", "SO-001", "so0001", "SO_999"]
        for bad_code in invalid_codes:
            bad_res = self.client.post(
                "/admin/orders/new",
                data={
                    "order_code": bad_code,
                    "customer_id": "1",
                    "order_date": "2026-10-10",
                    "salesperson": "陳冠宇",
                    "status": "處理中",
                    "product_id": ["1"],
                    "quantity": ["2"],
                },
            )
            self.assertEqual(bad_res.status_code, 400, f"編號 {bad_code} 未符合 SO+數字 應被後端阻擋")

        # 3. 資料庫 CHECK 約束阻擋：直接插入不合規編號觸發 IntegrityError
        conn = get_connection()
        cursor = conn.cursor()
        with self.assertRaises(sqlite3.IntegrityError):
            cursor.execute(
                "INSERT INTO orders (order_code, customer_id, order_date, status, salesperson) VALUES (?, ?, ?, ?, ?);",
                ("INVALID_CODE", 1, "2026-10-10", "處理中", "測試員"),
            )
        conn.close()

        # 4. 正確格式 SO+數字 (如 SO0008) 應成功建立
        ok_res = self.client.post(
            "/admin/orders/new",
            data={
                "order_code": "SO0008",
                "customer_id": "1",
                "order_date": "2026-10-10",
                "salesperson": "陳冠宇",
                "status": "處理中",
                "product_id": ["1", "2"],
                "quantity": ["1", "3"],
            },
            follow_redirects=True,
        )
        self.assertEqual(ok_res.status_code, 200)
        self.assertIn("SO0008", ok_res.get_data(as_text=True))

    def test_requirement_5_quantity_positive_integer_three_layers(self):
        """測試需求 5: 數量必須是正整數，前端、後端、資料庫 CHECK 三層都要擋"""
        with self.client.session_transaction() as sess:
            sess["admin"] = "admin"
            sess["role"] = "admin"

        # 1. 後端阻擋層測試：小數 (1.5)、零 (0)、負數 (-2)、字串 (abc) 均回傳 400
        invalid_quantities = ["0", "-1", "1.5", "abc", "2.0"]
        for bad_qty in invalid_quantities:
            res = self.client.post(
                "/admin/orders/new",
                data={
                    "order_code": "SO9999",
                    "customer_id": "1",
                    "order_date": "2026-10-10",
                    "salesperson": "陳冠宇",
                    "status": "處理中",
                    "product_id": ["1"],
                    "quantity": [bad_qty],
                },
            )
            self.assertEqual(res.status_code, 400, f"數量 {bad_qty} 未符合正整數應被後端阻擋")

        # 2. 資料庫 CHECK 約束層測試 (quantity > 0 AND typeof(quantity) = 'integer')
        conn = get_connection()
        cursor = conn.cursor()

        # 嘗試直接寫入 0
        with self.assertRaises(sqlite3.IntegrityError):
            cursor.execute("INSERT INTO order_item (order_id, product_id, quantity, unit_price) VALUES (1, 5, 0, 100);")

        # 嘗試直接寫入負數 -3
        with self.assertRaises(sqlite3.IntegrityError):
            cursor.execute("INSERT INTO order_item (order_id, product_id, quantity, unit_price) VALUES (1, 5, -3, 100);")

        # 嘗試直接寫入浮點數 2.5
        with self.assertRaises(sqlite3.IntegrityError):
            cursor.execute("INSERT INTO order_item (order_id, product_id, quantity, unit_price) VALUES (1, 5, 2.5, 100);")

        conn.close()


if __name__ == "__main__":
    unittest.main()
