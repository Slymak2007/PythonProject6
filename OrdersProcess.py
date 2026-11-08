import os
import json
import pandas as pd
import numpy as np
from typing import Generator, Dict, Any, Union
import datetime


def get_field(item: Any, *keys, default=None):
    if isinstance(item, dict):
        for k in keys:
            if k in item and item[k] is not None:
                return item[k]
        item_lower = {str(k).lower(): v for k, v in item.items()}
        for k in keys:
            k_low = str(k).lower()
            if k_low in item_lower and item_lower[k_low] is not None:
                return item_lower[k_low]
        for k, v in item.items():
            if any(term in str(k).lower() for term in ["price", "cost", "ціна", "val"]):
                if v is not None:
                    return v
    elif hasattr(item, '__dict__'):
        for k in keys:
            if hasattr(item, k):
                return getattr(item, k)
    return default


def placing():
    catalog_path = "catalog/catalog.json" if os.path.exists("catalog/catalog.json") else "catalog.json"
    if not os.path.exists(catalog_path):
        print("Помилка: Файл catalog.json не знайдено!")
        return []

    with open(catalog_path, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    cart = []
    print("\n--- СПИСОК ТОВАРІВ ---")
    for item in catalog:
        item_id = get_field(item, "id", "Id", "ID", "product_id")
        title = get_field(item, "title", "name", "Name", default="Товар")
        price = float(get_field(item, "price", "Price", "cost", default=0.0))
        print(f"ID: {item_id} | Назва: {title} | Ціна: {price}")

    while True:
        user_input = input("\nНапишіть ID товару для додавання (або '0' / Enter щоб завершити): ").strip()
        if user_input == "0" or user_input == "":
            break

        found = False
        for item in catalog:
            item_id = str(get_field(item, "id", "Id", "ID", "product_id"))
            if item_id == user_input:
                title = get_field(item, "title", "name", "Name", default="Товар")
                price = float(get_field(item, "price", "Price", "cost", default=0.0))
                if item["stock"] > 0:
                    if any(item['id'] == user_input for item in cart):
                        item["stock"] -= 1
                        cart[next((i for i, item in enumerate(cart) if item['id'] == user_input), None)][
                            'quantity'] += 1
                        item["popularity"] += 1
                    else:
                        cart.append({
                            "id": item_id,
                            "title": title,
                            "price": price,
                            "quantity": 1
                        })
                        item["stock"] -= 1
                        item["popularity"] += 1
                    print(f"✓ Товар '{title}' (ціна: {price}) додано до корзини!")
                    found = True
                    break
                else:
                    break

        if not found:
            print("Товар з таким ID не знайдено. Спробуйте ще раз.")
    with open(catalog_path, "r+", encoding="utf-8") as f:
        f.seek(0)
        json.dump(catalog, f, ensure_ascii=False, indent=4)
        f.truncate()
    return cart


def saving_order():
    name = input("Enter your name: ")
    email = input("Enter your email: ")

    cart = placing()
    if not cart:
        print("Корзина порожня. Замовлення не створено.")
        return

    os.makedirs("saved_orders", exist_ok=True)
    order_id = len([f for f in os.listdir("saved_orders") if f.endswith(".json")]) + 1

    order_data = {
        "order_id": order_id,
        "customer_name": name,
        "customer_email": email,
        "date": "2026-03-30",
        "items": cart
    }

    file_path = f"saved_orders/order{order_id}.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(order_data, f, ensure_ascii=False, indent=4)

    print(f"\n✓ Замовлення #{order_id} успішно збережено у '{file_path}'!")

    run_analytics_report()


def stream_order_logs(source: Union[str, list]) -> Generator[Dict[str, Any], None, None]:
    """Генератор для потокового читання замовлень."""
    if isinstance(source, list):
        yield from source
        return

    if os.path.isdir(source):
        for root, _, files in os.walk(source):
            for file in files:
                if file.endswith('.json'):
                    try:
                        with open(os.path.join(root, file), 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            yield from data if isinstance(data, list) else [data]
                    except Exception as e:
                        print(f"Помилка читання {file}: {e}")
    elif os.path.isfile(source):
        try:
            with open(source, 'r', encoding='utf-8') as f:
                data = json.load(f)
                yield from data if isinstance(data, list) else [data]
        except Exception as e:
            print(f"Помилка читання {source}: {e}")


class SalesAnalytics:
    """Аналіз продажів на Pandas та NumPy."""

    def __init__(self, orders_generator):
        raw_records = []
        for order in orders_generator:
            if not isinstance(order, dict):
                continue

            customer_raw = order.get("customer_name") or order.get("customer")
            if isinstance(customer_raw, dict):
                customer_name = customer_raw.get("name") or customer_raw.get("customer_name") or "Гість"
            elif isinstance(customer_raw, str):
                customer_name = customer_raw
            else:
                customer_name = "Гість"

            order_date = order.get("date") or order.get("created_at") or "2026-03-30"
            order_id = order.get("order_id") or order.get("id") or 1

            items = order.get("items") or order.get("products") or []
            if isinstance(items, dict):
                items = [items]

            for item in items:
                if not isinstance(item, dict):
                    continue

                p_id = get_field(item, "id", "Id", "product_id", default=1)
                p_name = get_field(item, "title", "name", "Name", default="Товар")
                p_price = float(get_field(item, "price", "Price", "cost", default=0.0))
                p_qty = int(get_field(item, "quantity", "qty", default=1))

                raw_records.append({
                    "order_id": order_id,
                    "customer_name": customer_name,
                    "order_date": order_date,
                    "product_id": p_id,
                    "product_name": p_name,
                    "quantity": p_qty,
                    "price": p_price,
                    "total_revenue": p_qty * p_price
                })

        self.df = pd.DataFrame(raw_records)
        if not self.df.empty and "order_date" in self.df.columns:
            self.df["order_date"] = pd.to_datetime(self.df["order_date"])

    def get_top_profitable_products(self, top_n=5):
        if self.df.empty:
            return "Немає даних для аналізу"
        return self.df.groupby(["product_id", "product_name"]).agg(
            total_sold=("quantity", "sum"),
            total_revenue=("total_revenue", "sum")
        ).reset_index().sort_values(by="total_revenue", ascending=False).head(top_n)

    def get_revenue_dynamics(self):
        if self.df.empty:
            return "Немає даних для аналізу"
        dynamics = self.df.groupby(pd.Grouper(key="order_date", freq="D")).agg(
            daily_revenue=("total_revenue", "sum"),
            order_count=("order_id", "nunique")
        ).reset_index()
        dynamics["avg_order_value"] = np.where(
            dynamics["order_count"] > 0,
            dynamics["daily_revenue"] / dynamics["order_count"],
            0.0
        )
        return dynamics

    def segment_customers(self):
        if self.df.empty:
            return "Немає даних для аналізу"
        spend = self.df.groupby("customer_name").agg(total_spent=("total_revenue", "sum")).reset_index()
        spends = spend["total_spent"].values
        q50 = np.quantile(spends, 0.5) if len(spends) > 0 else 0
        q85 = np.quantile(spends, 0.85) if len(spends) > 0 else 0

        conditions = [spend["total_spent"] >= q85, spend["total_spent"] >= q50]
        spend["segment"] = np.select(conditions, ["VIP", "Regular"], default="Low-value")
        return spend.sort_values(by="total_spent", ascending=False)


def run_analytics_report():
    print("\n" + "=" * 50)
    print("      НАПРЯМ 3: АНАЛІТИКА ПРОДАЖІВ (Pandas/NumPy)")
    print("=" * 50)

    analytics = SalesAnalytics(stream_order_logs("saved_orders"))

    print("\n1. [ТОП НАЙПРИБУТКОВІШИХ ТОВАРІВ]:")
    print(analytics.get_top_profitable_products())

    print("\n2. [ДИНАМІКА ВИРУЧКИ ЗА ДНЯМИ]:")
    print(analytics.get_revenue_dynamics())

    print("\n3. [СЕГМЕНТАЦІЯ КЛІЄНТІВ]:")
    print(analytics.segment_customers())
    print("=" * 50)