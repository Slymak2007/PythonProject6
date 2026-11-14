"""Тести оформлення замовлення: Cart, Customer, place_order та поведінка при збоях.

Запуск із кореня проєкту:   python -m unittest -v
"""
import os
from datetime import date
from unittest import mock

from classes import Cart, Customer, Order, OrderItem, OrderStatus, OutOfStockError, ValidationError
from shop_service import MAX_ID_RETRIES, active_order_records, change_order_status, \
    place_order, sales_analytics
from storage import OrderExistsError, StorageError
from tests.base import EBOOK, EMAIL, LAPTOP, NAME, PHONE, ShopTestCase


# =====================================================================
#  Кошик
# =====================================================================
class CartTests(ShopTestCase):
    def test_add_accumulates_quantity(self):
        cart, phone = Cart(), self.product(PHONE)
        cart.add(phone, 2)
        cart.add(phone, 1)
        self.assertEqual(cart.quantity_of(PHONE), 3)
        self.assertEqual(cart.count, 3)
        self.assertFalse(cart.is_empty)

    def test_add_out_of_stock_product_is_rejected(self):
        cart = Cart()
        with self.assertRaisesRegex(OutOfStockError, "немає в наявності"):
            cart.add(self.product(LAPTOP))
        self.assertTrue(cart.is_empty)

    def test_add_more_than_stock_is_rejected(self):
        cart = Cart()
        with self.assertRaises(OutOfStockError) as ctx:
            cart.add(self.product(PHONE), 6)  # на складі 5
        self.assertIn("5", str(ctx.exception))
        self.assertTrue(cart.is_empty)

    def test_add_exactly_stock_is_allowed(self):
        cart = Cart()
        cart.add(self.product(PHONE), 5)
        self.assertEqual(cart.quantity_of(PHONE), 5)

    def test_failed_add_keeps_previous_quantity(self):
        cart, phone = Cart(), self.product(PHONE)
        cart.add(phone, 3)
        with self.assertRaises(OutOfStockError):
            cart.add(phone, 3)  # разом 6 > 5
        self.assertEqual(cart.quantity_of(PHONE), 3)

    def test_invalid_quantity_is_rejected(self):
        phone = self.product(PHONE)
        for bad in (0, -1, "abc", "3", None, 1.5, True):
            with self.subTest(quantity=bad):
                cart = Cart()
                with self.assertRaises(ValidationError):
                    cart.add(phone, bad)
                self.assertTrue(cart.is_empty)

    def test_set_quantity_replaces_not_adds(self):
        cart, phone = Cart(), self.product(PHONE)
        cart.add(phone, 2)
        cart.set_quantity(phone, 4)
        self.assertEqual(cart.quantity_of(PHONE), 4)

    def test_set_quantity_zero_removes_line(self):
        cart, phone = Cart(), self.product(PHONE)
        cart.add(phone, 2)
        cart.set_quantity(phone, 0)
        self.assertTrue(cart.is_empty)

    def test_set_quantity_above_stock_is_rejected(self):
        cart, phone = Cart(), self.product(PHONE)
        cart.add(phone, 2)
        with self.assertRaises(OutOfStockError):
            cart.set_quantity(phone, 6)
        self.assertEqual(cart.quantity_of(PHONE), 2)

    def test_set_negative_quantity_is_rejected(self):
        cart, phone = Cart(), self.product(PHONE)
        cart.add(phone, 2)
        with self.assertRaises(ValidationError):
            cart.set_quantity(phone, -1)
        self.assertEqual(cart.quantity_of(PHONE), 2)

    def test_total_includes_shipping_of_physical_products_only(self):
        cart = self.make_cart({PHONE: 2, EBOOK: 1})
        # 2 × (20000 + 25 доставка) + 300 (цифровий товар без доставки)
        self.assertAlmostEqual(cart.total, 40350.0)

    def test_quantities_mapping(self):
        cart = self.make_cart({PHONE: 2, EBOOK: 1})
        self.assertEqual(cart.quantities, {PHONE: 2, EBOOK: 1})

    def test_remove_and_clear(self):
        cart = self.make_cart({PHONE: 2, EBOOK: 1})
        cart.remove(PHONE)
        cart.remove(999)  # неіснуючий товар — не помилка
        self.assertEqual(cart.quantities, {EBOOK: 1})
        cart.clear()
        self.assertTrue(cart.is_empty)

    def test_cart_never_changes_stock(self):
        before = self.catalog_bytes()
        self.make_cart({PHONE: 5, EBOOK: 8})
        self.assertEqual(self.catalog_bytes(), before)
        self.assertEqual(self.stock(PHONE), 5)


