from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from io import StringIO

import pandas as pd
import streamlit as st
from bson import ObjectId
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.errors import DuplicateKeyError, PyMongoError


st.set_page_config(page_title="Personal Finance", page_icon=":credit_card:", layout="wide")


DEFAULT_ACCOUNTS = [
    {"name": "Cash", "type": "cash", "opening_balance": 300.0},
    {"name": "Checking", "type": "bank", "opening_balance": 5200.0},
    {"name": "Credit Card", "type": "credit", "opening_balance": -420.0},
    {"name": "Savings", "type": "savings", "opening_balance": 12000.0},
]

DEFAULT_CATEGORIES = [
    {"name": "Food", "type": "expense"},
    {"name": "Transport", "type": "expense"},
    {"name": "Shopping", "type": "expense"},
    {"name": "Housing", "type": "expense"},
    {"name": "Utilities", "type": "expense"},
    {"name": "Health", "type": "expense"},
    {"name": "Travel", "type": "expense"},
    {"name": "Entertainment", "type": "expense"},
    {"name": "Salary", "type": "income"},
    {"name": "Bonus", "type": "income"},
    {"name": "Gift", "type": "income"},
    {"name": "Interest", "type": "income"},
]


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
    db.transactions.create_index([("type", ASCENDING), ("category", ASCENDING)])
    db.transactions.create_index([("status", ASCENDING)])
    db.accounts.create_index("name", unique=True)
    db.categories.create_index([("type", ASCENDING), ("name", ASCENDING)], unique=True)
    db.budgets.create_index([("month", ASCENDING), ("category", ASCENDING)], unique=True)
    db.recurring_rules.create_index([("active", ASCENDING), ("next_date", ASCENDING)])


def money_to_float(value):
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        return None
    if amount <= 0:
        return None
    return float(amount)


def as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return pd.to_datetime(value).date()


def to_datetime(value):
    if isinstance(value, datetime):
        return value
    return datetime.combine(value, datetime.min.time())


def month_key(value):
    value = as_date(value)
    return value.strftime("%Y-%m")


def seed_defaults(db):
    for account in DEFAULT_ACCOUNTS:
        db.accounts.update_one(
            {"name": account["name"]},
            {"$setOnInsert": {**account, "created_at": datetime.utcnow()}},
            upsert=True,
        )

    for category in DEFAULT_CATEGORIES:
        db.categories.update_one(
            {"type": category["type"], "name": category["name"]},
            {"$setOnInsert": category},
            upsert=True,
        )


def seed_demo_data(db):
    if db.transactions.count_documents({"source": "demo"}) > 0:
        return 0

    today = date.today()
    records = []
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

    this_month = today.strftime("%Y-%m")
    budgets = [
        {"month": this_month, "category": "Food", "amount": 650.0},
        {"month": this_month, "category": "Transport", "amount": 260.0},
        {"month": this_month, "category": "Shopping", "amount": 500.0},
        {"month": this_month, "category": "Entertainment", "amount": 220.0},
        {"month": this_month, "category": "Utilities", "amount": 180.0},
    ]
    for budget in budgets:
        db.budgets.update_one(
            {"month": budget["month"], "category": budget["category"]},
            {"$set": budget},
            upsert=True,
        )

    db.recurring_rules.update_one(
        {"name": "Monthly rent"},
        {
            "$set": {
                "name": "Monthly rent",
                "type": "expense",
                "amount": 1850.0,
                "account": "Checking",
                "category": "Housing",
                "frequency": "monthly",
                "next_date": to_datetime(today.replace(day=1) + timedelta(days=31)),
                "note": "Auto-created rent reminder",
                "active": True,
            }
        },
        upsert=True,
    )
    return len(records)


def get_accounts(db):
    return [item["name"] for item in db.accounts.find({}, {"name": 1}).sort("name", ASCENDING)]


def get_categories(db, category_type=None):
    query = {"type": category_type} if category_type else {}
    return [item["name"] for item in db.categories.find(query, {"name": 1}).sort("name", ASCENDING)]


def transaction_frame(db, query=None, limit=1000, include_id=True):
    projection = None if include_id else {"_id": 0}
    rows = list(db.transactions.find(query or {}, projection).sort("date", DESCENDING).limit(limit))
    if not rows:
        return pd.DataFrame()

    for row in rows:
        if include_id:
            row["id"] = str(row.pop("_id"))
        row["date"] = as_date(row.get("date", date.today()))
        row["status"] = row.get("status", "cleared")
        row["reimbursement_amount"] = float(row.get("reimbursement_amount", 0.0) or 0.0)
        row["tags"] = ", ".join(row.get("tags", []))
    frame = pd.DataFrame(rows)
    preferred = [
        "id",
        "date",
        "type",
        "amount",
        "account",
        "category",
        "status",
        "reimbursement_amount",
        "tags",
        "note",
    ]
    return frame[[column for column in preferred if column in frame.columns]]


