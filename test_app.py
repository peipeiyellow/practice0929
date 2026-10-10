import sqlite3
import unittest
from app import app
from create_db import get_connection, init_database


class AppTestCase(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.client = self.app.test_client()

    def test_hello_world_status_code(self):
        """測試首頁 HTTP 狀態碼"""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

    def test_hello_world_content(self):
        """測試首頁包含 Hello World 文字"""
        response = self.client.get("/")
        self.assertIn("Hello World", response.get_data(as_text=True))

    def test_api_check_endpoint(self):
        """測試 /api/check JSON 端點返回正確筆數"""
        response = self.client.get("/api/check")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["counts"]["customers"], 5)
        self.assertEqual(data["counts"]["products"], 5)
        self.assertEqual(data["counts"]["orders"], 5)
        self.assertGreaterEqual(data["counts"]["order_items"], 5)

    def test_check_constraints_and_composite_pk(self):
        """測試 SQLite CHECK 約束與複合主鍵保護機制"""
        conn = get_connection()
        cursor = conn.cursor()

        # 測試 1: order_item 數量 <= 0 應觸發 CHECK 約束錯誤
        with self.assertRaises(sqlite3.IntegrityError):
            cursor.execute(
                "INSERT INTO order_item (order_id, product_id, quantity, unit_price) VALUES (1, 2, 0, 100);"
            )

        # 測試 2: order_item 單價 < 0 應觸發 CHECK 約束錯誤
        with self.assertRaises(sqlite3.IntegrityError):
            cursor.execute(
                "INSERT INTO order_item (order_id, product_id, quantity, unit_price) VALUES (1, 2, 1, -50);"
            )

        # 測試 3: order_item 重複插入相同 (order_id, product_id) 應觸發複合主鍵衝突
        with self.assertRaises(sqlite3.IntegrityError):
            # 訂單 1 已存在商品 1
            cursor.execute(
                "INSERT INTO order_item (order_id, product_id, quantity, unit_price) VALUES (1, 1, 3, 45900);"
            )

        conn.close()


if __name__ == "__main__":
    unittest.main()
