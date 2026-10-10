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

    def test_requirement_2_unauthenticated_backend_access_blocked(self):
        """
        測試需求 2: 未登入訪問後台任何頁面與端點，均被全域攔截阻擋
        """
        protected_urls = [
            "/",
            "/orders",
            "/order/SO0001",
            "/admin/orders/new",
            "/admin/orders/update_status/1",
            "/admin/customer/add",
            "/admin/product/add",
        ]

        # 1. 網頁頁面未登入：全部必須 302 重導向至 /login
        for url in protected_urls:
            if "update_status" in url or "add" in url:
                res = self.client.post(url, data={})
            else:
                res = self.client.get(url)
            self.assertEqual(res.status_code, 302, f"未登入存取 {url} 應被 302 重導向")
            self.assertIn("/login", res.headers.get("Location", ""))

        # 2. 後台 API 未登入：回傳 401 Unauthorized
        api_res = self.client.get("/api/check")
        self.assertEqual(api_res.status_code, 401, "未登入存取後台 API 應回傳 401")

    def test_requirement_2_non_admin_role_blocked(self):
        """
        測試需求 2: 雖有登入但角色非 admin (如 role: user / guest)，仍被拒絕存取後台
        """
        with self.client.session_transaction() as sess:
            sess["admin"] = "normal_user"
            sess["role"] = "user"

        # 訪問首頁與新增訂單均應被重導向至 /login
        res_home = self.client.get("/")
        self.assertEqual(res_home.status_code, 302)
        self.assertIn("/login", res_home.headers.get("Location", ""))

        res_new = self.client.get("/admin/orders/new")
        self.assertEqual(res_new.status_code, 302)
        self.assertIn("/login", res_new.headers.get("Location", ""))

        # API 亦應回傳 401
        res_api = self.client.get("/api/check")
        self.assertEqual(res_api.status_code, 401)

    def test_requirement_2_admin_role_access_granted(self):
        """
        測試需求 2: 成功以管理員角色 (role: admin) 登入後，後台所有頁面可正常存取
        """
        with self.client.session_transaction() as sess:
            sess["admin"] = "admin"
            sess["role"] = "admin"

        # 1. 首頁總覽儀表板 (HTTP 200)
        res_home = self.client.get("/")
        self.assertEqual(res_home.status_code, 200)
        self.assertIn("SQLite 企業訂單管理系統", res_home.get_data(as_text=True))

        # 2. 專屬出貨單頁面 (HTTP 200)
        res_order = self.client.get("/order/SO0001")
        self.assertEqual(res_order.status_code, 200)
        self.assertIn("出貨明細單", res_order.get_data(as_text=True))

        # 3. 新增訂單頁面 (HTTP 200)
        res_new = self.client.get("/admin/orders/new")
        self.assertEqual(res_new.status_code, 200)

        # 4. API 查詢 (HTTP 200)
        res_api = self.client.get("/api/check")
        self.assertEqual(res_api.status_code, 200)

    def test_requirement_1_password_hashed_no_plaintext(self):
        """測試需求 1: 管理員密碼以 werkzeug 雜湊儲存，資料庫與登入頁絕無明碼"""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT username, password_hash, role FROM admin WHERE username = 'admin';")
        admin = cursor.fetchone()
        conn.close()

        # 1. 密碼欄位必須為 Werkzeug 安全雜湊格式
        self.assertTrue(
            admin["password_hash"].startswith("scrypt:") or admin["password_hash"].startswith("pbkdf2:"),
            "密碼必須為 Werkzeug 安全雜湊格式",
        )
        self.assertEqual(admin["role"], "admin")

        # 2. 登入畫面 HTML 絕無明碼預設值
        login_res = self.client.get("/login")
        self.assertNotIn('value="admin123"', login_res.get_data(as_text=True))
        self.assertNotIn('<code>admin123</code>', login_res.get_data(as_text=True))

        # 3. 正確密碼可登入並寫入 admin 角色 session，錯誤密碼被拒絕
        fail_res = self.client.post("/login", data={"username": "admin", "password": "wrong"})
        self.assertIn("帳號或密碼錯誤", fail_res.get_data(as_text=True))

        success_res = self.client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=False)
        self.assertEqual(success_res.status_code, 302)

    def test_requirement_3_parameterized_queries(self):
        """測試需求 3: 所有 SQL 查詢使用 ? 佔位符參數化，阻擋 SQL 注入攻擊"""
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

        # 2. 後端格式阻擋測試：不合規格式 (如 ORDER123、12345、SO-001) 應回傳 HTTP 400
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

        # 1. 後端阻擋層測試：小數 (1.5)、零 (0)、負數 (-1)、字串 (abc) 均回傳 400
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

    def test_hello_world_independent_app(self):
        """測試獨立的 Hello World 網頁 (Port 8899) 為公開服務且運作正常"""
        from hello_app import app as hello_flask_app
        hello_flask_app.config["TESTING"] = True
        client = hello_flask_app.test_client()
        res = client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Hello, World!", res.get_data(as_text=True))
        self.assertIn("歡迎來到python製作的一頁式網站", res.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
