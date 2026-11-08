import os
from classes import *
import pathlib
import json
import time

class InsufficientStockError(Exception):
    pass


class InvalidOrderStatusError(Exception):
    pass



def placing():
    clear = lambda: os.system('cls')
    order_ids = time.time()
    customer_ids = 1
    name = input("Enter your name: ")
    email = input("Enter your email: ")
    customer = Customer(customer_ids, name, email)
    order = Order(order_ids, customer, email)
    with open("catalog/catalog.json", "r+") as f:
        data = json.load(f)
        while True:
            print("Список товарів:")
            for i in data:
                print("Назва:", i['name'] + " Price:", i['base_price'], " Id:", i['product_id'])
            try:
                selc = int(input("Напишіть id товару який хочете обрати:"))
                if selc == 0:
                    break
                if selc < 1:
                    raise IndexError
                if order.status != "New":
                    raise InvalidOrderStatusError("Некоректний статус замовлення: " + str(order.status))
                if data[selc - 1]['stock'] < 1:
                    raise InsufficientStockError("Недостатньо товару на складі: " + data[selc - 1]['name'])
                order.add_product(data[selc - 1])
                data[selc - 1]['stock'] -= 1
                data[selc - 1]['popularity'] += 1
                f.seek(0)
                json.dump(data, f, ensure_ascii=False, indent=4)
                f.truncate()
            except ValueError:
                print("Помилка: введіть число")
            except IndexError:
                print("Помилка: товару з таким Id немає")
            except InsufficientStockError as e:
                print(e)
            except InvalidOrderStatusError as e:
                print(e)
                break
            clear()
            print("Товар додано до корзини!")
    return order, customer

def saving_order():
    order, customer = placing()
    order_dict = order.to_dict()
    json_order = json.dumps(order_dict)
    loaded_order = json.loads(json_order)
    restored = Order.from_order(loaded_order)
    order_name = "saved_orders/order" +"_"+ str(customer.name) + "_" +str(time.time())+ (".json")
    with open(order_name, "x") as f:
        json.dump(loaded_order, f, indent=2)