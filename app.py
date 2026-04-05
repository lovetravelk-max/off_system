import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect('agency_system.db')
    c = conn.cursor()
    # Create table for policies and commissions
    c.execute('''CREATE TABLE IF NOT EXISTS policies
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  client_code TEXT, agent_code TEXT, 
                  insured_name TEXT, premium REAL, 
                  total_comm REAL, agent_comm REAL, co_profit REAL,
                  created_at TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- APP UI ---
st.set_page_config(page_title="SME Insurance System", layout="wide")
st.title("🛡️ SME Insurance Management System")

# Sidebar for Navigation
menu = ["Data Entry (AI)", "Accounting Reports", "System Backup"]
choice = st.sidebar.selectbox("Menu", menu)

if choice == "Data Entry (AI)":
    st.subheader("1. Upload Policy PDF")
    uploaded_file = st.file_uploader("Choose a PDF file", type="pdf")
    
    if uploaded_file:
        # --- THIS IS WHERE YOUR AI EXTRACTION CODE LIVES ---
        st.info("AI is extracting data... (Simulated for now)")
        
        # Simulated Extracted Data
        extracted_data = {
            "insured": "Sample Corp Ltd",
            "premium": 5000.00,
            "class": "Public Liability"
        }
        
        # --- BACKEND SYSTEM FORM ---
        st.subheader("2. Backend System Verification")
        col1, col2 = st.columns(2)
        
        with col1:
            client_name = st.text_input("Insured Name", value=extracted_data['insured'])
            client_code = st.text_input("Client Code (Manual)", "C123")
            agent_code = st.text_input("Agent Code (Manual)", "A01")
        
        with col2:
            premium = st.number_input("Gross Premium ($)", value=extracted_data['premium'])
            agent_split = st.slider("Agent Commission Split %", 0, 100, 50)

        # Calculations
        total_comm = premium * 0.20  # Example 20% commission
        agent_comm = total_comm * (agent_split / 100)
        co_profit = total_comm - agent_comm

        st.write(f"**Calculated Profit:** Company: ${co_profit:,.2f} | Agent: ${agent_comm:,.2f}")

        if st.button("Save to System & Generate Debit Notes"):
            conn = sqlite3.connect('agency_system.db')
            c = conn.cursor()
            c.execute("INSERT INTO policies (client_code, agent_code, insured_name, premium, total_comm, agent_comm, co_profit, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                      (client_code, agent_code, client_name, premium, total_comm, agent_comm, co_profit, datetime.now()))
            conn.commit()
            conn.close()
            st.success("Record saved to Offline Database!")

elif choice == "Accounting Reports":
    st.subheader("📊 Financial Overview")
    conn = sqlite3.connect('agency_system.db')
    df = pd.read_sql_query("SELECT * FROM policies", conn)
    conn.close()
    
    if not df.empty:
        st.dataframe(df)
        st.download_button("Download CSV (Offline Server Backup)", df.to_csv(), "accounting_report.csv")
    else:
        st.warning("No data found in the system yet.")
