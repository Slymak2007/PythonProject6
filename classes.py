"""Предметна область інтернет-магазину.

Структура (композиція):  Order  ─┬─ Customer
                                 └─ [OrderItem, ...]   (знімок товару на момент покупки)
Спадкування:  Product  ─┬─ PhysicalProduct  (є доставка: вага × тариф)
                        └─ DigitalProduct   (доставки немає, є посилання на завантаження)

Єдина схема даних (її читають і пишуть усі модулі):
  catalog.json : product_id, name, base_price, type, stock, popularity,
                 + weight_kg, shipping_rate (physical) або download_link (digital)
  orderN.json  : order_id, customer_name, customer_email, date, status,
                 items[ {id, title, price, quantity, shipping} ]
"""
import math
import re
from datetime import date
from enum import Enum

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---------------------------------------------------------------- помилки
class ShopError(Exception):
    """Базова помилка магазину: її можна безпечно показати користувачеві."""


class ValidationError(ShopError):
    """Некоректні дані (товар, клієнт, замовлення)."""


class OutOfStockError(ShopError):
    """Недостатньо товару на складі."""


class InvalidStatusError(ShopError):
    """Недопустимий статус або перехід між статусами замовлення."""


# ---------------------------------------------------------------- перевірки
def _require_text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"Поле «{field}» має бути непорожнім рядком")
    return value.strip()


def _require_int(value, field, minimum=0):
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(f"Поле «{field}» має бути цілим числом, отримано {value!r}")
    if value < minimum:
        raise ValidationError(f"Поле «{field}» не може бути меншим за {minimum}")
    return value


def _require_number(value, field, minimum=0.0):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValidationError(f"Поле «{field}» має бути числом, отримано {value!r}")
    if value < minimum:
        raise ValidationError(f"Поле «{field}» не може бути меншим за {minimum}")
    return float(value)


def _require_field(data, key):
    if key not in data:
        raise ValidationError(f"Відсутнє обов'язкове поле «{key}»")
    return data[key]


# ---------------------------------------------------------------- товари
class Product:
    """Базовий товар. Спільні поля та перевірки; доставку визначають нащадки."""

    product_type = None  # у нащадків: "physical" / "digital"

    def __init__(self, product_id, name, base_price, stock=0, popularity=0):
        self.product_id = _require_int(product_id, "product_id", 1)
        self.name = _require_text(name, "name")
        self.base_price = _require_number(base_price, "base_price")
        self.stock = _require_int(stock, "stock")
        self.popularity = _require_int(popularity, "popularity")

    def shipping_cost(self):
        """Вартість доставки одиниці товару. Перевизначається в нащадках."""
        return 0.0

    def calculate_total_price(self):
        """Ціна одиниці товару разом з доставкою."""
        return self.base_price + self.shipping_cost()

    def to_dict(self):
        return {
            "product_id": self.product_id,
            "name": self.name,
            "base_price": self.base_price,
            "type": self.product_type,
            "stock": self.stock,
            "popularity": self.popularity,
        }

    @staticmethod
    def from_dict(data):
        """Фабрика: за полем type створює потрібний клас товару."""
        if not isinstance(data, dict):
            raise ValidationError("Запис товару має бути об'єктом")
        ptype = _require_field(data, "type")
        cls = PRODUCT_TYPES.get(ptype)
        if cls is None:
            raise ValidationError(f"Невідомий тип товару: {ptype!r}")
        return cls._from_fields(data)

    @staticmethod
    def _common_fields(data):
        return dict(
            product_id=_require_field(data, "product_id"),
            name=_require_field(data, "name"),
            base_price=_require_field(data, "base_price"),
            stock=data.get("stock", 0),
            popularity=data.get("popularity", 0),
        )

    def __str__(self):
        return f"{self.name} (ID: {self.product_id})"


class PhysicalProduct(Product):
    product_type = "physical"

    def __init__(self, product_id, name, base_price, weight_kg, shipping_rate=50.0,
                 stock=0, popularity=0):
        super().__init__(product_id, name, base_price, stock, popularity)
        self.weight_kg = _require_number(weight_kg, "weight_kg")
        self.shipping_rate = _require_number(shipping_rate, "shipping_rate")

    def shipping_cost(self):
        # вага (кг) × тариф за кг
        return self.weight_kg * self.shipping_rate

    def to_dict(self):
        data = super().to_dict()
        data.update(weight_kg=self.weight_kg, shipping_rate=self.shipping_rate)
        return data

    @classmethod
    def _from_fields(cls, data):
        return cls(weight_kg=_require_field(data, "weight_kg"),
                   shipping_rate=data.get("shipping_rate", 50.0),
                   **cls._common_fields(data))