# =====================================================================
#  Дані клієнта
# =====================================================================
class CustomerTests(ShopTestCase):
    def test_valid_customer_is_trimmed(self):
        customer = Customer("  Іван Петренко  ", " ivan@example.com ")
        self.assertEqual(customer.name, "Іван Петренко")
        self.assertEqual(customer.email, "ivan@example.com")

    def test_invalid_names_are_rejected(self):
        for bad in ("", "   ", "І", None, 123):
            with self.subTest(name=bad):
                with self.assertRaises(ValidationError):
                    Customer(bad, EMAIL)

    def test_invalid_emails_are_rejected(self):
        for bad in ("", "bad", "a@b", "@b.ua", "a b@c.ua", "a@b@c.ua", None):
            with self.subTest(email=bad):
                with self.assertRaises(ValidationError):
                    Customer(NAME, bad)


# =====================================================================
#  Успішне оформлення
# =====================================================================
class PlaceOrderSuccessTests(ShopTestCase):
    def test_returns_new_order_with_expected_data(self):
        cart = self.make_cart({PHONE: 2, EBOOK: 1})
        order = place_order(self.storage, cart, NAME, EMAIL)

        self.assertIsInstance(order, Order)
        self.assertEqual(order.order_id, 1)
        self.assertEqual(order.status, OrderStatus.NEW)
        self.assertEqual(order.created, date.today().isoformat())
        self.assertEqual(order.customer.name, NAME)
        self.assertEqual(order.customer.email, EMAIL)
        self.assertEqual(len(order.items), 2)

    def test_totals_are_split_into_goods_and_shipping(self):
        order = place_order(self.storage, self.make_cart({PHONE: 2, EBOOK: 1}), NAME, EMAIL)
        self.assertAlmostEqual(order.goods_total, 40300.0)
        self.assertAlmostEqual(order.shipping_total, 50.0)
        self.assertAlmostEqual(order.total, 40350.0)

    def test_order_total_equals_cart_total(self):
        cart = self.make_cart({PHONE: 3, EBOOK: 2})
        expected = cart.total
        order = place_order(self.storage, cart, NAME, EMAIL)
        self.assertAlmostEqual(order.total, expected)

    def test_order_file_has_agreed_schema(self):
        place_order(self.storage, self.make_cart({PHONE: 2, EBOOK: 1}), NAME, EMAIL)
        data = self.read_order_json(1)

        self.assertEqual(data["order_id"], 1)
        self.assertEqual(data["customer_name"], NAME)
        self.assertEqual(data["customer_email"], EMAIL)
        self.assertEqual(data["date"], date.today().isoformat())
        self.assertEqual(data["status"], "New")
        self.assertEqual(data["items"], [
            {"id": PHONE, "title": "Phone", "price": 20000.0, "quantity": 2, "shipping": 25.0},
            {"id": EBOOK, "title": "Ebook", "price": 300.0, "quantity": 1, "shipping": 0.0},
        ])

    def test_saved_order_can_be_loaded_back(self):
        order = place_order(self.storage, self.make_cart({PHONE: 2}), NAME, EMAIL)
        loaded = self.storage.load_order(order.order_id)
        self.assertEqual(loaded.to_dict(), order.to_dict())

    def test_stock_decreases_and_popularity_grows(self):
        place_order(self.storage, self.make_cart({PHONE: 2, EBOOK: 3}), NAME, EMAIL)
        self.assertEqual(self.stock(PHONE), 3)
        self.assertEqual(self.stock(EBOOK), 5)
        self.assertEqual(self.popularity(PHONE), 2)
        self.assertEqual(self.popularity(EBOOK), 5)  # було 2 + 3

    def test_untouched_products_keep_their_stock(self):
        place_order(self.storage, self.make_cart({PHONE: 1}), NAME, EMAIL)
        self.assertEqual(self.stock(EBOOK), 8)
        self.assertEqual(self.stock(LAPTOP), 0)

    def test_buying_entire_stock_is_allowed(self):
        place_order(self.storage, self.make_cart({PHONE: 5}), NAME, EMAIL)
        self.assertEqual(self.stock(PHONE), 0)

    def test_cart_is_cleared_after_success(self):
        cart = self.make_cart({PHONE: 1})
        place_order(self.storage, cart, NAME, EMAIL)
        self.assertTrue(cart.is_empty)

    def test_customer_data_is_trimmed_in_saved_order(self):
        order = place_order(self.storage, self.make_cart({PHONE: 1}),
                            "  Оля Іваненко ", " olya@example.com ")
        self.assertEqual(self.read_order_json(order.order_id)["customer_name"], "Оля Іваненко")
        self.assertEqual(self.read_order_json(order.order_id)["customer_email"], "olya@example.com")

    def test_order_ids_increase(self):
        first = place_order(self.storage, self.make_cart({PHONE: 1}), NAME, EMAIL)
        second = place_order(self.storage, self.make_cart({PHONE: 1}), NAME, EMAIL)
        self.assertEqual((first.order_id, second.order_id), (1, 2))
        self.assertEqual(self.order_files(), ["order1.json", "order2.json"])

    def test_deleting_old_order_does_not_cause_id_reuse(self):
        place_order(self.storage, self.make_cart({PHONE: 1}), NAME, EMAIL)  # №1
        place_order(self.storage, self.make_cart({PHONE: 1}), NAME, EMAIL)  # №2
        self.storage.delete_order(1)
        third = place_order(self.storage, self.make_cart({PHONE: 1}), NAME, EMAIL)
        self.assertEqual(third.order_id, 3)

    def test_price_is_a_snapshot_and_survives_catalog_change(self):
        order = place_order(self.storage, self.make_cart({PHONE: 1}), NAME, EMAIL)
        catalog = self.storage.load_catalog()
        for p in catalog:
            p.base_price = 99999.0
        self.storage.save_catalog(catalog)
        self.assertEqual(self.storage.load_order(order.order_id).items[0].unit_price, 20000.0)

    def test_no_temporary_files_left_behind(self):
        place_order(self.storage, self.make_cart({PHONE: 1}), NAME, EMAIL)
        self.assertEqual(os.listdir(os.path.dirname(self.catalog_path)), ["catalog.json"])
        self.assertEqual(self.order_files(), ["order1.json"])


