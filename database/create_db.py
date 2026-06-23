import sqlite3
import random
from datetime import datetime, timedelta

DB_PATH = "database.db"

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# ==================================================
# DROP OLD TABLES
# ==================================================
cursor.execute("DROP TABLE IF EXISTS orders")
cursor.execute("DROP TABLE IF EXISTS customers")
cursor.execute("DROP TABLE IF EXISTS pizzas")
cursor.execute("DROP TABLE IF EXISTS stores")

# ==================================================
# CREATE TABLES
# ==================================================

# Pizza menu
cursor.execute("""
CREATE TABLE pizzas (
    pizza_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    category TEXT,
    size TEXT,
    price REAL,
    calories INTEGER,
    available INTEGER
)
""")

# Customers
cursor.execute("""
CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT,
    city TEXT,
    member_level TEXT,
    signup_date TEXT
)
""")

# Stores
cursor.execute("""
CREATE TABLE stores (
    store_id INTEGER PRIMARY KEY AUTOINCREMENT,
    branch_name TEXT,
    city TEXT,
    manager TEXT
)
""")

# Orders
cursor.execute("""
CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER,
    pizza_id INTEGER,
    store_id INTEGER,
    quantity INTEGER,
    total_price REAL,
    payment_method TEXT,
    order_status TEXT,
    order_time TEXT,
    delivery_minutes INTEGER,
    rating INTEGER,
    FOREIGN KEY(customer_id) REFERENCES customers(customer_id),
    FOREIGN KEY(pizza_id) REFERENCES pizzas(pizza_id),
    FOREIGN KEY(store_id) REFERENCES stores(store_id)
)
""")

# ==================================================
# DATA
# ==================================================

pizza_names = [
    ("Margherita", "Classic"),
    ("Pepperoni", "Meat"),
    ("BBQ Chicken", "Meat"),
    ("Hawaiian", "Meat"),
    ("Veggie", "Vegetarian"),
    ("Four Cheese", "Vegetarian"),
    ("Seafood", "Seafood"),
    ("Meat Lovers", "Meat"),
    ("Spicy Beef", "Meat"),
    ("Mushroom Deluxe", "Vegetarian")
]

sizes = {
    "S": 6,
    "M": 9,
    "L": 12
}

cities = ["Hanoi", "HCM", "Da Nang", "Hai Phong", "Can Tho"]
member_levels = ["Normal", "Silver", "Gold", "VIP"]
payments = ["Cash", "Card", "Momo", "ZaloPay"]
statuses = ["Completed", "Completed", "Completed", "Cancelled", "Preparing"]

# ==================================================
# INSERT STORES
# ==================================================
stores = []
for i in range(1, 8):
    stores.append((
        f"Pizza Branch {i}",
        random.choice(cities),
        f"Manager {i}"
    ))

cursor.executemany("""
INSERT INTO stores (branch_name, city, manager)
VALUES (?, ?, ?)
""", stores)

# ==================================================
# INSERT CUSTOMERS
# ==================================================
customers = []

for i in range(1, 501):
    signup = datetime.now() - timedelta(days=random.randint(1, 1000))
    customers.append((
        f"Customer {i}",
        random.choice(cities),
        random.choice(member_levels),
        signup.strftime("%Y-%m-%d")
    ))

cursor.executemany("""
INSERT INTO customers (full_name, city, member_level, signup_date)
VALUES (?, ?, ?, ?)
""", customers)

# ==================================================
# INSERT PIZZAS
# ==================================================
pizza_rows = []

for name, category in pizza_names:
    for size, base in sizes.items():
        price = round(base + random.uniform(0, 3), 2)
        calories = random.randint(500, 1400)
        available = random.choice([1, 1, 1, 1, 0])

        pizza_rows.append((
            name, category, size, price, calories, available
        ))

cursor.executemany("""
INSERT INTO pizzas
(name, category, size, price, calories, available)
VALUES (?, ?, ?, ?, ?, ?)
""", pizza_rows)

# ==================================================
# INSERT ORDERS (5000 rows)
# ==================================================
orders = []

for _ in range(5000):
    customer_id = random.randint(1, 500)
    pizza_id = random.randint(1, len(pizza_rows))
    store_id = random.randint(1, 7)
    quantity = random.randint(1, 5)

    # lấy giá pizza
    cursor.execute("SELECT price FROM pizzas WHERE pizza_id=?", (pizza_id,))
    price = cursor.fetchone()[0]

    total = round(price * quantity, 2)

    order_date = datetime.now() - timedelta(
        days=random.randint(0, 365),
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59)
    )

    status = random.choice(statuses)

    delivery = random.randint(15, 60) if status == "Completed" else None
    rating = random.randint(1, 5) if status == "Completed" else None

    orders.append((
        customer_id,
        pizza_id,
        store_id,
        quantity,
        total,
        random.choice(payments),
        status,
        order_date.strftime("%Y-%m-%d %H:%M:%S"),
        delivery,
        rating
    ))

cursor.executemany("""
INSERT INTO orders (
customer_id, pizza_id, store_id, quantity,
total_price, payment_method, order_status,
order_time, delivery_minutes, rating
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
""", orders)

# ==================================================
# FINISH
# ==================================================
conn.commit()
conn.close()

print("✅ Advanced Pizza Database Created Successfully!")
print("Tables:")
print("- pizzas")
print("- customers")
print("- stores")
print("- orders")
print("5000 orders generated.")