class DigitalProduct(Product):
    product_type = "digital"

    def __init__(self, product_id, name, base_price, download_link="", stock=0, popularity=0):
        super().__init__(product_id, name, base_price, stock, popularity)
        if not isinstance(download_link, str):
            raise ValidationError("Поле «download_link» має бути рядком")
        self.download_link = download_link.strip()

    # shipping_cost() не перевизначаємо: цифровий товар не доставляється (0 грн)

    def to_dict(self):
        data = super().to_dict()
        data["download_link"] = self.download_link
        return data

    @classmethod
    def _from_fields(cls, data):
        return cls(download_link=data.get("download_link", ""), **cls._common_fields(data))


PRODUCT_TYPES = {cls.product_type: cls for cls in (PhysicalProduct, DigitalProduct)}


# ---------------------------------------------------------------- клієнт
class Customer:
    def __init__(self, name, email):
        self.name = _require_text(name, "ім'я")
        if len(self.name) < 2:
            raise ValidationError("Ім'я має містити щонайменше 2 символи")
        self.email = _require_text(email, "email")
        if not EMAIL_RE.match(self.email):
            raise ValidationError("Некоректний email, приклад: name@example.com")

    def __str__(self):
        return f"Клієнт {self.name} ({self.email})"


# ---------------------------------------------------------------- замовлення
class OrderStatus(str, Enum):
    NEW = "New"
    PAID = "Paid"
    SHIPPED = "Shipped"
    DELIVERED = "Delivered"
    CANCELLED = "Cancelled"

    @classmethod
    def parse(cls, value):
        if isinstance(value, cls):
            return value
        try:
            return cls(value)
        except ValueError:
            allowed = ", ".join(s.value for s in cls)
            raise InvalidStatusError(f"Невідомий статус {value!r}. Допустимі: {allowed}") from None

    @property
    def label(self):
        return STATUS_LABELS[self]


STATUS_LABELS = {
    OrderStatus.NEW: "Нове",
    OrderStatus.PAID: "Оплачене",
    OrderStatus.SHIPPED: "Відправлене",
    OrderStatus.DELIVERED: "Доставлене",
    OrderStatus.CANCELLED: "Скасоване",
}

ALLOWED_TRANSITIONS = {
    OrderStatus.NEW: (OrderStatus.PAID, OrderStatus.CANCELLED),
    OrderStatus.PAID: (OrderStatus.SHIPPED, OrderStatus.CANCELLED),
    OrderStatus.SHIPPED: (OrderStatus.DELIVERED,),
    OrderStatus.DELIVERED: (),
    OrderStatus.CANCELLED: (),
}


class OrderItem:
    """Позиція замовлення — знімок товару: ціна не зміниться, якщо каталог оновлять."""

    def __init__(self, product_id, title, unit_price, quantity, shipping=0.0):
        self.product_id = _require_int(product_id, "id", 1)
        self.title = _require_text(title, "title")
        self.unit_price = _require_number(unit_price, "price")
        self.quantity = _require_int(quantity, "quantity", 1)
        self.shipping = _require_number(shipping, "shipping")

    @classmethod
    def from_product(cls, product, quantity):
        return cls(product.product_id, product.name, product.base_price, quantity,
                   product.shipping_cost())

    @property
    def goods_total(self):
        return self.unit_price * self.quantity

    @property
    def shipping_total(self):
        return self.shipping * self.quantity

    @property
    def total(self):
        return self.goods_total + self.shipping_total

    def to_dict(self):
        return {"id": self.product_id, "title": self.title, "price": self.unit_price,
                "quantity": self.quantity, "shipping": self.shipping}

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ValidationError("Позиція замовлення має бути об'єктом")
        return cls(_require_field(data, "id"), _require_field(data, "title"),
                   _require_field(data, "price"), _require_field(data, "quantity"),
                   data.get("shipping", 0.0))