# =====================================================================
#  Помилки валідації: нічого не записується, кошик зберігається
# =====================================================================
class PlaceOrderValidationTests(ShopTestCase):
    def assert_nothing_changed(self, before_catalog, cart, expected_quantities):
        self.assertEqual(self.order_files(), [])
        self.assertEqual(self.catalog_bytes(), before_catalog)
        self.assertEqual(cart.quantities, expected_quantities)  # кошик не очищено

    def test_empty_cart_is_rejected(self):
        before = self.catalog_bytes()
        with self.assertRaisesRegex(ValidationError, "Кошик порожній"):
            place_order(self.storage, Cart(), NAME, EMAIL)
        self.assertEqual(self.order_files(), [])
        self.assertEqual(self.catalog_bytes(), before)

    def test_invalid_name_is_rejected(self):
        for bad in ("", "  ", "І", None):
            with self.subTest(name=bad):
                cart, before = self.make_cart({PHONE: 2}), self.catalog_bytes()
                with self.assertRaises(ValidationError):
                    place_order(self.storage, cart, bad, EMAIL)
                self.assert_nothing_changed(before, cart, {PHONE: 2})

    def test_invalid_email_is_rejected(self):
        for bad in ("", "bad", "a@b", "a b@c.ua", None):
            with self.subTest(email=bad):
                cart, before = self.make_cart({PHONE: 2}), self.catalog_bytes()
                with self.assertRaises(ValidationError):
                    place_order(self.storage, cart, NAME, bad)
                self.assert_nothing_changed(before, cart, {PHONE: 2})

    def test_failed_attempt_does_not_consume_order_number(self):
        cart = self.make_cart({PHONE: 1})
        with self.assertRaises(ValidationError):
            place_order(self.storage, cart, NAME, "bad")
        order = place_order(self.storage, cart, NAME, EMAIL)  # той самий кошик, виправлений email
        self.assertEqual(order.order_id, 1)


