-- SQLite schema for AI SQL Assistant

CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT,
    city TEXT,
    member_level TEXT,
    signup_date TEXT
);
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
);
CREATE TABLE pizza (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    category TEXT,
    size TEXT,
    price REAL
);
CREATE TABLE pizzas (
    pizza_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    category TEXT,
    size TEXT,
    price REAL,
    calories INTEGER,
    available INTEGER
);
CREATE TABLE stores (
    store_id INTEGER PRIMARY KEY AUTOINCREMENT,
    branch_name TEXT,
    city TEXT,
    manager TEXT
);
