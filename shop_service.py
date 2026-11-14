"""Бізнес-логіка магазину: оформлення замовлення, зміна статусу, дані для аналітики.

Не залежить від інтерфейсу (консоль / Tkinter) — обидва викликають ці функції.
"""
import logging

from analytics import SalesAnalytics
from classes import (Customer, Order, OrderItem, OrderStatus, OutOfStockError,
                     ValidationError)
from storage import OrderExistsError, StorageError

log = logging.getLogger(__name__)

MAX_ID_RETRIES = 5


def place_order(storage, cart, name, email):
    """Оформлює замовлення з кошика.

    Порядок дій гарантує узгодженість файлів:
      1. перевірка даних клієнта і кошика (нічого не записано);
      2. перечитування каталогу та перевірка залишків (дані могли змінитись);
      3. запис файлу замовлення;
      4. списання зі складу + запис каталогу; якщо запис каталогу не вдався —
         файл замовлення видаляється (відкат).
    Кошик очищується лише після успіху.
    """
    if cart.is_empty:
        raise ValidationError("Кошик порожній — додайте хоча б один товар")
    customer = Customer(name, email)

    catalog = storage.load_catalog()
    by_id = {p.product_id: p for p in catalog}

    items = []
    for product_id, quantity in cart.quantities.items():
        product = by_id.get(product_id)
        if product is None:
            raise ValidationError(f"Товару з ID {product_id} більше немає в каталозі")
        if product.stock < quantity:
            raise OutOfStockError(
                f"Недостатньо «{product.name}» на складі: потрібно {quantity}, є {product.stock}")
        items.append(OrderItem.from_product(product, quantity))

    order = _create_order_file(storage, customer, items)

    try:
        for item in items:
            product = by_id[item.product_id]
            product.stock -= item.quantity
            product.popularity += item.quantity
        storage.save_catalog(catalog)
    except StorageError:
        log.error("Відкат: видаляю замовлення #%d, бо каталог не збережено", order.order_id)
        storage.delete_order(order.order_id)
        raise

    cart.clear()
    return order


def _create_order_file(storage, customer, items):
    for _ in range(MAX_ID_RETRIES):
        order = Order(storage.next_order_id(), customer, items)
        try:
            storage.create_order(order)
            return order
        except OrderExistsError:
            continue  # хтось інший встиг зайняти цей номер — беремо наступний
    raise StorageError("Не вдалося підібрати вільний номер замовлення")


def change_order_status(storage, order_id, new_status):
    """Змінює статус замовлення. При скасуванні повертає товари на склад."""
    order = storage.load_order(order_id)
    previous = order.status
    order.set_status(new_status)  # InvalidStatusError, якщо перехід заборонений

    storage.update_order(order)
    if order.status is OrderStatus.CANCELLED:
        try:
            _restore_stock(storage, order)
        except StorageError:
            order.status = previous  # відкат статусу, щоб склад і замовлення не розійшлись
            storage.update_order(order)
            raise
    return order


def _restore_stock(storage, order):
    catalog = storage.load_catalog()
    by_id = {p.product_id: p for p in catalog}
    for item in order.items:
        product = by_id.get(item.product_id)
        if product is None:
            log.warning("Товар %d видалено з каталогу — склад не відновлено", item.product_id)
            continue
        product.stock += item.quantity
        product.popularity = max(0, product.popularity - item.quantity)
    storage.save_catalog(catalog)


def active_order_records(storage):
    """Генератор: замовлення у вигляді словників для аналітики.

    Скасовані замовлення пропускаються, щоб вони не завищували виручку.
    """
    for order in storage.iter_orders():
        if order.status is not OrderStatus.CANCELLED:
            yield order.to_dict()


def sales_analytics(storage):
    return SalesAnalytics(active_order_records(storage))