# =====================================================================
#  Нестача товару: перевірка залишків під час оформлення
# =====================================================================
class PlaceOrderStockTests(ShopTestCase):
    def test_stock_taken_by_another_order_is_detected(self):
        cart = self.make_cart({PHONE: 3})                      # на момент додавання було 5
        place_order(self.storage, self.make_cart({PHONE: 4}), "Оля", EMAIL)  # лишилась 1 шт.
        before = self.catalog_bytes()

        with self.assertRaises(OutOfStockError) as ctx:
            place_order(self.storage, cart, NAME, EMAIL)

        self.assertIn("Phone", str(ctx.exception))
        self.assertEqual(self.stock(PHONE), 1)
        self.assertEqual(self.order_files(), ["order1.json"])
        self.assertEqual(self.catalog_bytes(), before)
        self.assertEqual(cart.quantities, {PHONE: 3})          # кошик збережено

    def test_all_or_nothing_when_one_line_is_unavailable(self):
        cart = self.make_cart({PHONE: 1, EBOOK: 5})
        place_order(self.storage, self.make_cart({EBOOK: 8}), "Оля", EMAIL)  # Ebook розібрали
        before = self.catalog_bytes()

        with self.assertRaises(OutOfStockError):
            place_order(self.storage, cart, NAME, EMAIL)

        self.assertEqual(self.stock(PHONE), 5)                 # Phone теж не списано
        self.assertEqual(self.order_files(), ["order1.json"])
        self.assertEqual(self.catalog_bytes(), before)

    def test_last_unit_goes_to_first_buyer_only(self):
        self.set_stock(PHONE, 1)
        first, second = self.make_cart({PHONE: 1}), self.make_cart({PHONE: 1})

        place_order(self.storage, first, NAME, EMAIL)
        with self.assertRaises(OutOfStockError):
            place_order(self.storage, second, "Оля", EMAIL)

        self.assertEqual(self.stock(PHONE), 0)                 # не стало від'ємним
        self.assertEqual(self.order_files(), ["order1.json"])

    def test_product_removed_from_catalog_is_rejected(self):
        cart = self.make_cart({PHONE: 1, EBOOK: 1})
        self.storage.save_catalog([p for p in self.storage.load_catalog()
                                   if p.product_id != PHONE])
        before = self.catalog_bytes()

        with self.assertRaises(ValidationError):
            place_order(self.storage, cart, NAME, EMAIL)

        self.assertEqual(self.order_files(), [])
        self.assertEqual(self.catalog_bytes(), before)


