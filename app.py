import streamlit as st
import sqlite3
import google.generativeai as genai
import pandas as pd
from datetime import datetime
import json

# --- 1. CONFIG & AI SETUP ---
st.set_page_config(page_title="SME Insurance System", layout="wide")

if "GOOGLE_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
else:
    st.error("Missing GOOGLE_API_KEY in Streamlit Secrets!")

# --- 2. DATABASE ENGINE ---
def init_db():
    conn = sqlite3.connect('sme_insurance.db', check_same_thread=False)
    c = conn.cursor()
    # Policies Table
    c.execute('''CREATE TABLE IF NOT EXISTS policies
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  client_id TEXT, agent_code TEXT, insured_name TEXT, 
                  policy_class TEXT, period TEXT, premium REAL, 
                  description TEXT, agent_payout REAL, co_profit REAL, 
                  created_at TEXT)''')
    # Clients Table (The "Master List")
    c.execute('''CREATE TABLE IF NOT EXISTS clients
                 (client_id TEXT PRIMARY KEY, name TEXT, 
                  address TEXT, location TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- 3. AI EXTRACTION ENGINE ---
def extract_policy_data(pdf_file):
    model = genai.GenerativeModel('models/gemini-1.5-flash')
    pdf_content = pdf_file.read()
    
    prompt = """
    Extract these fields from the insurance policy:
    - insured_name
    - policy_class
    - policy_period
    - premium (number only, excluding levy)
    - correspondence_address
    - insured_location
    
    Return ONLY a raw JSON object. Use "N/A" if not found.
    """
    
    response = model.generate_content([
        prompt, 
        {"mime_type": "application/pdf", "data": pdf_content}
    ])
    
    # Clean JSON string
    clean_text = response.text.replace("```json", "").replace("```", "").strip()
    return json.loads(clean_text)

# --- 4. APP INTERFACE ---
st.title("🛡️ SME Insurance Management System")

# Load Client List for the dropdown
conn = sqlite3.connect('sme_insurance.db')
clients_df = pd.read_sql_query("SELECT client_id, name FROM clients", conn)
conn.close()

tab1, tab2, tab3 = st.tabs(["New Entry (AI)", "Accounting Reports", "System Backup"])

with tab1:
    st.header("Step 1: Policy Upload")
    uploaded_file = st.file_uploader("Upload Policy PDF", type="pdf")
    
    if "ai_results" not in st.session_state:
        st.session_state.ai_results = {}

    if uploaded_file and st.button("Analyze with AI"):
        with st.spinner("Extracting data..."):
            try:
                st.session_state.ai_results = extract_policy_data(uploaded_file)
                st.success("Extraction Complete!")
            except Exception as e:
                st.error(f"AI Error: {e}")

    st.divider()

    # --- BACKEND SYSTEM ---
    st.header("Step 2: Backend System Details")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("👤 Client Identification")
        client_options = ["[NEW CLIENT]"] + [f"{row['name']} ({row['client_id']})" for _, row in clients_df.iterrows()]
        client_choice = st.selectbox("Select Client from Database", client_options)
        
        # Logic for New vs Existing Client
        if client_choice == "[NEW CLIENT]":
            final_name = st.text_input("Insured Name (from AI)", value=st.session_state.ai_results.get("insured_name", ""))
            final_id = st.text_input("Assign Client Code (e.g., C001)")
        else:
            # Extract name and ID from the selection "Name (ID)"
            final_name = client_choice.split(" (")[0]
            final_id = client_choice.split(" (")[1].replace(")", "")
            st.info(f"Using Existing ID: {final_id}")

        addr = st.text_area("Correspondence Address", value=st.session_state.ai_results.get("correspondence_address", ""))
        loc = st.text_area("Insured Location", value=st.session_state.ai_results.get("insured_location", ""))

    with col2:
        st.subheader("💰 Commission & Splits")
        p_class = st.text_input("Insurance Class", value=st.session_state.ai_results.get("policy_class", ""))
        p_period = st.text_input("Policy Period", value=st.session_state.ai_results.get("policy_period", ""))
        p_desc = st.text_input("Manual Description / Remarks")
        
        premium = st.number_input("Premium (Excl. Levy)", value=float(st.session_state.ai_results.get("premium", 0) or 0))
        comm_rate = st.number_input("Insurer Comm Rate %", value=15.0)
        
        total_comm = premium * (comm_rate / 100)
        st.write(f"**Gross Comm from Insurer:** ${total_comm:,.2f}")
        
        agent_split = st.number_input("Agent Split % (e.g., 60)", value=60.0)
        discount = st.number_input("Client Discount / Rebate ($)", value=0.0)
        deduct_from = st.radio("Deduct Discount From:", ["Company Profit Only", "Agent Share Only", "Proportional Split"])

    # --- MATH LOGIC ---
    raw_agent = total_comm * (agent_split / 100)
    raw_co = total_comm - raw_agent

    if deduct_from == "Company Profit Only":
        f_agent, f_co = raw_agent, raw_co - discount
    elif deduct_from == "Agent Share Only":
        f_agent, f_co = raw_agent - discount, raw_co
    else: # Proportional
        f_agent = raw_agent - (discount * (agent_split/100))
        f_co = total_comm - f_agent - discount

    st.divider()
    res_col1, res_col2 = st.columns(2)
    res_col1.metric("Final Agent Payout", f"${f_agent:,.2f}")
    res_col2.metric("Final Company Profit", f"${f_co:,.2f}")

    if st.button("Finalize: Save & Generate Records"):
        conn = sqlite3.connect('sme_insurance.db')
        # 1. Update Client Master List
        conn.execute("INSERT OR REPLACE INTO clients VALUES (?, ?, ?, ?)", (final_id, final_name, addr, loc))
        # 2. Record the Policy Transaction
        conn.execute('''INSERT INTO policies 
                     (client_id, agent_code, insured_name, policy_class, period, premium, description, agent_payout, co_profit, created_at) 
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                     (final_id, "AGENT_01", final_name, p_class, p_period, premium, p_desc, f_agent, f_co, datetime.now().strftime("%Y-%m-%d")))
        conn.commit()
        conn.close()
        st.success(f"System Updated! Record saved for {final_name} ({final_id})")

with tab2:
    st.header("📊 Accounting Reports")
    conn = sqlite3.connect('sme_insurance.db')
    df = pd.read_sql_query("SELECT * FROM policies", conn)
    conn.close()
    if not df.empty:
        st.dataframe(df)
        st.download_button("Export Accounting CSV", df.to_csv(index=False), "accounting_report.csv")
    else:
        st.info("No records yet.")

with tab3:
    st.header("💾 Offline System Backup")
    st.write("Download your database file here to keep an offline copy of your business data.")
    with open("sme_insurance.db", "rb") as f:
        st.download_button("Download Database (.db)", f, "sme_offline_backup.db")
