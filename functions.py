from classes import *
import pathlib
import json
import datetime

def placing():
    order_ids = 1
    customer_ids = 1
    name = input("Enter your name: ")
    email = input("Enter your email: ")

    customer = Customer(customer_ids, name, email)
    order = Order(order_ids, customer, email)
    laptop = PhysicalProduct(1, "Laptop", 25000.0, "physical", 2, )
    smartphone = PhysicalProduct(2, "Smasung A52", 20000, "physical",1)
    ebook = DigitalProduct(3, "Ebook", 300.0, "physical", "http://link.com/book")

    with open("catalog/catalog.json", "r+") as f:
        data = json.load(f)
        cor = []
        while True:
            print("Оберіть товари")
            for i in data:
                print("Назва:", i['name'] + " Price:", i['base_price'], " Id:", i['product_id'])
            selc = int(input())
            if selc == 0:
                break
            order.add_product(data[selc - 1])
    '''order.add_product(laptop)
    order.add_product(ebook)

    order_ids += 1
    '''
    return order, customer

def saving_order():
    order, customer = placing()

    order_dict = order.to_dict()
    json_order = json.dumps(order_dict)
    loaded_order = json.loads(json_order)
    restored = Order.from_order(loaded_order)
    print(loaded_order)
    order_name = "saved_orders/order" + str(datetime.date.today()) + (".json")
    with open(order_name, "w") as f:
        json.dump(loaded_order, f, indent=2)