def save_transaction(db, payload, transaction_id=None):
    payload["updated_at"] = datetime.utcnow()
    if transaction_id:
        db.transactions.update_one({"_id": ObjectId(transaction_id)}, {"$set": payload})
        return
    payload["created_at"] = datetime.utcnow()
    db.transactions.insert_one(payload)


def transaction_form(db, accounts, mode="create", transaction=None):
    tx = transaction or {}
    default_type = tx.get("type", "expense")
    type_index = ["expense", "income", "transfer"].index(default_type) if default_type in ["expense", "income", "transfer"] else 0
    tx_type = st.radio("Type", ["expense", "income", "transfer"], index=type_index, horizontal=True, key=f"{mode}_type")

    category_options = get_categories(db, tx_type) if tx_type != "transfer" else ["Transfer"]
    if not category_options:
        category_options = ["Uncategorized"]

    with st.form(f"{mode}_transaction_form", clear_on_submit=mode == "create"):
        amount = st.number_input("Amount", min_value=0.0, step=1.0, format="%.2f", value=float(tx.get("amount", 0.0)))
        account_index = accounts.index(tx.get("account")) if tx.get("account") in accounts else 0
        account = st.selectbox("Account", accounts, index=account_index)
        category_index = category_options.index(tx.get("category")) if tx.get("category") in category_options else 0
        category = st.selectbox("Category", category_options, index=category_index)
        tx_date = st.date_input("Date", value=as_date(tx.get("date", date.today())))
        status_options = ["cleared", "pending", "pending_reimbursement", "reimbursed", "refund"]
        status_index = status_options.index(tx.get("status")) if tx.get("status") in status_options else 0
        status = st.selectbox("Status", status_options, index=status_index)
        reimbursement_amount = st.number_input(
            "Reimbursement amount",
            min_value=0.0,
            step=1.0,
            format="%.2f",
            value=float(tx.get("reimbursement_amount", 0.0)),
        )
        tags = st.text_input("Tags", value=", ".join(tx.get("tags", [])) if isinstance(tx.get("tags"), list) else tx.get("tags", ""))
        note = st.text_input("Note", value=tx.get("note", ""))
        submitted = st.form_submit_button("Save")

    if submitted:
        parsed_amount = money_to_float(amount)
        if parsed_amount is None:
            st.error("Enter an amount greater than zero.")
            return False

        payload = {
            "type": tx_type,
            "amount": parsed_amount,
            "account": account,
            "category": category,
            "date": to_datetime(tx_date),
            "status": status,
            "reimbursement_amount": float(reimbursement_amount),
            "tags": [item.strip() for item in tags.split(",") if item.strip()],
            "note": note.strip(),
        }
        save_transaction(db, payload, tx.get("id"))
        st.success("Transaction saved.")
        return True
    return False


def dashboard(db):
    frame = transaction_frame(db, include_id=False)
    st.subheader("Dashboard")

    if frame.empty:
        st.info("No transactions yet. Add one manually or seed demo data.")
        return

    today = date.today()
    start_of_month = today.replace(day=1)
    month_frame = frame[frame["date"] >= start_of_month]
    income = month_frame.loc[month_frame["type"] == "income", "amount"].sum()
    expenses = month_frame.loc[month_frame["type"] == "expense", "amount"].sum()
    pending = month_frame.loc[month_frame["status"] == "pending_reimbursement", "reimbursement_amount"].sum()

    metric_a, metric_b, metric_c, metric_d = st.columns(4)
    metric_a.metric("Monthly income", f"${income:,.2f}")
    metric_b.metric("Monthly expenses", f"${expenses:,.2f}")
    metric_c.metric("Net", f"${income - expenses:,.2f}")
    metric_d.metric("Pending reimbursement", f"${pending:,.2f}")

    chart_left, chart_right = st.columns(2, gap="large")
    with chart_left:
        st.caption("Expense by category")
        category_data = (
            month_frame[month_frame["type"] == "expense"]
            .groupby("category", as_index=False)["amount"]
            .sum()
            .sort_values("amount", ascending=False)
        )
        st.bar_chart(category_data, x="category", y="amount")

    with chart_right:
        st.caption("Daily cashflow")
        daily = frame.copy()
        daily["signed_amount"] = daily.apply(lambda row: row["amount"] if row["type"] == "income" else -row["amount"], axis=1)
        daily = daily.groupby("date", as_index=False)["signed_amount"].sum().sort_values("date")
        st.line_chart(daily, x="date", y="signed_amount")

    st.caption("Recent transactions")
    st.dataframe(frame.head(12), use_container_width=True, hide_index=True)


