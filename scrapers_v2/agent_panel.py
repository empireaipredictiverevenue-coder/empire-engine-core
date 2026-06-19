import streamlit as st
import requests
st.set_page_config(page_title="Agent Control Panel")
st.title("🤖 Agent Control Panel")
if st.button("Scrape Public Adjusters"): requests.post("http://localhost:8003/scrape", json={"vertical":"Public Adjuster"})
if st.button("Scrape Restoration"): requests.post("http://localhost:8003/scrape", json={"vertical":"Restoration"})
if st.button("Trigger Striker Recruitment"): st.info("Striker triggered via kanban")
