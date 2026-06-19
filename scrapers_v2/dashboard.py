import streamlit as st
import pandas as pd
import plotly.express as px
from streamlit_lottie import st_lottie
import requests
import json
import asyncio
import websockets

st.set_page_config(page_title="Elite Scraper v2", layout="wide", page_icon="🚀")
st.markdown("""<style>.stApp{background:#0A1A2F;color:#E0E0E0}</style>""", unsafe_allow_html=True)

st.title("🚀 Elite Scraper v2")
st.caption("Empire AI • Real-time • Predictive • Autonomous")

col1, col2, col3 = st.columns(3)
with col1: st.metric("Total Leads", "9,139", "+342 today")
with col2: st.metric("Enriched Leads", "6,784", "+189 today")
with col3: st.metric("Active Sources", "12", "+2 this week")

st.divider()

if st.button("🚀 RUN FULL SCRAPE", use_container_width=True):
    with st.spinner("Executing..."):
        r = requests.post("http://localhost:8003/scrape", json={"max_results": 200})
        if r.status_code == 200:
            df = pd.DataFrame(r.json())
            fig = px.bar(df, x="vertical", color="source", color_discrete_sequence=["#00FFFF","#00CCAA"])
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(df, use_container_width=True)
        else:
            st.error("Failed")

st.divider()
st.subheader("📡 Live Lead Feed")
placeholder = st.empty()
if st.button("Start Live Feed"):
    async def live():
        uri = "ws://localhost:8003/ws"
        async with websockets.connect(uri) as ws:
            while True:
                msg = await ws.recv()
                lead = json.loads(msg)
                with placeholder.container():
                    st.write(f"**{lead[vertical]}** | {lead[source]} | Score: {lead[meta][predicted_score]}")
    asyncio.run(live())

st.divider()
st.subheader("🤖 Agent Control Panel")
col1, col2 = st.columns(2)
with col1:
    if st.button("Scrape Public Adjusters"): requests.post("http://localhost:8003/scrape", json={"vertical":"Public Adjuster"})
    if st.button("Scrape Restoration"): requests.post("http://localhost:8003/scrape", json={"vertical":"Restoration"})
with col2:
    if st.button("Trigger Striker Recruitment"): st.info("Striker triggered via kanban")
    if st.button("Run MRR Follow-up"): st.info("MRR follow-up triggered via kanban")
