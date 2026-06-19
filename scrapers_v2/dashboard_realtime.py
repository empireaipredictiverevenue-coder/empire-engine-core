import streamlit as st
import pandas as pd
import plotly.express as px
from streamlit_lottie import st_lottie
import requests
import asyncio
import websockets
import json

st.set_page_config(page_title="Elite Scraper v2", layout="wide", page_icon="🚀")

st.markdown("""
<style>
    .stApp { background-color: #0A1A2F; color: #E0E0E0; }
    .stButton>button { background: linear-gradient(90deg, #00FFFF, #00CCAA); color: #0A1A2F; font-weight: 700; }
</style>
""", unsafe_allow_html=True)

st.title("🚀 Elite Scraper v2 — Live")
st.caption("Empire AI • Real-time • Predictive • Autonomous")

# Live metrics
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Total Leads", "9,139", "+342 today")
with col2:
    st.metric("Enriched Leads", "6,784", "+189 today")
with col3:
    st.metric("Active Sources", "12", "+2 this week")

st.divider()

# Real-time lead feed
st.subheader("📡 Live Lead Feed")

if st.button("Start Live Feed"):
    placeholder = st.empty()
    async def live_feed():
        uri = "ws://localhost:8003/ws"
        async with websockets.connect(uri) as websocket:
            while True:
                message = await websocket.recv()
                lead = json.loads(message)
                with placeholder.container():
                    st.write(f"**{lead[vertical]}** | {lead[source]} | Score: {lead[meta][predicted_score]}")
    asyncio.run(live_feed())
