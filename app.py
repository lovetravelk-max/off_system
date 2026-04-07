import streamlit as st
import sqlite3
import google.generativeai as genai
import pandas as pd
from datetime import datetime
import json
import re

# --- 1. CONFIG ---
st.set_page_config(page_title="SME Insurance System", layout="wide")

if "GOOGLE_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
else:
    st.error("Missing API Key in Secrets!")

# --- 2. DATABASE ENGINE ---
DB_NAME = 'sme_insurance.db'

def init_db():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS policies
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  client_id TEXT, agent_id TEXT, insurer_id TEXT,
                  premium REAL, ia_levy REAL, ec_levy REAL, 
                  agent_payout REAL, co_profit REAL, created_at TEXT)''')
    c.execute('CREATE TABLE IF NOT EXISTS clients (id TEXT PRIMARY KEY, name TEXT, addr TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS agents (id TEXT PRIMARY KEY, name TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS insurers (id TEXT PRIMARY KEY, name TEXT)')
    conn.commit()
    conn.close()

init_db()

def get_master_data(table):
    conn = sqlite3.connect(DB_NAME)
    try:
        return pd.read_sql_query(f"SELECT id, name FROM {table}", conn)
    except:
        return pd.DataFrame(columns=['id', 'name'])
    finally:
        conn.close()

# --- 3. THE "VISION" EXTRACTION ENGINE ---
def extract_data(pdf_file):
    # Force use of 1.5-flash for OCR/Vision capabilities
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    # Read the file bytes
    file_bytes = pdf_file.read()
    
    prompt = """
    Analyze this insurance document carefully. Extract the following values and return them in RAW JSON format. 
    Look for keywords like 'Policyholder', 'Sum Payable', 'Levy', 'Insurer'.
    
    Return this exact JSON structure:
    {
      "insurer": "Company Name",
      "insured_name": "Full Client Name",
      "premium": 0.0,
      "ia_levy": 0.0,
      "ec_levy": 0.0,
      "address": "Full Correspondence Address"
    }
    
    Note: If a value is missing, use 0 for numbers and "N/A" for text. Return ONLY JSON.
    """
    
    try:
        # We pass the bytes directly as a PDF blob
        response = model.generate_content([
            prompt,
            {"mime_type": "application/pdf", "data": file_bytes}
        ])
        
        # Robust JSON cleaning
        res_text = response.text
        # Find the first { and last }
        start = res_text.find('{')
        end = res_text.rfind('}') + 1
        json_str = res_text[start:end]
        
        return json.loads(json_str)
    except Exception as e:
        st.error(f"AI Extraction Failed: {e}")
        return {}

# --- 4. MAIN INTERFACE ---
st.title("🛡️ SME Insurance Management System")

# Load Master Lists
df_clients = get_master_data("clients")
df_agents = get_master_data("agents")
df_insurers = get_master_data("insurers")

tab1, tab2, tab3 = st.tabs(["Create Debit Note", "Master Lists", "History"])

with tab1:
    # Initialize the "Brain" of the form if it doesn't exist
    if "ai_data" not in st.session_state:
        st.session_state.ai_data = {}

    uploaded_file = st.file_uploader("Upload Policy PDF", type="pdf")
    
    if uploaded_file:
        if st.button("🔍 Run AI Scan"):
            with st.spinner("Analyzing document structure..."):
                extracted = extract_data(uploaded_file)
                if extracted:
                    st.session_state.ai_data = extracted
                    st.success("Data Pulled! Check the fields below.")
                    st.rerun() # Force UI refresh to fill boxes

    st.divider()
    
    # UI Layout using session_state to fill values
    col1, col2, col3 = st.columns(3)

    with col1:
        st.subheader("👤 Client")
        c_list = ["+ ADD NEW"] + df_clients['id'].tolist()
        c_sel = st.selectbox("Client Code", c_list)
        
        if c_sel == "+ ADD NEW":
            c_id = st.text_input("New Client ID")
            c_name = st.text_input("Client Name", value=st.session_state.ai_data.get("insured_name", ""))
        else:
            c_id = c_sel
            c_name = df_clients[df_clients['id'] == c_id]['name'].values[0]
        
        c_addr = st.text_area("Address", value=st.session_state.ai_data.get("address", ""))

    with col2:
        st.subheader("🤵 Agent")
        a_list = ["+ ADD NEW"] + df_agents['id'].tolist()
        a_sel = st.selectbox("Agent Code", a_list)
        a_id = st.text_input("New Agent ID") if a_sel == "+ ADD NEW" else a_sel
        a_name = st.text_input("Agent Name") if a_sel == "+ ADD NEW" else df_agents[df_agents['id'] == a_id]['name'].values[0]

    with col3:
        st.subheader("🏢 Insurer")
        i_list = ["+ ADD NEW"] + df_insurers['id'].tolist()
        i_sel = st.selectbox("Insurer Code", i_list)
        i_id = st.text_input("New Insurer ID") if i_sel == "+ ADD NEW" else i_sel
        i_name = st.text_input("Insurer Name", value=st.session_state.ai_data.get("insurer", "")) if i_sel == "+ ADD NEW" else df_insurers[df_insurers['id'] == i_id]['name'].values[0]

    st.divider()
    
    # Premium & Split logic
    m1, m2 = st.columns(2)
    with m1:
        # Defaulting numbers to 0.0 if not found
        prem = st.number_input("Premium", value=float(st.session_state.ai_data.get("premium", 0.0)))
        ia = st.number_input("IA Levy", value=float(st.session_state.ai_data.get("ia_levy", 0.0)))
        ec = st.number_input("EC Levy", value=float(st.session_state.ai_data.get("ec_levy", 0.0)))
        st.info(f"Total Billable: ${prem + ia + ec:,.2f}")
    
    with m2:
        rate = st.number_input("Comm %", value=15.0)
        split = st.number_input("Agent Split %", value=60.0)
        disc = st.number_input("Discount $", value=0.0)
        mode = st.radio("Discount from:", ["Company", "Agent", "Proportional"])

    # Basic Split Logic
    total_comm = prem * (rate/100)
    raw_a = total_comm * (split/100)
    raw_c = total_comm - raw_a
    
    if mode == "Company": f_a, f_c = raw_a, raw_c - disc
    elif mode == "Agent": f_a, f_c = raw_a - disc, raw_c
    else: 
        f_a = raw_a - (disc * (split/100))
        f_c = raw_c - (disc * (1 - split/100))

    st.write(f"**Agent Payout:** ${f_a:,.2f} | **Company Profit:** ${f_c:,.2f}")

    if st.button("💾 Save Record"):
        conn = sqlite3.connect(DB_NAME)
        conn.execute("INSERT OR REPLACE INTO clients VALUES (?,?,?)", (c_id, c_name, c_addr))
        conn.execute("INSERT OR REPLACE INTO agents VALUES (?,?)", (a_id, a_name))
        conn.execute("INSERT OR REPLACE INTO insurers VALUES (?,?)", (i_id, i_name))
        conn.execute("INSERT INTO policies (client_id, agent_id, insurer_id, premium, ia_levy, ec_levy, agent_payout, co_profit, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                     (c_id, a_id, i_id, prem, ia, ec, f_a, f_c, datetime.now().strftime("%Y-%m-%d")))
        conn.commit()
        conn.close()
        st.success("Saved!")
        st.session_state.ai_data = {} # Reset for next one
        st.rerun()
