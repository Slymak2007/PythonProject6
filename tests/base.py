import json
import os
import shutil
import tempfile
import unittest

from classes import Cart, DigitalProduct, PhysicalProduct
from storage import Storage

PHONE, LAPTOP, EBOOK = 1, 2, 3

NAME = "Іван Петренко"
EMAIL = "ivan@example.com"

class ShopTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="shop_test_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.catalog_path = os.path.join(self.tmp, "catalog", "catalog.json")
        self.orders_dir = os.path.join(self.tmp, "saved_orders")
        self.storage = Storage(self.catalog_path, self.orders_dir)
        self.storage.save_catalog([
            PhysicalProduct(PHONE, "Phone", 20000, weight_kg=0.5, shipping_rate=50.0,
                            stock=5, popularity=0),
            PhysicalProduct(LAPTOP, "Laptop", 25000, weight_kg=2.0, shipping_rate=50.0,
                            stock=0, popularity=0),
            DigitalProduct(EBOOK, "Ebook", 300, download_link="https://example.com/e.pdf",
                           stock=8, popularity=2),
        ])

    def product(self, product_id):
        return {p.product_id: p for p in self.storage.load_catalog()}[product_id]

    def stock(self, product_id):
        return self.product(product_id).stock

    def popularity(self, product_id):
        return self.product(product_id).popularity

    def set_stock(self, product_id, value):
        catalog = self.storage.load_catalog()
        for p in catalog:
            if p.product_id == product_id:
                p.stock = value
        self.storage.save_catalog(catalog)

    def make_cart(self, quantities):
        cart = Cart()
        for product_id, qty in quantities.items():
            cart.add(self.product(product_id), qty)
        return cart

    def catalog_bytes(self):
        with open(self.catalog_path, "rb") as f:
            return f.read()

    def order_files(self):
        if not os.path.isdir(self.orders_dir):
            return []
        return sorted(n for n in os.listdir(self.orders_dir) if n.startswith("order"))

    def order_bytes(self, order_id):
        with open(os.path.join(self.orders_dir, f"order{order_id}.json"), "rb") as f:
            return f.read()

    def read_order_json(self, order_id):
        with open(os.path.join(self.orders_dir, f"order{order_id}.json"), encoding="utf-8") as f:
            return json.load(f)

    def write_raw_order_file(self, filename, text):
        os.makedirs(self.orders_dir, exist_ok=True)
        with open(os.path.join(self.orders_dir, filename), "w", encoding="utf-8") as f:
            f.write(text)
