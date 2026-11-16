import logging
import sys

from classes import ALLOWED_TRANSITIONS, Cart, ShopError
from shop_service import change_order_status, place_order, sales_analytics
from storage import Storage

MENU = """
========== ІНТЕРНЕТ-МАГАЗИН ==========
1. Каталог товарів
2. Додати товар у кошик
3. Показати кошик
4. Очистити кошик
5. Оформити замовлення
6. Список замовлень
7. Змінити статус замовлення
8. Аналітика продажів
0. Вихід"""


def ask_int(prompt, minimum=None, maximum=None):
    """Питає ціле число, доки користувач не введе коректне."""
    while True:
        raw = input(prompt).strip()
        try:
            value = int(raw)
        except ValueError:
            print("  Введіть ціле число.")
            continue
        if minimum is not None and value < minimum:
            print(f"  Число має бути не менше {minimum}.")
        elif maximum is not None and value > maximum:
            print(f"  Число має бути не більше {maximum}.")
        else:
            return value


def ask_text(prompt):
    return input(prompt).strip()


def show_catalog(storage):
    products = storage.load_catalog()
    if not products:
        print("Каталог порожній.")
        return products
    print(f"\n{'ID':<4}{'Назва':<24}{'Тип':<10}{'Ціна':>10}{'З доставкою':>14}{'Склад':>8}")
    for p in products:
        stock = p.stock if p.stock > 0 else "немає"
        print(f"{p.product_id:<4}{p.name:<24}{p.product_type:<10}{p.base_price:>10.2f}"
              f"{p.calculate_total_price():>14.2f}{stock:>8}")
    return products


def add_to_cart(storage, cart):
    products = show_catalog(storage)
    if not products:
        return
    by_id = {p.product_id: p for p in products}
    product_id = ask_int("\nID товару (0 — скасувати): ", minimum=0)
    if product_id == 0:
        return
    product = by_id.get(product_id)
    if product is None:
        print(f"Товару з ID {product_id} у каталозі немає.")
        return
    quantity = ask_int("Кількість: ", minimum=1)
    cart.add(product, quantity)  # OutOfStockError, якщо не вистачає
    print(f"✓ «{product.name}» × {quantity} додано в кошик")


def show_cart(cart):
    if cart.is_empty:
        print("Кошик порожній.")
        return
    print(f"\n{'Товар':<24}{'Ціна':>10}{'К-сть':>7}{'Сума':>12}")
    for product, qty in cart.lines():
        print(f"{product.name:<24}{product.calculate_total_price():>10.2f}{qty:>7}"
              f"{product.calculate_total_price() * qty:>12.2f}")
    print(f"Разом (з доставкою): {cart.total:.2f} грн")


def checkout(storage, cart):
    if cart.is_empty:
        print("Кошик порожній — спочатку додайте товари.")
        return
    show_cart(cart)
    name = ask_text("\nВаше ім'я: ")
    email = ask_text("Ваш email: ")
    order = place_order(storage, cart, name, email)
    print(f"\n✓ Замовлення #{order.order_id} оформлено. До сплати: {order.total:.2f} грн")


def list_orders(storage):
    orders = list(storage.iter_orders())
    if not orders:
        print("Замовлень ще немає.")
        return orders
    print()
    for order in orders:
        print(order)
    return orders


def change_status(storage):
    orders = list_orders(storage)
    if not orders:
        return
    order_id = ask_int("\nНомер замовлення (0 — скасувати): ", minimum=0)
    if order_id == 0:
        return
    order = storage.load_order(order_id)
    options = ALLOWED_TRANSITIONS[order.status]
    if not options:
        print(f"Замовлення #{order_id} має статус «{order.status.label}» — змінити його не можна.")
        return
    print(f"Поточний статус: {order.status.label}. Можна змінити на:")
    for i, status in enumerate(options, start=1):
        print(f"  {i}. {status.label}")
    choice = ask_int("Ваш вибір: ", minimum=1, maximum=len(options))
    updated = change_order_status(storage, order_id, options[choice - 1])
    print(f"✓ Замовлення #{order_id}: статус «{updated.status.label}»")


def show_analytics(storage):
    analytics = sales_analytics(storage)
    print("\n" + "=" * 50)
    print("      АНАЛІТИКА ПРОДАЖІВ (Pandas/NumPy)")
    print("      (скасовані замовлення не враховуються)")
    print("=" * 50)
    print("\n1. [ТОП НАЙПРИБУТКОВІШИХ ТОВАРІВ]:")
    print(analytics.get_top_profitable_products())
    print("\n2. [ДИНАМІКА ВИРУЧКИ ЗА ДНЯМИ]:")
    print(analytics.get_revenue_dynamics())
    print("\n3. [СЕГМЕНТАЦІЯ КЛІЄНТІВ]:")
    print(analytics.segment_customers())
    print("=" * 50)


def main():
    logging.basicConfig(level=logging.WARNING, format="[%(levelname)s] %(message)s")
    storage = Storage()
    cart = Cart()
    actions = {
        "1": lambda: show_catalog(storage),
        "2": lambda: add_to_cart(storage, cart),
        "3": lambda: show_cart(cart),
        "4": lambda: (cart.clear(), print("Кошик очищено.")),
        "5": lambda: checkout(storage, cart),
        "6": lambda: list_orders(storage),
        "7": lambda: change_status(storage),
        "8": lambda: show_analytics(storage),
    }
    while True:
        print(MENU)
        choice = ask_text("Оберіть пункт: ")
        if choice == "0":
            print("До побачення!")
            return
        action = actions.get(choice)
        if action is None:
            print("Невідомий пункт меню.")
            continue
        try:
            action()
        except ShopError as exc:
            print(f"✗ Помилка: {exc}")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nРоботу перервано.")
        sys.exit(0)