class Order:
    def __init__(self, order_id, customer, items, status=OrderStatus.NEW, created=None):
        self.order_id = _require_int(order_id, "order_id", 1)
        if not isinstance(customer, Customer):
            raise ValidationError("Клієнт замовлення має бути об'єктом Customer")
        self.customer = customer
        items = list(items)
        if not items or not all(isinstance(i, OrderItem) for i in items):
            raise ValidationError("Замовлення має містити хоча б одну позицію")
        self.items = items
        self.status = OrderStatus.parse(status)
        if created is None:
            created = date.today().isoformat()
        try:
            date.fromisoformat(created)
        except (TypeError, ValueError):
            raise ValidationError(f"Некоректна дата замовлення: {created!r}") from None
        self.created = created

    @property
    def goods_total(self):
        return sum(i.goods_total for i in self.items)

    @property
    def shipping_total(self):
        return sum(i.shipping_total for i in self.items)

    @property
    def total(self):
        return self.goods_total + self.shipping_total

    def set_status(self, new_status):
        """Змінює статус, якщо перехід дозволений (New→Paid→Shipped→Delivered; скасування з New/Paid)."""
        new_status = OrderStatus.parse(new_status)
        if new_status not in ALLOWED_TRANSITIONS[self.status]:
            raise InvalidStatusError(
                f"Неможливо змінити статус «{self.status.label}» на «{new_status.label}»")
        self.status = new_status

    def to_dict(self):
        return {
            "order_id": self.order_id,
            "customer_name": self.customer.name,
            "customer_email": self.customer.email,
            "date": self.created,
            "status": self.status.value,
            "items": [i.to_dict() for i in self.items],
        }

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ValidationError("Замовлення має бути об'єктом")
        if "items" not in data:
            raise ValidationError("Застарілий формат замовлення (немає поля «items»)")
        raw_items = data["items"]
        if not isinstance(raw_items, list):
            raise ValidationError("Поле «items» має бути списком")
        return cls(
            order_id=_require_field(data, "order_id"),
            customer=Customer(_require_field(data, "customer_name"),
                              _require_field(data, "customer_email")),
            items=[OrderItem.from_dict(i) for i in raw_items],
            status=data.get("status", OrderStatus.NEW.value),
            created=data.get("date"),
        )

    def __repr__(self):
        return f"Order(id={self.order_id}, customer={self.customer.name!r}, status={self.status.value})"

    def __str__(self):
        units = sum(i.quantity for i in self.items)
        return (f"Замовлення #{self.order_id} | {self.created} | {self.customer.name} | "
                f"{units} шт. | {self.total:.2f} грн | {self.status.label}")


# ---------------------------------------------------------------- кошик
class Cart:
    """Кошик. Склад НЕ змінює — залишки списуються лише при оформленні замовлення."""

    def __init__(self):
        self._lines = {}  # product_id -> [Product, quantity]

    @staticmethod
    def _check_stock(product, wanted, in_cart=0):
        if product.stock <= 0:
            raise OutOfStockError(f"Товару «{product.name}» немає в наявності")
        if wanted > product.stock:
            in_cart_note = f" (у кошику вже {in_cart})" if in_cart else ""
            raise OutOfStockError(f"Доступно лише {product.stock} шт. «{product.name}»{in_cart_note}")

    def add(self, product, quantity=1):
        quantity = _require_int(quantity, "кількість", 1)
        current = self._lines[product.product_id][1] if product.product_id in self._lines else 0
        self._check_stock(product, current + quantity, current)
        self._lines[product.product_id] = [product, current + quantity]

    def set_quantity(self, product, quantity):
        quantity = _require_int(quantity, "кількість", 0)
        if quantity == 0:
            self.remove(product.product_id)
            return
        self._check_stock(product, quantity)
        self._lines[product.product_id] = [product, quantity]

    def remove(self, product_id):
        self._lines.pop(product_id, None)

    def clear(self):
        self._lines.clear()

    def lines(self):
        return [(p, q) for p, q in self._lines.values()]

    @property
    def quantities(self):
        return {pid: q for pid, (_, q) in self._lines.items()}

    def quantity_of(self, product_id):
        return self._lines[product_id][1] if product_id in self._lines else 0

    @property
    def is_empty(self):
        return not self._lines

    @property
    def count(self):
        return sum(q for _, q in self._lines.values())

    @property
    def total(self):
        return sum(p.calculate_total_price() * q for p, q in self._lines.values())
