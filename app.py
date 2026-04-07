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

# --- 3. UPDATED AI EXTRACTION (Fixed 404 Error) ---
def extract_data(pdf_file):
    # We use 'gemini-1.5-flash' without the 'models/' prefix to be safe
    model = genai.GenerativeModel('gemini-1.5-flash')
    pdf_content = pdf_file.read()
    
    prompt = """
    Extract as raw JSON only: 
    {"insurer": "", "insured_name": "", "class": "", "premium": 0, "ia_levy": 0, "ec_levy": 0, "address": ""}
    If a value is missing, use 0 for numbers or "N/A" for text.
    """
    
    # Adding a try-except block here specifically for the AI call
    try:
        response = model.generate_content([
            prompt, 
            {"mime_type": "application/pdf", "data": pdf_content}
        ])
        # Clean the response text
        res_text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(res_text)
    except Exception as e:
        st.error(f"AI could not read this PDF automatically. Error: {e}")
        return {}

# --- 4. MAIN INTERFACE ---
st.title("🛡️ SME Insurance Management System")

# Refresh lists
df_clients = get_master_data("clients")
df_agents = get_master_data("agents")
df_insurers = get_master_data("insurers")

tab1, tab2, tab3 = st.tabs(["Create Debit Note", "Master Data", "Reports"])

with tab1:
    uploaded_file = st.file_uploader("Upload Policy PDF", type="pdf")
    if "ai" not in st.session_state: st.session_state.ai = {}

    if uploaded_file and st.button("🔍 AI Scan Policy"):
        with st.spinner("Connecting to Google AI..."):
            st.session_state.ai = extract_data(uploaded_file)
            if st.session_state.ai:
                st.success("AI extraction successful!")
            st.rerun()

    st.divider()
    
    col1, col2, col3 = st.columns(3)

    with col1:
        st.subheader("👤 Client")
        c_list = ["+ ADD NEW"] + df_clients['id'].tolist()
        c_search = st.selectbox("Search Client Code", c_list)
        if c_search == "+ ADD NEW":
            c_id = st.text_input("New Client Code (e.g. C001)")
            c_name = st.text_input("Client Name", value=st.session_state.ai.get("insured_name", ""))
        else:
            c_id = c_search
            c_name = df_clients[df_clients['id'] == c_id]['name'].values[0]
            st.info(f"Selected: {c_name}")
        c_addr = st.text_area("Address", value=st.session_state.ai.get("address", ""))

    with col2:
        st.subheader("🤵 Agent")
        a_list = ["+ ADD NEW"] + df_agents['id'].tolist()
        a_search = st.selectbox("Search Agent Code", a_list)
        if a_search == "+ ADD NEW":
            a_id = st.text_input("New Agent Code")
            a_name = st.text_input("Agent Name")
        else:
            a_id = a_search
            a_name = df_agents[df_agents['id'] == a_id]['name'].values[0]
            st.info(f"Selected: {a_name}")

    with col3:
        st.subheader("🏢 Insurer")
        i_list = ["+ ADD NEW"] + df_insurers['id'].tolist()
        i_search = st.selectbox("Search Insurer Code", i_list)
        if i_search == "+ ADD NEW":
            i_id = st.text_input("New Insurer Code")
            i_name = st.text_input("Insurer Name", value=st.session_state.ai.get("insurer", ""))
        else:
            i_id = i_search
            i_name = df_insurers[df_insurers['id'] == i_id]['name'].values[0]
            st.info(f"Selected: {i_name}")

    st.divider()
    
    m1, m2 = st.columns(2)
    with m1:
        prem = st.number_input("Premium", value=float(st.session_state.ai.get("premium", 0)))
        ia = st.number_input("IA Levy", value=float(st.session_state.ai.get("ia_levy", 0)))
        ec = st.number_input("EC Levy", value=float(st.session_state.ai.get("ec_levy", 0)))
    
    with m2:
        rate = st.number_input("Comm %", value=15.0)
        split = st.number_input("Agent Split %", value=60.0)
        disc = st.number_input("Discount $", value=0.0)
        mode = st.radio("Deduct Discount From:", ["Company Profit Only", "Agent Share Only", "Proportional"])

    # Calculations
    total_comm = prem * (rate/100)
    raw_a, raw_c = total_comm * (split/100), total_comm * (1 - split/100)
    
    if mode == "Company Profit Only": f_a, f_c = raw_a, raw_c - disc
    elif mode == "Agent Share Only": f_a, f_c = raw_a - disc, raw_c
    else: f_a, f_c = raw_a - (disc * (split/100)), raw_c - (disc * (1-split/100))

    st.write(f"### Net: Agent ${f_a:,.2f} | Company ${f_c:,.2f}")

    if st.button("💾 Save Transaction"):
        conn = sqlite3.connect(DB_NAME)
        conn.execute("INSERT OR REPLACE INTO clients VALUES (?,?,?)", (c_id, c_name, c_addr))
        conn.execute("INSERT OR REPLACE INTO agents VALUES (?,?)", (a_id, a_name))
        conn.execute("INSERT OR REPLACE INTO insurers VALUES (?,?)", (i_id, i_name))
        conn.execute("INSERT INTO policies (client_id, agent_id, insurer_id, premium, ia_levy, ec_levy, agent_payout, co_profit, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                     (c_id, a_id, i_id, prem, ia, ec, f_a, f_c, datetime.now().strftime("%Y-%m-%d")))
        conn.commit()
        conn.close()
        st.success("Debit Note Saved!")
        st.rerun()

with tab2:
    st.subheader("📋 System Master Lists")
    cl1, cl2, cl3 = st.columns(3)
    with cl1: st.write("**Clients**"); st.dataframe(df_clients)
    with cl2: st.write("**Agents**"); st.dataframe(df_agents)
    with cl3: st.write("**Insurers**"); st.dataframe(df_insurers)

with tab3:
    st.subheader("📊 Accounting Report")
    conn = sqlite3.connect(DB_NAME)
    df_p = pd.read_sql_query("SELECT * FROM policies", conn)
    conn.close()
    st.dataframe(df_p)
    st.download_button("Download Database Backup", open(DB_NAME, "rb"), "sme_backup.db")
