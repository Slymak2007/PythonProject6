from classes import *
import pathlib
import json

def placing():
    order_ids = 1
    customer_ids = 1
    name = "d"
    email = "k"

    customer = Customer(customer_ids, name, email)

    laptop = PhysicalProduct(1, "Laptop", 25000.0, "physical", 2, )
    smartphone = PhysicalProduct(2, "Smasung A52", 20000, "physical",1)
    ebook = DigitalProduct(3, "Ebook", 300.0, "physical", "http://link.com/book")

    '''catalog_list = []
    catalog_list.append(laptop.to_dict())
    catalog_list.append(smartphone.to_dict())
    catalog_list.append(ebook.to_dict())


    with open("catalog/catalog.json", "w") as f:
        json.dumps(catalog_list)
        f.write(json.dumps(catalog_list))
    print(json.dumps(catalog_list))'''

    order = Order(order_ids, customer, email)
    order.add_product(laptop)
    order.add_product(ebook)

    order_ids += 1

    return order, customer

def saving_order():
    order, customer = placing()
    print(repr(order))

    order_dict = order.to_dict()
    json_order = json.dumps(order_dict)
    loaded_order = json.loads(json_order)
    restored = Order.from_order(loaded_order)
    print(loaded_order)
    order_name = "saved_orders/order" + str(restored.order_id) + (".json"
                                                                  ""
                                                                 "")
    print(order_name)
    with open(order_name, "w") as f:
        json.dump(loaded_order, f, indent=2)