def transaction_manager(db, accounts):
    st.subheader("Transactions")
    frame = transaction_frame(db)
    if frame.empty:
        st.info("No transactions yet.")
        return

    filters = st.columns(4)
    with filters[0]:
        type_filter = st.selectbox("Type filter", ["all", "expense", "income", "transfer"])
    with filters[1]:
        account_filter = st.selectbox("Account filter", ["all"] + accounts)
    with filters[2]:
        category_filter = st.selectbox("Category filter", ["all"] + get_categories(db))
    with filters[3]:
        status_filter = st.selectbox("Status filter", ["all", "cleared", "pending", "pending_reimbursement", "reimbursed", "refund"])

    visible = frame.copy()
    if type_filter != "all":
        visible = visible[visible["type"] == type_filter]
    if account_filter != "all":
        visible = visible[visible["account"] == account_filter]
    if category_filter != "all":
        visible = visible[visible["category"] == category_filter]
    if status_filter != "all":
        visible = visible[visible["status"] == status_filter]

    st.dataframe(visible, use_container_width=True, hide_index=True)
    if visible.empty:
        st.info("No transactions match these filters.")
        return

    selected_id = st.selectbox("Select a transaction to edit", visible["id"].tolist(), format_func=lambda item: item[:8] if item else "")
    selected = visible[visible["id"] == selected_id].iloc[0].to_dict()

    edit_col, delete_col = st.columns([3, 1])
    with edit_col:
        if transaction_form(db, accounts, mode="edit", transaction=selected):
            st.rerun()
    with delete_col:
        st.write("")
        st.write("")
        if st.button("Delete transaction", type="secondary"):
            db.transactions.delete_one({"_id": ObjectId(selected_id)})
            st.success("Transaction deleted.")
            st.rerun()


def budgets_view(db):
    st.subheader("Budgets")
    selected_month = st.text_input("Budget month", value=date.today().strftime("%Y-%m"))
    expense_categories = get_categories(db, "expense")

    with st.form("budget_form", clear_on_submit=True):
        category = st.selectbox("Category", expense_categories)
        amount = st.number_input("Monthly budget", min_value=0.0, step=50.0, format="%.2f")
        submitted = st.form_submit_button("Save budget")

    if submitted:
        parsed_amount = money_to_float(amount)
        if parsed_amount:
            db.budgets.update_one(
                {"month": selected_month, "category": category},
                {"$set": {"month": selected_month, "category": category, "amount": parsed_amount}},
                upsert=True,
            )
            st.success("Budget saved.")
            st.rerun()

    budgets = pd.DataFrame(list(db.budgets.find({"month": selected_month}, {"_id": 0})))
    if budgets.empty:
        st.info("No budgets set for this month.")
        return

    tx = transaction_frame(db, include_id=False)
    if tx.empty:
        budgets["spent"] = 0.0
    else:
        tx["month"] = tx["date"].apply(lambda item: item.strftime("%Y-%m"))
        spent = (
            tx[(tx["type"] == "expense") & (tx["month"] == selected_month)]
            .groupby("category", as_index=False)["amount"]
            .sum()
            .rename(columns={"amount": "spent"})
        )
        budgets = budgets.merge(spent, on="category", how="left").fillna({"spent": 0.0})
    budgets["remaining"] = budgets["amount"] - budgets["spent"]
    budgets["used_pct"] = (budgets["spent"] / budgets["amount"] * 100).round(1)
    st.dataframe(budgets, use_container_width=True, hide_index=True)


def recurring_view(db, accounts):
    st.subheader("Recurring")
    with st.form("recurring_form", clear_on_submit=True):
        name = st.text_input("Name")
        tx_type = st.radio("Recurring type", ["expense", "income"], horizontal=True)
        amount = st.number_input("Amount", min_value=0.0, step=1.0, format="%.2f")
        account = st.selectbox("Account", accounts)
        category = st.selectbox("Category", get_categories(db, tx_type))
        frequency = st.selectbox("Frequency", ["weekly", "monthly", "yearly"])
        next_date = st.date_input("Next date", value=date.today())
        note = st.text_input("Note")
        submitted = st.form_submit_button("Save recurring rule")

    if submitted:
        parsed_amount = money_to_float(amount)
        if parsed_amount and name.strip():
            db.recurring_rules.update_one(
                {"name": name.strip()},
                {
                    "$set": {
                        "name": name.strip(),
                        "type": tx_type,
                        "amount": parsed_amount,
                        "account": account,
                        "category": category,
                        "frequency": frequency,
                        "next_date": to_datetime(next_date),
                        "note": note.strip(),
                        "active": True,
                    }
                },
                upsert=True,
            )
            st.success("Recurring rule saved.")
            st.rerun()

    rows = list(db.recurring_rules.find({}, {"_id": 0}).sort("next_date", ASCENDING))
    if rows:
        frame = pd.DataFrame(rows)
        frame["next_date"] = pd.to_datetime(frame["next_date"]).dt.date
        st.dataframe(frame, use_container_width=True, hide_index=True)
    else:
        st.info("No recurring rules yet.")


