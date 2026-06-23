"""
Tạo cơ sở dữ liệu mẫu thứ hai: cửa hàng thương mại điện tử (ecommerce.db).
Lược đồ khác hẳn database pizza để minh hoạ việc đổi database làm thay đổi
sơ đồ quan hệ (ER) trên web.

Quan hệ:
    products.category_id   -> categories.category_id
    orders.customer_id     -> customers.customer_id
    order_items.order_id   -> orders.order_id
    order_items.product_id -> products.product_id
"""

import sqlite3
import random
from datetime import datetime, timedelta

DB_PATH = "ecommerce.db"

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# ==================================================
# DROP OLD TABLES
# ==================================================
for tbl in ("order_items", "orders", "products", "customers", "categories"):
    cur.execute(f"DROP TABLE IF EXISTS {tbl}")

# ==================================================
# CREATE TABLES
# ==================================================
cur.execute("""
CREATE TABLE categories (
    category_id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_name TEXT,
    description TEXT
)
""")

cur.execute("""
CREATE TABLE products (
    product_id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_name TEXT,
    category_id INTEGER,
    price REAL,
    stock_quantity INTEGER,
    FOREIGN KEY(category_id) REFERENCES categories(category_id)
)
""")

cur.execute("""
CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT,
    email TEXT,
    city TEXT,
    signup_date TEXT
)
""")

cur.execute("""
CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER,
    order_date TEXT,
    status TEXT,
    shipping_fee REAL,
    FOREIGN KEY(customer_id) REFERENCES customers(customer_id)
)
""")

cur.execute("""
CREATE TABLE order_items (
    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER,
    product_id INTEGER,
    quantity INTEGER,
    unit_price REAL,
    FOREIGN KEY(order_id) REFERENCES orders(order_id),
    FOREIGN KEY(product_id) REFERENCES products(product_id)
)
""")

# ==================================================
# SEED DATA
# ==================================================
category_rows = [
    ("Electronics", "Phones, laptops and accessories"),
    ("Books", "Printed and e-books"),
    ("Home & Kitchen", "Appliances and homeware"),
    ("Fashion", "Clothing, shoes and bags"),
    ("Sports", "Sportswear and equipment"),
]
cur.executemany(
    "INSERT INTO categories (category_name, description) VALUES (?, ?)",
    category_rows,
)

product_pool = {
    "Electronics": ["Smartphone", "Laptop", "Headphones", "Smartwatch", "Tablet"],
    "Books": ["Novel", "Cookbook", "Textbook", "Comic", "Biography"],
    "Home & Kitchen": ["Blender", "Coffee Maker", "Air Fryer", "Knife Set", "Vacuum"],
    "Fashion": ["T-Shirt", "Jeans", "Sneakers", "Backpack", "Jacket"],
    "Sports": ["Yoga Mat", "Dumbbell", "Football", "Tennis Racket", "Bicycle"],
}
products = []
for cat_id, (cat_name, _) in enumerate(category_rows, start=1):
    for name in product_pool[cat_name]:
        price = round(random.uniform(5, 800), 2)
        stock = random.randint(0, 300)
        products.append((f"{name}", cat_id, price, stock))
cur.executemany(
    "INSERT INTO products (product_name, category_id, price, stock_quantity) "
    "VALUES (?, ?, ?, ?)",
    products,
)
n_products = len(products)

cities = ["Hanoi", "HCM", "Da Nang", "Hai Phong", "Can Tho", "Hue", "Vung Tau"]
customers = []
for i in range(1, 301):
    signup = datetime.now() - timedelta(days=random.randint(1, 1200))
    customers.append((
        f"Customer {i}",
        f"customer{i}@shop.example",
        random.choice(cities),
        signup.strftime("%Y-%m-%d"),
    ))
cur.executemany(
    "INSERT INTO customers (full_name, email, city, signup_date) VALUES (?, ?, ?, ?)",
    customers,
)

statuses = ["Delivered", "Delivered", "Delivered", "Shipping", "Cancelled"]
orders = []
for _ in range(1500):
    customer_id = random.randint(1, 300)
    order_date = datetime.now() - timedelta(
        days=random.randint(0, 365),
        hours=random.randint(0, 23),
    )
    orders.append((
        customer_id,
        order_date.strftime("%Y-%m-%d %H:%M:%S"),
        random.choice(statuses),
        round(random.uniform(0, 5), 2),
    ))
cur.executemany(
    "INSERT INTO orders (customer_id, order_date, status, shipping_fee) "
    "VALUES (?, ?, ?, ?)",
    orders,
)
n_orders = len(orders)

# Pre-load product prices for the order items
cur.execute("SELECT product_id, price FROM products")
price_by_product = dict(cur.fetchall())

order_items = []
for order_id in range(1, n_orders + 1):
    for _ in range(random.randint(1, 4)):
        product_id = random.randint(1, n_products)
        quantity = random.randint(1, 5)
        order_items.append((
            order_id,
            product_id,
            quantity,
            price_by_product[product_id],
        ))
cur.executemany(
    "INSERT INTO order_items (order_id, product_id, quantity, unit_price) "
    "VALUES (?, ?, ?, ?)",
    order_items,
)

conn.commit()
conn.close()

print("E-commerce database created: ecommerce.db")
print("Tables: categories, products, customers, orders, order_items")
print(f"{n_products} products, {len(customers)} customers, "
      f"{n_orders} orders, {len(order_items)} order items.")
