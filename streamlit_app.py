from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import pandas as pd
import streamlit as st
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.errors import PyMongoError


st.set_page_config(page_title="Personal Finance", page_icon=":credit_card:", layout="wide")


@st.cache_resource
def get_database():
    config = st.secrets.get("mongodb", {})
    uri = config.get("uri")
    database_name = config.get("database", "finance_app")

    if not uri:
        return None

    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    return client[database_name]


def ensure_indexes(db):
    db.transactions.create_index([("date", DESCENDING), ("created_at", DESCENDING)])
    db.transactions.create_index([("type", ASCENDING)])
    db.transactions.create_index([("category", ASCENDING)])
    db.accounts.create_index("name", unique=True)
    db.categories.create_index([("type", ASCENDING), ("name", ASCENDING)], unique=True)


def money_to_float(value):
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        return None
    if amount <= 0:
        return None
    return float(amount)


def seed_defaults(db):
    if db.accounts.count_documents({}) == 0:
        db.accounts.insert_many(
            [
                {"name": "Cash", "type": "cash", "created_at": datetime.utcnow()},
                {"name": "Checking", "type": "bank", "created_at": datetime.utcnow()},
                {"name": "Credit Card", "type": "credit", "created_at": datetime.utcnow()},
            ]
        )

    if db.categories.count_documents({}) == 0:
        db.categories.insert_many(
            [
                {"name": "Food", "type": "expense"},
                {"name": "Transport", "type": "expense"},
                {"name": "Shopping", "type": "expense"},
                {"name": "Housing", "type": "expense"},
                {"name": "Salary", "type": "income"},
                {"name": "Gift", "type": "income"},
            ]
        )


def transaction_frame(db):
    rows = list(db.transactions.find({}, {"_id": 0}).sort("date", DESCENDING).limit(500))
    if not rows:
        return pd.DataFrame()

    frame = pd.DataFrame(rows)
    visible_columns = ["date", "type", "amount", "account", "category", "note", "created_at"]
    frame = frame[[column for column in visible_columns if column in frame.columns]]
    if "date" in frame:
        frame["date"] = pd.to_datetime(frame["date"]).dt.date
    if "created_at" in frame:
        frame["created_at"] = pd.to_datetime(frame["created_at"]).dt.strftime("%Y-%m-%d %H:%M")
    return frame


st.title("Personal Finance")

try:
    db = get_database()
except PyMongoError as error:
    st.error("Could not connect to MongoDB. Check your Streamlit Secrets and Atlas network access.")
    st.caption(str(error))
    st.stop()

if db is None:
    st.warning("Add your MongoDB connection details in Streamlit Secrets to start using the app.")
    st.code(
        """[mongodb]
uri = "mongodb+srv://USERNAME:PASSWORD@cluster.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
database = "finance_app"
""",
        language="toml",
    )
    st.stop()

ensure_indexes(db)
seed_defaults(db)

accounts = [item["name"] for item in db.accounts.find({}, {"name": 1}).sort("name", ASCENDING)]

entry, overview = st.columns([0.9, 1.4], gap="large")

with entry:
    st.subheader("New Transaction")
    transaction_type = st.radio("Type", ["expense", "income"], horizontal=True)
    categories = [
        item["name"]
        for item in db.categories.find({"type": transaction_type}, {"name": 1}).sort("name", ASCENDING)
    ]

    with st.form("transaction_form", clear_on_submit=True):
        amount = st.number_input("Amount", min_value=0.0, step=1.0, format="%.2f")
        account = st.selectbox("Account", accounts)
        category = st.selectbox("Category", categories)
        transaction_date = st.date_input("Date", value=date.today())
        note = st.text_input("Note")
        submitted = st.form_submit_button("Save")

    if submitted:
        parsed_amount = money_to_float(amount)
        if parsed_amount is None:
            st.error("Enter an amount greater than zero.")
        else:
            db.transactions.insert_one(
                {
                    "type": transaction_type,
                    "amount": parsed_amount,
                    "account": account,
                    "category": category,
                    "date": datetime.combine(transaction_date, datetime.min.time()),
                    "note": note.strip(),
                    "created_at": datetime.utcnow(),
                }
            )
            st.success("Transaction saved.")
            st.rerun()

with overview:
    st.subheader("Overview")
    frame = transaction_frame(db)

    if frame.empty:
        st.info("No transactions yet.")
    else:
        income = frame.loc[frame["type"] == "income", "amount"].sum()
        expenses = frame.loc[frame["type"] == "expense", "amount"].sum()
        balance = income - expenses

        metric_a, metric_b, metric_c = st.columns(3)
        metric_a.metric("Income", f"${income:,.2f}")
        metric_b.metric("Expenses", f"${expenses:,.2f}")
        metric_c.metric("Net", f"${balance:,.2f}")

        st.dataframe(frame, use_container_width=True, hide_index=True)

        chart_data = frame.groupby(["category", "type"], as_index=False)["amount"].sum()
        st.bar_chart(chart_data, x="category", y="amount", color="type")
