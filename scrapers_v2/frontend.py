import streamlit as st
import requests
import pandas as pd

st.set_page_config(page_title="Elite Scraper v2", layout="wide")
st.title("Elite Scraper v2 — Dashboard")

col1, col2 = st.columns(2)

with col1:
    if st.button("Run Full Scrape"):
        with st.spinner("Scraping..."):
            r = requests.post("http://localhost:8003/scrape", json={"max_results": 100})
            if r.status_code == 200:
                data = r.json()
                st.success(f"Found {len(data)} leads")
                df = pd.DataFrame(data)
                st.dataframe(df)
            else:
                st.error("Scrape failed")

with col2:
    st.metric("API Status", "Running" if requests.get("http://localhost:8003/health").status_code == 200 else "Down")

st.caption("Metrics available on :8002 (Prometheus)")
