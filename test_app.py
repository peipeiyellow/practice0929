import sqlite3
import unittest
from app import app
from create_db import get_connection, init_database


class AppTestCase(unittest.TestCase):
    def setUp(self):
        # 每次測試前重置資料庫為初始狀態
        init_database()
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def test_hello_world_status_code(self):
        """測試首頁 HTTP 狀態碼"""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

    def test_hello_world_content(self):
        """測試首頁包含 Hello World 文字"""
        response = self.client.get("/")
        self.assertIn("Hello World", response.get_data(as_text=True))

    def test_admin_login_success_and_failure(self):
        """測試需求 5: 管理員登入成功與失敗流程 (admin / admin123)"""
        # 失敗密碼測試
        fail_res = self.client.post("/login", data={"username": "admin", "password": "wrongpassword"})
        self.assertIn("帳號或密碼錯誤", fail_res.get_data(as_text=True))

        # 成功登入測試
        success_res = self.client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=True)
        self.assertEqual(success_res.status_code, 200)
        self.assertIn("管理員：", success_res.get_data(as_text=True))

    def test_order_detail_page_and_qrcode(self):
        """測試需求 9: 訂單專屬頁面 /order/<id> 與出貨單 QRCode 容器"""
        response = self.client.get("/order/1")
        self.assertEqual(response.status_code, 200)
        content = response.get_data(as_text=True)
        self.assertIn("出貨明細單", content)
        self.assertIn("台灣積體電路製造股份有限公司", content)
        self.assertIn("qrcode", content)

    def test_order_status_update(self):
        """測試需求 8: 訂單狀態在列表中直接更新"""
        # 模擬管理員登入
        with self.client.session_transaction() as sess:
            sess["admin"] = "admin"

        # 更新訂單 3 的狀態為 '已出貨'
        post_res = self.client.post("/admin/orders/update_status/3", data={"status": "已出貨"}, follow_redirects=True)
        self.assertEqual(post_res.status_code, 200)

        # 檢查資料庫狀態是否已更新
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM orders WHERE order_id = 3;")
        status = cursor.fetchone()["status"]
        conn.close()
        self.assertEqual(status, "已出貨")

    def test_multi_item_order_and_historical_price_preservation(self):
        """
        測試需求 6 & 7:
        1. 新增訂單可一次勾選多項商品填數量
        2. order_item 儲存下單當下價格，商品改價不影響歷史訂單
        """
        # 登入管理員
        with self.client.session_transaction() as sess:
            sess["admin"] = "admin"

        # 取得商品 1 原價格 ($45,900) 與商品 2 原價格 ($16,800)
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT price FROM product WHERE product_id = 1;")
        orig_p1_price = cursor.fetchone()["price"]
        conn.close()

        # 建立新訂單：勾選商品 1 (數量 2) 與商品 2 (數量 1)
        res = self.client.post(
            "/admin/orders/new",
            data={
                "customer_id": "1",
                "order_date": "2026-10-10",
                "salesperson": "陳冠宇",
                "status": "處理中",
                "product_ids": ["1", "2"],
                "quantity_1": "2",
                "quantity_2": "1",
            },
            follow_redirects=True,
        )
        self.assertEqual(res.status_code, 200)

        # 查詢新建立的訂單明細中的成交單價
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(order_id) as new_id FROM orders;")
        new_order_id = cursor.fetchone()["new_id"]

        cursor.execute("SELECT unit_price FROM order_item WHERE order_id = ? AND product_id = 1;", (new_order_id,))
        saved_unit_price = cursor.fetchone()["unit_price"]
        self.assertEqual(saved_unit_price, orig_p1_price)

        # 模擬商品 1 改價：由 $45,900 大幅調整為 $99,999
        self.client.post(
            "/admin/product/edit/1",
            data={"name": "旗艦級 AI 智慧筆電 16吋", "price": "99999", "stock": "50", "category": "電腦設備"},
        )

        # 驗證商品表價格已變更
        cursor.execute("SELECT price FROM product WHERE product_id = 1;")
        new_prod_price = cursor.fetchone()["price"]
        self.assertEqual(new_prod_price, 99999.0)

        # 關鍵驗收 (需求 7)：歷史訂單明細中的單價必須完全不受商品改價影響！
        cursor.execute("SELECT unit_price FROM order_item WHERE order_id = ? AND product_id = 1;", (new_order_id,))
        historical_price = cursor.fetchone()["unit_price"]
        self.assertEqual(historical_price, orig_p1_price)

        conn.close()

    def test_sqlite_check_constraints(self):
        """測試 SQLite CHECK 約束與複合主鍵保護機制"""
        conn = get_connection()
        cursor = conn.cursor()

        # 測試數量 <= 0 CHECK 約束
        with self.assertRaises(sqlite3.IntegrityError):
            cursor.execute("INSERT INTO order_item (order_id, product_id, quantity, unit_price) VALUES (1, 2, 0, 100);")

        # 測試單價 < 0 CHECK 約束
        with self.assertRaises(sqlite3.IntegrityError):
            cursor.execute("INSERT INTO order_item (order_id, product_id, quantity, unit_price) VALUES (1, 2, 1, -50);")

        # 測試複合主鍵重疊
        with self.assertRaises(sqlite3.IntegrityError):
            cursor.execute("INSERT INTO order_item (order_id, product_id, quantity, unit_price) VALUES (1, 1, 3, 45900);")

        conn.close()


if __name__ == "__main__":
    unittest.main()