def accounts_categories_view(db):
    account_tab, category_tab = st.tabs(["Accounts", "Categories"])

    with account_tab:
        with st.form("account_form", clear_on_submit=True):
            name = st.text_input("Account name")
            account_type = st.selectbox("Account type", ["cash", "bank", "credit", "savings", "investment", "loan"])
            opening_balance = st.number_input("Opening balance", step=100.0, format="%.2f")
            submitted = st.form_submit_button("Add account")
        if submitted and name.strip():
            try:
                db.accounts.insert_one(
                    {
                        "name": name.strip(),
                        "type": account_type,
                        "opening_balance": float(opening_balance),
                        "created_at": datetime.utcnow(),
                    }
                )
                st.success("Account added.")
                st.rerun()
            except DuplicateKeyError:
                st.error("That account already exists.")
        st.dataframe(pd.DataFrame(list(db.accounts.find({}, {"_id": 0}))), use_container_width=True, hide_index=True)

    with category_tab:
        with st.form("category_form", clear_on_submit=True):
            name = st.text_input("Category name")
            category_type = st.radio("Category type", ["expense", "income"], horizontal=True)
            submitted = st.form_submit_button("Add category")
        if submitted and name.strip():
            try:
                db.categories.insert_one({"name": name.strip(), "type": category_type})
                st.success("Category added.")
                st.rerun()
            except DuplicateKeyError:
                st.error("That category already exists.")
        st.dataframe(pd.DataFrame(list(db.categories.find({}, {"_id": 0}))), use_container_width=True, hide_index=True)


def import_export_view(db, accounts):
    st.subheader("Import / Export")
    frame = transaction_frame(db)
    export_frame = frame.drop(columns=["id"], errors="ignore")
    st.download_button(
        "Download CSV",
        data=export_frame.to_csv(index=False).encode("utf-8"),
        file_name=f"transactions-{date.today().isoformat()}.csv",
        mime="text/csv",
        disabled=export_frame.empty,
    )

    uploaded = st.file_uploader("Upload CSV", type=["csv"])
    if uploaded:
        imported = pd.read_csv(uploaded)
        required = {"date", "type", "amount", "account", "category"}
        missing = required - set(imported.columns)
        if missing:
            st.error(f"Missing columns: {', '.join(sorted(missing))}")
        else:
            st.dataframe(imported.head(20), use_container_width=True, hide_index=True)
            if st.button("Import rows"):
                records = []
                for _, row in imported.iterrows():
                    records.append(
                        {
                            "date": to_datetime(pd.to_datetime(row["date"]).date()),
                            "type": str(row["type"]),
                            "amount": float(row["amount"]),
                            "account": str(row["account"]),
                            "category": str(row["category"]),
                            "status": str(row.get("status", "cleared")),
                            "reimbursement_amount": float(row.get("reimbursement_amount", 0.0) or 0.0),
                            "tags": [item.strip() for item in str(row.get("tags", "")).split(",") if item.strip()],
                            "note": str(row.get("note", "")),
                            "source": "csv",
                            "created_at": datetime.utcnow(),
                        }
                    )
                if records:
                    db.transactions.insert_many(records)
                    st.success(f"Imported {len(records)} rows.")
                    st.rerun()

    if st.button("Seed demo data"):
        count = seed_demo_data(db)
        st.success(f"Added {count} demo transactions." if count else "Demo data already exists.")
        st.rerun()


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
accounts = get_accounts(db)

tabs = st.tabs(["Dashboard", "Add", "Transactions", "Budgets", "Recurring", "Accounts", "Import / Export"])

with tabs[0]:
    dashboard(db)

with tabs[1]:
    st.subheader("New Transaction")
    if transaction_form(db, accounts):
        st.rerun()

with tabs[2]:
    transaction_manager(db, accounts)

with tabs[3]:
    budgets_view(db)

with tabs[4]:
    recurring_view(db, accounts)

with tabs[5]:
    accounts_categories_view(db)

with tabs[6]:
    import_export_view(db, accounts)
