# Financial App

A Streamlit personal finance tracker backed by MongoDB Atlas.

## Features

- Dashboard with monthly income, expenses, net cashflow, reimbursements, and charts
- Expense, income, and transfer transaction entry
- Transaction search/filter, edit, and delete
- Account and category management
- Monthly category budgets with spend and remaining views
- Recurring transaction rules
- Reimbursement and refund status tracking
- CSV import and export
- Demo data seeding for local or hosted testing

## Streamlit Community Cloud setup

Add these values in the app's Streamlit Secrets:

```toml
[mongodb]
uri = "mongodb+srv://USERNAME:PASSWORD@cluster.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
database = "finance_app"
```

Do not commit `.streamlit/secrets.toml`. The app reads credentials from `st.secrets`.

## Local run

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

To add demo records:

```bash
python seed_demo_data.py tianwin
python seed_demo_data.py meng
```
