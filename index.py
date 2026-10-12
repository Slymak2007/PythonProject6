import pathlib
import json


class Product:
    def __init__(self, product_id, name, base_price):
        self.product_id = product_id
        self.name = name
        self.base_price = base_price

    def calculate_total_price(self):
        # Метод, який перевизначається у дочірніх класах
        return self.base_price

    def __str__(self):
        return f"{self.name} (ID: {self.product_id})"

#2.СПАДКУВАННЯ ТА ПОЛІМОРФІЗМ

class PhysicalProduct(Product):
    def __init__(self, product_id, name, base_price, weight_kg, shipping_rate=50.0):
        super().__init__(product_id, name, base_price)
        self.weight_kg = weight_kg
        self.shipping_rate = shipping_rate

    def calculate_total_price(self):
        #базова ціна + (вага * тариф за кг)
        return self.base_price + (self.weight_kg * self.shipping_rate)

class DigitalProduct(Product):
    def __init__(self, product_id, name, base_price, download_link):
        super().__init__(product_id, name, base_price)
        self.download_link = download_link

    def calculate_total_price(self):
        #лише базова ціна
        return self.base_price

#3.КЛАСИ КЛІЄНТА ТА ЗАМОВЛЕННЯ

class Customer:
    def __init__(self, customer_id, name, email):
        self.customer_id = customer_id
        self.name = name
        self.email = email

    def __str__(self):
        return f"Клієнт {self.name} ({self.email})"

class Order:
    def __init__(self, order_id, customer, email):
        self.order_id = order_id
        self.customer = customer
        self.email = email
        self.products_order = []  #Список товарів
        self.status = "New"

    def add_product(self, product):
        self.products_order.append(product)

    def calculate_order_total(self):
        #кожен товар сам знає, як рахувати свою ціну
        return sum(product.calculate_total_price() for product in self.products_order)

    def to_dict(self):
        return {
            "order_id": self.order_id,
            "customer": self.customer,
            "email": self.email
        }

    @classmethod
    def from_order(cls, data):
        return cls(order_id = data["order_id"],
                   customer = data["customer"],
                   email = data["email"]
                   )

    def __repr__(self):
        return f"Order(order_id: {self.order_id}, customer: {self.customer}, email: {self.email})"

    def __str__(self):
        return (f"Замовлення #{self.order_id} | Клієнт: {self.customer.name} | "
                f"Товарів: {len(self.products_order)} | Сума: {self.calculate_order_total()} грн")

'''class JsonStorage:
    def __init__(self, path):
        self.path = pathlib.Path(path)

    def save_json(self, data):
        self.path'''

#ДЕМОНСТРАЦІЯ РОБОТИ

def placing():
    order_ids = 1
    customer_ids = 1
    name = "dima"
    email = "kra"

    customer = Customer(customer_ids, name, email)

    laptop = PhysicalProduct(101, "Ноутбук", 25000.0, 2.5)
    ebook = DigitalProduct(102, "Електронна книга", 300.0, "http://link.com/book")

    order = Order(order_ids, customer, email)
    order.add_product(laptop)
    order.add_product(ebook)

    order_ids += 1

    return order, customer

if __name__ == "__main__":
    order, customer = placing()
    print(repr(order))

    order_dict = order.to_dict()
    print(order_dict)
    print(order)
    print(customer)