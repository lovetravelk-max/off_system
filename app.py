import streamlit as st
import sqlite3
import google.generativeai as genai
import pandas as pd
from datetime import datetime
import json
import re

# --- 1. CONFIG & API SETUP ---
st.set_page_config(page_title="SME Insurance System", layout="wide")

if "GOOGLE_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
else:
    st.error("Missing API Key! Please add GOOGLE_API_KEY to your Streamlit Secrets.")

# --- 2. DATABASE ENGINE ---
DB_NAME = 'sme_insurance.db'

def init_db():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    c = conn.cursor()
    # Policies Table
    c.execute('''CREATE TABLE IF NOT EXISTS policies
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  client_id TEXT, agent_id TEXT, insurer_id TEXT,
                  premium REAL, ia_levy REAL, ec_levy REAL, 
                  created_at TEXT)''')
    # Master Data Tables
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

# --- 3. AI EXTRACTION ENGINE ---
def extract_data(pdf_file):
    model = genai.GenerativeModel('gemini-1.5-flash')
    pdf_file.seek(0)
    file_bytes = pdf_file.read()
    
    prompt = """
    Analyze this insurance document. Extract the following and return ONLY raw JSON:
    {
      "insurer": "Company Name",
      "insured_name": "Client Name",
      "premium": 0.0,
      "ia_levy": 0.0,
      "ec_levy": 0.0,
      "address": "Correspondence Address"
    }
    Use 0 for missing numbers. No currency symbols.
    """
    
    try:
        response = model.generate_content([
            prompt,
            {"mime_type": "application/pdf", "data": file_bytes}
        ])
        # Find JSON block using Regex
        match = re.search(r'\{.*\}', response.text, re.DOTALL)
        if match:
            return json.loads(match.group())
        return {}
    except Exception as e:
        st.error(f"AI Error: {e}")
        return {}

# --- 4. MAIN INTERFACE ---
st.title("🛡️ SME Insurance Management System")

# Refresh database lists
df_clients = get_master_data("clients")
df_agents = get_master_data("agents")
df_insurers = get_master_data("insurers")

# Initialize Session State for AI data
if "ai_data" not in st.session_state:
    st.session_state.ai_data = {
        "insured_name": "", "insurer": "", "address": "",
        "premium": 0.0, "ia_levy": 0.0, "ec_levy": 0.0
    }

tab1, tab2, tab3 = st.tabs(["🆕 Create Debit Note", "📋 Master Lists", "📊 Reports"])

with tab1:
    # --- UPLOAD & SCAN ---
    uploaded_file = st.file_uploader("Upload Policy PDF", type="pdf")
    
    if uploaded_file:
        if st.button("🔍 Run AI Scan"):
            with st.spinner("AI is reading the policy..."):
                result = extract_data(uploaded_file)
                if result:
                    st.session_state.ai_data.update(result)
                    st.success("Data Pulled! Fields updated below.")
                    st.rerun()

    st.divider()
    
    # --- DATA ENTRY & EDITING ---
    col1, col2, col3 = st.columns(3)

    with col1:
        st.subheader("👤 Client")
        c_list = ["+ ADD NEW"] + df_clients['id'].tolist()
        c_sel = st.selectbox("Search Client Code", c_list)
        
        if c_sel == "+ ADD NEW":
            c_id = st.text_input("New Client ID (Manual)")
            c_name = st.text_input("Client Name", value=st.session_state.ai_data.get("insured_name", ""))
        else:
            c_id = c_sel
            c_name = df_clients[df_clients['id'] == c_id]['name'].values[0]
            st.info(f"Existing Client: {c_name}")
            
        c_addr = st.text_area("Address", value=st.session_state.ai_data.get("address", ""))

    with col2:
        st.subheader("🤵 Agent")
        a_list = ["+ ADD NEW"] + df_agents['id'].tolist()
        a_sel = st.selectbox("Search Agent Code", a_list)
        if a_sel == "+ ADD NEW":
            a_id = st.text_input("New Agent ID")
            a_name = st.text_input("Agent Name")
        else:
            a_id = a_sel
            a_name = df_agents[df_agents['id'] == a_id]['name'].values[0]

    with col3:
        st.subheader("🏢 Insurer")
        i_list = ["+ ADD NEW"] + df_insurers['id'].tolist()
        i_sel = st.selectbox("Search Insurer Code", i_list)
        if i_sel == "+ ADD NEW":
            i_id = st.text_input("New Insurer ID")
            i_name = st.text_input("Insurer Name", value=st.session_state.ai_data.get("insurer", ""))
        else:
            i_id = i_sel
            i_name = df_insurers[df_insurers['id'] == i_id]['name'].values[0]

    st.divider()
    
    # --- PREMIUMS & CALCULATIONS ---
    m1, m2 = st.columns(2)
    with m1:
        st.write("**Policy Amounts**")
        final_prem = st.number_input("Premium", value=float(st.session_state.ai_data.get("premium", 0.0)))
        final_ia = st.number_input("IA Levy", value=float(st.session_state.ai_data.get("ia_levy", 0.0)))
        final_ec = st.number_input("EC Levy", value=float(st.session_state.ai_data.get("ec_levy", 0.0)))
        total = final_prem + final_ia + final_ec
        st.metric("Total to Client", f"${total:,.2f}")

    with m2:
        st.write("**Internal Split**")
        rate = st.number_input("Comm Rate %", value=15.0)
        split = st.number_input("Agent Payout %", value=60.0)
        
        # Simple Logic check
        total_comm = final_prem * (rate/100)
        agent_amt = total_comm * (split/100)
        st.write(f"Est. Agent Payout: **${agent_amt:,.2f}**")

    # --- SAVE ACTION ---
    if st.button("✅ Save & Update Database"):
        if not c_id or not a_id or not i_id:
            st.warning("Please ensure all Codes (Client, Agent, Insurer) are filled.")
        else:
            conn = sqlite3.connect(DB_NAME)
            # Save Master Data
            conn.execute("INSERT OR REPLACE INTO clients VALUES (?,?,?)", (c_id, c_name, c_addr))
            conn.execute("INSERT OR REPLACE INTO agents VALUES (?,?)", (a_id, a_name))
            conn.execute("INSERT OR REPLACE INTO insurers VALUES (?,?)", (i_id, i_name))
            # Save Policy
            conn.execute('''INSERT INTO policies (client_id, agent_id, insurer_id, premium, ia_levy, ec_levy, created_at) 
                         VALUES (?,?,?,?,?,?,?)''', 
                         (c_id, a_id, i_id, final_prem, final_ia, final_ec, datetime.now().strftime("%Y-%m-%d")))
            conn.commit()
            conn.close()
            st.success(f"Saved: {c_name} successfully added to database.")
            st.session_state.ai_data = {} # Reset AI data after save
            st.rerun()

with tab2:
    st.subheader("Master Data Views")
    sel_view = st.radio("Select Table", ["Clients", "Agents", "Insurers"], horizontal=True)
    if sel_view == "Clients": st.dataframe(get_master_data("clients"), use_container_width=True)
    elif sel_view == "Agents": st.dataframe(get_master_data("agents"), use_container_width=True)
    else: st.dataframe(get_master_data("insurers"), use_container_width=True)

with tab3:
    st.subheader("Historical Policy Records")
    conn = sqlite3.connect(DB_NAME)
    df_history = pd.read_sql_query("SELECT * FROM policies", conn)
    conn.close()
    st.dataframe(df_history, use_container_width=True)
