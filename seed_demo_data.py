from datetime import date, datetime, timedelta
from pathlib import Path
import re

from pymongo import MongoClient


def read_local_secret():
    secrets_path = Path(".streamlit/secrets.toml")
    if not secrets_path.exists():
        raise SystemExit("Missing .streamlit/secrets.toml")

    text = secrets_path.read_text(encoding="utf-8")
    uri_match = re.search(r'uri\s*=\s*"([^"]+)"', text)
    db_match = re.search(r'database\s*=\s*"([^"]+)"', text)
    if not uri_match:
        raise SystemExit("Missing mongodb.uri in .streamlit/secrets.toml")
    return uri_match.group(1), db_match.group(1) if db_match else "finance_app"


def to_datetime(value):
    return datetime.combine(value, datetime.min.time())


def seed_demo_data(db):
    if db.transactions.count_documents({"source": "demo"}) > 0:
        return 0

    today = date.today()
    expense_plan = [
        ("Food", "Credit Card", 18.5, "Coffee and lunch"),
        ("Transport", "Credit Card", 42.0, "Fuel and parking"),
        ("Shopping", "Credit Card", 86.7, "Home supplies"),
        ("Utilities", "Checking", 96.2, "Electric bill"),
        ("Entertainment", "Credit Card", 34.0, "Movie night"),
        ("Health", "Credit Card", 58.0, "Pharmacy"),
        ("Housing", "Checking", 1850.0, "Rent"),
    ]
    income_plan = [
        ("Salary", "Checking", 4200.0, "Monthly salary"),
        ("Interest", "Savings", 18.4, "Savings interest"),
        ("Bonus", "Checking", 650.0, "Project bonus"),
    ]

    records = []
    for index in range(75):
        tx_date = today - timedelta(days=index)
        category, account, amount, note = expense_plan[index % len(expense_plan)]
        status = "pending_reimbursement" if index in {8, 19, 43} else "cleared"
        records.append(
            {
                "type": "expense",
                "amount": round(amount * (1 + (index % 5) * 0.07), 2),
                "account": account,
                "category": category,
                "date": to_datetime(tx_date),
                "note": note,
                "status": status,
                "reimbursement_amount": round(amount * 0.8, 2) if status == "pending_reimbursement" else 0.0,
                "tags": ["demo"],
                "source": "demo",
                "created_at": datetime.utcnow(),
            }
        )

    for index in range(4):
        category, account, amount, note = income_plan[index % len(income_plan)]
        records.append(
            {
                "type": "income",
                "amount": amount,
                "account": account,
                "category": category,
                "date": to_datetime(today.replace(day=1) - timedelta(days=30 * index)),
                "note": note,
                "status": "cleared",
                "reimbursement_amount": 0.0,
                "tags": ["demo"],
                "source": "demo",
                "created_at": datetime.utcnow(),
            }
        )

    records.append(
        {
            "type": "income",
            "amount": 72.5,
            "account": "Credit Card",
            "category": "Shopping",
            "date": to_datetime(today - timedelta(days=6)),
            "note": "Refund for returned item",
            "status": "refund",
            "reimbursement_amount": 0.0,
            "tags": ["demo", "refund"],
            "source": "demo",
            "created_at": datetime.utcnow(),
        }
    )

    db.transactions.insert_many(records)

    for account in [
        {"name": "Cash", "type": "cash", "opening_balance": 300.0},
        {"name": "Checking", "type": "bank", "opening_balance": 5200.0},
        {"name": "Credit Card", "type": "credit", "opening_balance": -420.0},
        {"name": "Savings", "type": "savings", "opening_balance": 12000.0},
    ]:
        db.accounts.update_one({"name": account["name"]}, {"$setOnInsert": account}, upsert=True)

    for category in ["Food", "Transport", "Shopping", "Entertainment", "Utilities"]:
        db.budgets.update_one(
            {"month": today.strftime("%Y-%m"), "category": category},
            {"$set": {"month": today.strftime("%Y-%m"), "category": category, "amount": 500.0}},
            upsert=True,
        )

    return len(records)


if __name__ == "__main__":
    uri, database_name = read_local_secret()
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    count = seed_demo_data(client[database_name])
    print(f"seeded={count}")