# =====================================================================
#  Збої сховища: відкат і узгодженість
# =====================================================================
class PlaceOrderStorageFailureTests(ShopTestCase):
    def test_missing_catalog_file(self):
        cart = self.make_cart({PHONE: 1})
        os.remove(self.catalog_path)
        with self.assertRaises(StorageError):
            place_order(self.storage, cart, NAME, EMAIL)
        self.assertEqual(self.order_files(), [])
        self.assertEqual(cart.quantities, {PHONE: 1})

    def test_corrupted_catalog_file(self):
        cart = self.make_cart({PHONE: 1})
        with open(self.catalog_path, "w", encoding="utf-8") as f:
            f.write("[ це не json")
        with self.assertRaises(StorageError):
            place_order(self.storage, cart, NAME, EMAIL)
        self.assertEqual(self.order_files(), [])

    def test_catalog_save_failure_rolls_back_order_file(self):
        cart = self.make_cart({PHONE: 2})
        before = self.catalog_bytes()

        with mock.patch.object(self.storage, "save_catalog",
                               side_effect=StorageError("диск повний")):
            with self.assertRaises(StorageError):
                place_order(self.storage, cart, NAME, EMAIL)

        self.assertEqual(self.order_files(), [])               # файл замовлення видалено
        self.assertEqual(self.catalog_bytes(), before)         # склад не змінено
        self.assertEqual(cart.quantities, {PHONE: 2})          # кошик не очищено
        # після відкату сховище працездатне, і номер 1 знову вільний
        self.assertEqual(place_order(self.storage, cart, NAME, EMAIL).order_id, 1)

    def test_order_file_creation_failure_leaves_stock_untouched(self):
        cart = self.make_cart({PHONE: 2})
        before = self.catalog_bytes()
        with mock.patch.object(self.storage, "create_order",
                               side_effect=StorageError("немає прав")):
            with self.assertRaises(StorageError):
                place_order(self.storage, cart, NAME, EMAIL)
        self.assertEqual(self.catalog_bytes(), before)
        self.assertEqual(cart.quantities, {PHONE: 2})

    def test_write_error_mid_order_leaves_no_partial_file(self):
        cart = self.make_cart({PHONE: 2})
        before = self.catalog_bytes()
        with mock.patch("storage.json.dump", side_effect=OSError("збій диска")):
            with self.assertRaises(StorageError):
                place_order(self.storage, cart, NAME, EMAIL)
        self.assertEqual(self.order_files(), [])               # напівзаписаного файлу немає
        self.assertEqual(self.catalog_bytes(), before)

    def test_id_collision_is_retried_with_next_number(self):
        place_order(self.storage, self.make_cart({PHONE: 1}), NAME, EMAIL)  # order1.json
        order1_before = self.order_bytes(1)

        # «хтось інший» встиг зайняти номер 1: перша спроба дає колізію, друга — вільний №2
        with mock.patch.object(self.storage, "next_order_id", side_effect=[1, 2]):
            order = place_order(self.storage, self.make_cart({PHONE: 1}), "Оля", EMAIL)

        self.assertEqual(order.order_id, 2)
        self.assertEqual(self.order_bytes(1), order1_before)   # чуже замовлення не перезаписано
        self.assertEqual(self.order_files(), ["order1.json", "order2.json"])

    def test_gives_up_after_max_id_retries(self):
        place_order(self.storage, self.make_cart({PHONE: 1}), NAME, EMAIL)
        order1_before, stock_before = self.order_bytes(1), self.stock(PHONE)
        cart = self.make_cart({PHONE: 1})

        with mock.patch.object(self.storage, "next_order_id", return_value=1) as next_id:
            with self.assertRaises(StorageError):
                place_order(self.storage, cart, "Оля", EMAIL)

        self.assertEqual(next_id.call_count, MAX_ID_RETRIES)
        self.assertEqual(self.order_bytes(1), order1_before)
        self.assertEqual(self.stock(PHONE), stock_before)
        self.assertEqual(cart.quantities, {PHONE: 1})

    def test_corrupted_order_file_still_occupies_its_number(self):
        self.write_raw_order_file("order7.json", "{ зламаний")
        order = place_order(self.storage, self.make_cart({PHONE: 1}), NAME, EMAIL)
        self.assertEqual(order.order_id, 8)
        self.assertEqual(self.order_bytes(7), "{ зламаний".encode("utf-8"))

    def test_foreign_files_do_not_affect_numbering(self):
        for filename in ("order1", "notes.json", ".gitkeep", "order2.json.tmp"):
            self.write_raw_order_file(filename, "x")
        order = place_order(self.storage, self.make_cart({PHONE: 1}), NAME, EMAIL)
        self.assertEqual(order.order_id, 1)


