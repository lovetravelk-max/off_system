import streamlit as st
import sqlite3
import google.generativeai as genai
import pandas as pd
from datetime import datetime
import json

# --- 1. CONFIG ---
st.set_page_config(page_title="SME Insurance System", layout="wide")
if "GOOGLE_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])

# --- 2. DATABASE ENGINE (Added Agent & Insurer Tables) ---
def init_db():
    conn = sqlite3.connect('sme_insurance.db', check_same_thread=False)
    c = conn.cursor()
    # Policies
    c.execute('''CREATE TABLE IF NOT EXISTS policies
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  client_id TEXT, agent_id TEXT, insurer_id TEXT,
                  premium REAL, ia_levy REAL, ec_levy REAL, 
                  agent_payout REAL, co_profit REAL, created_at TEXT)''')
    # Master Data Tables
    c.execute('CREATE TABLE IF NOT EXISTS clients (id TEXT PRIMARY KEY, name TEXT, addr TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS agents (id TEXT PRIMARY KEY, name TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS insurers (id TEXT PRIMARY KEY, name TEXT)')
    conn.commit()
    conn.close()

init_db()

# --- 3. AI EXTRACTION ---
def extract_data(pdf_file):
    model = genai.GenerativeModel('gemini-1.5-flash')
    pdf_content = pdf_file.read()
    prompt = """Extract as JSON: "insurer", "insured_name", "class", "premium", "ia_levy", "ec_levy", "address". Use 0 for missing numbers."""
    response = model.generate_content([prompt, {"mime_type": "application/pdf", "data": pdf_content}])
    return json.loads(response.text.replace("```json", "").replace("```", "").strip())

# --- 4. UI HELPER FUNCTIONS ---
def get_master_data(table):
    conn = sqlite3.connect('sme_insurance.db')
    df = pd.read_sql_query(f"SELECT id, name FROM {table}", conn)
    conn.close()
    return df

# --- 5. MAIN APP ---
st.title("🛡️ SME Insurance Management System")

tab1, tab2, tab3 = st.tabs(["Create Debit Note", "Master Data (Lists)", "Accounting"])

with tab1:
    uploaded_file = st.file_uploader("Upload Policy PDF", type="pdf")
    if "ai" not in st.session_state: st.session_state.ai = {}

    if uploaded_file and st.button("🔍 AI Scan Policy"):
        with st.spinner("AI analyzing..."):
            st.session_state.ai = extract_data(uploaded_file)
            st.rerun()

    st.divider()
    
    # FETCH LISTS FOR SEARCH/DROPDOWNS
    df_clients = get_master_data("clients")
    df_agents = get_master_data("agents")
    df_insurers = get_master_data("insurers")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.subheader("👤 Client")
        c_search = st.selectbox("Search Client List", ["+ ADD NEW"] + df_clients['id'].tolist())
        if c_search == "+ ADD NEW":
            c_id = st.text_input("New Client Code")
            c_name = st.text_input("Client Name", value=st.session_state.ai.get("insured_name", ""))
        else:
            c_id = c_search
            c_name = df_clients[df_clients['id'] == c_id]['name'].values[0]
            st.success(f"Selected: {c_name}")
        c_addr = st.text_area("Address", value=st.session_state.ai.get("address", ""))

    with col2:
        st.subheader("🤵 Agent")
        a_search = st.selectbox("Search Agent List", ["+ ADD NEW"] + df_agents['id'].tolist())
        if a_search == "+ ADD NEW":
            a_id = st.text_input("New Agent Code")
            a_name = st.text_input("Agent Name")
        else:
            a_id = a_search
            a_name = df_agents[df_agents['id'] == a_id]['name'].values[0]
            st.success(f"Selected: {a_name}")

    with col3:
        st.subheader("🏢 Insurer")
        i_search = st.selectbox("Search Insurer List", ["+ ADD NEW"] + df_insurers['id'].tolist())
        if i_search == "+ ADD NEW":
            i_id = st.text_input("New Insurer Code")
            i_name = st.text_input("Insurer Name", value=st.session_state.ai.get("insurer", ""))
        else:
            i_id = i_search
            i_name = df_insurers[df_insurers['id'] == i_id]['name'].values[0]
            st.success(f"Selected: {i_name}")

    st.divider()
    
    # MATH SECTION
    m_col1, m_col2 = st.columns(2)
    with m_col1:
        prem = st.number_input("Premium", value=float(st.session_state.ai.get("premium", 0)))
        ia = st.number_input("IA Levy", value=float(st.session_state.ai.get("ia_levy", 0)))
        ec = st.number_input("EC Levy", value=float(st.session_state.ai.get("ec_levy", 0)))
        st.info(f"Total Billable: ${prem + ia + ec:,.2f}")
    
    with m_col2:
        rate = st.number_input("Comm %", value=15.0)
        split = st.number_input("Agent Split %", value=60.0)
        disc = st.number_input("Discount $", value=0.0)
        mode = st.radio("Discount from:", ["Company", "Agent", "Proportional"])

    # Calculations
    total_comm = prem * (rate/100)
    raw_a, raw_c = total_comm * (split/100), total_comm * (1 - split/100)
    
    if mode == "Company": f_a, f_c = raw_a, raw_c - disc
    elif mode == "Agent": f_a, f_c = raw_a - disc, raw_c
    else: f_a, f_c = raw_a - (disc * (split/100)), raw_c - (disc * (1-split/100))

    if st.button("✅ Generate Debit Note & Save"):
        conn = sqlite3.connect('sme_insurance.db')
        # Save Master Data if new
        conn.execute("INSERT OR REPLACE INTO clients VALUES (?,?,?)", (c_id, c_name, c_addr))
        conn.execute("INSERT OR REPLACE INTO agents VALUES (?,?)", (a_id, a_name))
        conn.execute("INSERT OR REPLACE INTO insurers VALUES (?,?)", (i_id, i_name))
        # Save Policy
        conn.execute("INSERT INTO policies (client_id, agent_id, insurer_id, premium, ia_levy, ec_levy, agent_payout, co_profit, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                     (c_id, a_id, i_id, prem, ia, ec, f_a, f_c, datetime.now().strftime("%Y-%m-%d")))
        conn.commit()
        conn.close()
        st.success("Debit Note Recorded!")

with tab2:
    st.subheader("Existing Client List")
    st.dataframe(get_master_data("clients"))
    st.subheader("Existing Agent List")
    st.dataframe(get_master_data("agents"))

with tab3:
    conn = sqlite3.connect('sme_insurance.db')
    df_p = pd.read_sql_query("SELECT * FROM policies", conn)
    conn.close()
    st.dataframe(df_p)
