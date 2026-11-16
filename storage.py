import functools
import json
import logging
import os
import re

from classes import Order, Product, ShopError, ValidationError

log = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CATALOG_PATH = os.path.join(BASE_DIR, "catalog", "catalog.json")
ORDERS_DIR = os.path.join(BASE_DIR, "saved_orders")

ORDER_FILE_RE = re.compile(r"^order(\d+)\.json$")


class StorageError(ShopError):
    """Не вдалося прочитати або записати дані."""


class OrderNotFoundError(StorageError):
    pass


class OrderExistsError(StorageError):
    pass


def safe_io(operation):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except ShopError:
                raise
            except (OSError, ValueError) as exc:  # json.JSONDecodeError — теж ValueError
                log.error("%s: %s", operation, exc)
                raise StorageError(f"{operation}: {exc}") from exc
        return wrapper
    return decorator


def _atomic_write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


class Storage:
    def __init__(self, catalog_path=CATALOG_PATH, orders_dir=ORDERS_DIR):
        self.catalog_path = catalog_path
        self.orders_dir = orders_dir

    @safe_io("Не вдалося прочитати каталог")
    def load_catalog(self):
        if not os.path.exists(self.catalog_path):
            raise StorageError(f"Файл каталогу не знайдено: {self.catalog_path}")
        with open(self.catalog_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, list):
            raise StorageError("Каталог має бути списком товарів")

        products, seen = [], set()
        for index, entry in enumerate(raw, start=1):
            try:
                product = Product.from_dict(entry)
            except ValidationError as exc:
                log.warning("Товар №%d пропущено: %s", index, exc)
                continue
            if product.product_id in seen:
                log.warning("Товар №%d пропущено: дубль ID %d", index, product.product_id)
                continue
            seen.add(product.product_id)
            products.append(product)
        return products

    @safe_io("Не вдалося зберегти каталог")
    def save_catalog(self, products):
        _atomic_write_json(self.catalog_path, [p.to_dict() for p in products])

    def _order_path(self, order_id):
        return os.path.join(self.orders_dir, f"order{order_id}.json")

    def _order_ids(self):
        if not os.path.isdir(self.orders_dir):
            return []
        ids = []
        for name in os.listdir(self.orders_dir):
            match = ORDER_FILE_RE.match(name)
            if match:
                ids.append(int(match.group(1)))
        return sorted(ids)

    def next_order_id(self):
        ids = self._order_ids()
        return (ids[-1] + 1) if ids else 1

    @safe_io("Не вдалося прочитати замовлення")
    def _read_order(self, order_id):
        path = self._order_path(order_id)
        if not os.path.exists(path):
            raise OrderNotFoundError(f"Замовлення #{order_id} не знайдено")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        order = Order.from_dict(data)
        if order.order_id != order_id:
            raise ValidationError(
                f"Номер у файлі ({order.order_id}) не збігається з назвою файлу (order{order_id}.json)")
        return order

    def load_order(self, order_id):
        return self._read_order(order_id)

    def iter_orders(self):
        for order_id in self._order_ids():
            try:
                order = self._read_order(order_id)
            except ShopError as exc:
                log.warning("Файл order%d.json пропущено: %s", order_id, exc)
                continue
            yield order

    @safe_io("Не вдалося зберегти замовлення")
    def create_order(self, order):
        os.makedirs(self.orders_dir, exist_ok=True)
        path = self._order_path(order.order_id)
        try:
            with open(path, "x", encoding="utf-8") as f:
                json.dump(order.to_dict(), f, ensure_ascii=False, indent=4)
        except FileExistsError:
            raise OrderExistsError(f"Замовлення #{order.order_id} уже існує") from None
        except BaseException:
            if os.path.exists(path):  # не залишаємо напівзаписаний файл
                os.remove(path)
            raise

    @safe_io("Не вдалося оновити замовлення")
    def update_order(self, order):
        if not os.path.exists(self._order_path(order.order_id)):
            raise OrderNotFoundError(f"Замовлення #{order.order_id} не знайдено")
        _atomic_write_json(self._order_path(order.order_id), order.to_dict())

    def delete_order(self, order_id):
        try:
            os.remove(self._order_path(order_id))
        except FileNotFoundError:
            pass
        except OSError as exc:
            log.error("Не вдалося видалити замовлення #%d: %s", order_id, exc)