# =====================================================================
#  Гарантії шару збереження, на які спирається оформлення
# =====================================================================
class StorageGuaranteeTests(ShopTestCase):
    def test_failed_catalog_write_keeps_original_and_no_tmp_file(self):
        before = self.catalog_bytes()
        products = self.storage.load_catalog()
        with mock.patch("storage.os.replace", side_effect=OSError("збій")):
            with self.assertRaises(StorageError):
                self.storage.save_catalog(products)
        self.assertEqual(self.catalog_bytes(), before)
        self.assertEqual(os.listdir(os.path.dirname(self.catalog_path)), ["catalog.json"])

    def test_create_order_never_overwrites_existing_file(self):
        place_order(self.storage, self.make_cart({PHONE: 1}), NAME, EMAIL)
        before = self.order_bytes(1)
        duplicate = Order(1, Customer("Тест", "t@t.ua"), [OrderItem(PHONE, "Phone", 1, 1)])
        with self.assertRaises(OrderExistsError):
            self.storage.create_order(duplicate)
        self.assertEqual(self.order_bytes(1), before)

    def test_catalog_skips_invalid_and_duplicate_entries(self):
        with open(self.catalog_path, "w", encoding="utf-8") as f:
            f.write('[{"product_id": 1, "name": "A", "base_price": 10, "type": "digital", "stock": 1},'
                    ' {"product_id": 1, "name": "дубль", "base_price": 10, "type": "digital"},'
                    ' {"product_id": 2, "name": "", "base_price": 10, "type": "digital"},'
                    ' {"product_id": 3, "name": "B", "base_price": -5, "type": "digital"},'
                    ' {"product_id": 4, "name": "C", "base_price": 5, "type": "toy"},'
                    ' {"name": "D"}, 5]')
        with self.assertLogs("storage", level="WARNING") as logs:
            products = self.storage.load_catalog()
        self.assertEqual([p.name for p in products], ["A"])
        self.assertEqual(len(logs.records), 6)  # кожен пропущений запис залогований


# =====================================================================
#  Оформлене замовлення в аналітиці
# =====================================================================
class CheckoutAnalyticsTests(ShopTestCase):
    def test_analytics_revenue_counts_goods_without_shipping(self):
        order = place_order(self.storage, self.make_cart({PHONE: 2}), NAME, EMAIL)
        analytics = sales_analytics(self.storage)
        self.assertAlmostEqual(float(analytics.df["total_revenue"].sum()), 40000.0)
        self.assertAlmostEqual(order.total, 40050.0)           # у замовленні доставка є

    def test_cancelled_orders_are_excluded(self):
        place_order(self.storage, self.make_cart({PHONE: 2}), NAME, EMAIL)       # №1
        place_order(self.storage, self.make_cart({EBOOK: 1}), "Оля", EMAIL)      # №2
        change_order_status(self.storage, 1, "Cancelled")

        records = list(active_order_records(self.storage))
        self.assertEqual([r["order_id"] for r in records], [2])
        self.assertAlmostEqual(float(sales_analytics(self.storage).df["total_revenue"].sum()), 300.0)

    def test_analytics_on_empty_storage_does_not_crash(self):
        self.assertTrue(sales_analytics(self.storage).df.empty)
