# Financial App

A Streamlit personal finance tracker backed by MongoDB Atlas.

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
