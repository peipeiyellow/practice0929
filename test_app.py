import unittest
from app import app


class AppTestCase(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.client = self.app.test_client()

    def test_hello_world_status_code(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

    def test_hello_world_content(self):
        response = self.client.get("/")
        self.assertIn("Hello World", response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
