"""Тести статусів замовлення та скасування (повернення товарів на склад).

Запуск із кореня проєкту:   python -m unittest -v
"""
import json
import os
from unittest import mock

from classes import InvalidStatusError, OrderStatus
from shop_service import change_order_status, place_order
from storage import OrderNotFoundError, StorageError
from tests.base import EBOOK, EMAIL, NAME, PHONE, ShopTestCase


class OrderStatusTests(ShopTestCase):
    def setUp(self):
        super().setUp()
        # замовлення №1: 2 телефони (на складі лишається 3, популярність 2)
        self.order = place_order(self.storage, self.make_cart({PHONE: 2}), NAME, EMAIL)

    def file_status(self, order_id=1):
        return self.read_order_json(order_id)["status"]

    # ------------------------------------------------------------ переходи
    def test_new_order_starts_with_status_new(self):
        self.assertEqual(self.order.status, OrderStatus.NEW)
        self.assertEqual(self.file_status(), "New")

    def test_full_happy_path_is_persisted_at_each_step(self):
        for status in ("Paid", "Shipped", "Delivered"):
            with self.subTest(status=status):
                updated = change_order_status(self.storage, 1, status)
                self.assertEqual(updated.status.value, status)
                self.assertEqual(self.file_status(), status)

    def test_status_accepts_enum_value(self):
        change_order_status(self.storage, 1, OrderStatus.PAID)
        self.assertEqual(self.file_status(), "Paid")

    def test_forbidden_transition_is_rejected_and_file_unchanged(self):
        before = self.order_bytes(1)
        with self.assertRaises(InvalidStatusError):
            change_order_status(self.storage, 1, "Delivered")  # New → Delivered заборонено
        self.assertEqual(self.order_bytes(1), before)

    def test_unknown_status_is_rejected(self):
        # «Оплачене» — це лише підпис для показу, у програмі приймається значення «Paid»
        for bad in ("Foo", "", None, "paid", "Оплачене"):
            with self.subTest(status=bad):
                with self.assertRaises(InvalidStatusError):
                    change_order_status(self.storage, 1, bad)
        self.assertEqual(self.file_status(), "New")

    def test_same_status_is_not_a_transition(self):
        with self.assertRaises(InvalidStatusError):
            change_order_status(self.storage, 1, "New")

    def test_final_statuses_cannot_be_changed(self):
        for status in ("Paid", "Shipped", "Delivered"):
            change_order_status(self.storage, 1, status)
        for target in ("Cancelled", "Paid", "New"):
            with self.subTest(target=target):
                with self.assertRaises(InvalidStatusError):
                    change_order_status(self.storage, 1, target)
        self.assertEqual(self.file_status(), "Delivered")

    def test_nonexistent_order(self):
        with self.assertRaises(OrderNotFoundError):
            change_order_status(self.storage, 99, "Paid")
        self.assertIsInstance(OrderNotFoundError("x"), StorageError)

    # ------------------------------------------------------------ скасування
    def test_cancel_returns_stock_and_popularity(self):
        self.assertEqual((self.stock(PHONE), self.popularity(PHONE)), (3, 2))
        change_order_status(self.storage, 1, "Cancelled")
        self.assertEqual((self.stock(PHONE), self.popularity(PHONE)), (5, 0))
        self.assertEqual(self.file_status(), "Cancelled")

    def test_cancel_after_payment_also_returns_stock(self):
        change_order_status(self.storage, 1, "Paid")
        change_order_status(self.storage, 1, "Cancelled")
        self.assertEqual(self.stock(PHONE), 5)

    def test_cancel_twice_does_not_restore_stock_twice(self):
        change_order_status(self.storage, 1, "Cancelled")
        with self.assertRaises(InvalidStatusError):
            change_order_status(self.storage, 1, "Cancelled")
        self.assertEqual(self.stock(PHONE), 5)

    def test_cannot_cancel_shipped_order(self):
        change_order_status(self.storage, 1, "Paid")
        change_order_status(self.storage, 1, "Shipped")
        stock_before = self.stock(PHONE)
        with self.assertRaises(InvalidStatusError):
            change_order_status(self.storage, 1, "Cancelled")
        self.assertEqual(self.stock(PHONE), stock_before)

    def test_popularity_never_goes_below_zero(self):
        catalog = self.storage.load_catalog()
        for p in catalog:
            if p.product_id == PHONE:
                p.popularity = 0  # хтось скинув лічильник уручну
        self.storage.save_catalog(catalog)
        change_order_status(self.storage, 1, "Cancelled")
        self.assertEqual(self.popularity(PHONE), 0)

    def test_cancel_rolls_status_back_if_stock_cannot_be_restored(self):
        stock_before = self.stock(PHONE)
        with mock.patch.object(self.storage, "save_catalog",
                               side_effect=StorageError("диск повний")):
            with self.assertRaises(StorageError):
                change_order_status(self.storage, 1, "Cancelled")
        self.assertEqual(self.file_status(), "New")            # статус повернуто
        self.assertEqual(self.stock(PHONE), stock_before)      # склад не змінено

    def test_cancel_when_product_was_deleted_from_catalog(self):
        order2 = place_order(self.storage, self.make_cart({PHONE: 1, EBOOK: 2}), "Оля", EMAIL)
        ebook_stock = self.stock(EBOOK)
        self.storage.save_catalog([p for p in self.storage.load_catalog()
                                   if p.product_id != PHONE])

        with self.assertLogs("shop_service", level="WARNING"):
            change_order_status(self.storage, order2.order_id, "Cancelled")  # без винятку

        self.assertEqual(self.stock(EBOOK), ebook_stock + 2)   # решту товарів повернуто
        self.assertEqual(self.file_status(order2.order_id), "Cancelled")

    # ------------------------------------------------------------ пошкоджені файли
    def test_unknown_status_in_file_is_reported(self):
        data = self.read_order_json(1)
        data["status"] = "Weird"
        self.write_raw_order_file("order1.json", json.dumps(data, ensure_ascii=False))

        with self.assertRaises(InvalidStatusError):
            self.storage.load_order(1)
        with self.assertRaises(InvalidStatusError):
            change_order_status(self.storage, 1, "Paid")

    def test_order_with_unknown_status_is_skipped_in_listing(self):
        data = self.read_order_json(1)
        data["status"] = "Weird"
        self.write_raw_order_file("order1.json", json.dumps(data, ensure_ascii=False))
        place_order(self.storage, self.make_cart({EBOOK: 1}), "Оля", EMAIL)      # №2, справний

        with self.assertLogs("storage", level="WARNING"):
            orders = list(self.storage.iter_orders())
        self.assertEqual([o.order_id for o in orders], [2])

    def test_missing_status_in_file_means_new(self):
        data = self.read_order_json(1)
        del data["status"]
        self.write_raw_order_file("order1.json", json.dumps(data, ensure_ascii=False))
        self.assertEqual(self.storage.load_order(1).status, OrderStatus.NEW)

    def test_order_number_in_file_must_match_filename(self):
        data = self.read_order_json(1)
        data["order_id"] = 5
        self.write_raw_order_file("order1.json", json.dumps(data, ensure_ascii=False))
        with self.assertRaises(Exception) as ctx:
            self.storage.load_order(1)
        self.assertEqual(type(ctx.exception).__name__, "ValidationError")

    def test_legacy_order_without_items_is_skipped(self):
        legacy = '{"order_id": 9, "customer": "dima", "email": "@", "product_names": ["Laptop"], "price": 25000.0}'
        self.write_raw_order_file("order9.json", legacy)
        with self.assertLogs("storage", level="WARNING"):
            ids = [o.order_id for o in self.storage.iter_orders()]
        self.assertEqual(ids, [1])
        self.assertTrue(os.path.exists(os.path.join(self.orders_dir, "order9.json")))  # файл не видалено
