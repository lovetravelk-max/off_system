import streamlit as st
import sqlite3
import google.generativeai as genai
import pandas as pd
from datetime import datetime
import json

# --- 1. SETTINGS & AI CONFIG ---
st.set_page_config(page_title="SME Insurance System", layout="wide")

# Configure Gemini (Ensure GOOGLE_API_KEY is in your Streamlit Secrets)
if "GOOGLE_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
else:
    st.error("Please add GOOGLE_API_KEY to your Streamlit Secrets.")

# --- 2. SQLITE DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect('sme_insurance.db', check_same_thread=False)
    c = conn.cursor()
    # Create table with all the fields you need for accounting
    c.execute('''CREATE TABLE IF NOT EXISTS policies
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  client_code TEXT, 
                  agent_code TEXT, 
                  insured_name TEXT, 
                  policy_class TEXT,
                  premium_ex_levy REAL, 
                  insurer_comm_pct REAL,
                  total_insurer_comm REAL,
                  agent_split_pct REAL,
                  discount REAL,
                  final_agent_payout REAL, 
                  final_co_profit REAL,
                  created_at TEXT)''')
    conn.commit()
    conn.close()

init_db()

def save_to_db(data_tuple):
    conn = sqlite3.connect('sme_insurance.db', check_same_thread=False)
    c = conn.cursor()
    query = '''INSERT INTO policies 
               (client_code, agent_code, insured_name, policy_class, premium_ex_levy, 
                insurer_comm_pct, total_insurer_comm, agent_split_pct, discount, 
                final_agent_payout, final_co_profit, created_at) 
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)'''
    c.execute(query, data_tuple)
    conn.commit()
    conn.close()

# --- 3. AI EXTRACTION FUNCTION ---
def extract_data_from_pdf(pdf_file):
    model = genai.GenerativeModel('gemini-1.5-flash')
    pdf_content = pdf_file.read()
    
    prompt = """
    Extract data from this insurance policy. 
    Return ONLY a JSON object with these keys: 
    "insured_name", "premium", "policy_class", "policy_period".
    If not found, use "N/A". Do not store this data.
    """
    
    response = model.generate_content([
        prompt, 
        {"mime_type": "application/pdf", "data": pdf_content}
    ])
    
    # Clean the response to ensure it's valid JSON
    clean_json = response.text.replace("```json", "").replace("```", "").strip()
    return json.loads(clean_json)

# --- 4. APP INTERFACE ---
st.title("🛡️ SME Insurance Management System")

tab1, tab2, tab3 = st.tabs(["New Policy (AI)", "Accounting Reports", "System Backup"])

with tab1:
    st.header("Step 1: AI Policy Extraction")
    uploaded_file = st.file_uploader("Upload Policy PDF", type="pdf")
    
    # Initialize session state for AI data so it persists
    if "ai_data" not in st.session_state:
        st.session_state.ai_data = {"insured_name": "", "premium": 0.0, "policy_class": ""}

    if uploaded_file:
        if st.button("Run Privacy-First Extraction"):
            with st.spinner("AI is analyzing..."):
                try:
                    st.session_state.ai_data = extract_data_from_pdf(uploaded_file)
                    st.success("Data Extracted!")
                except Exception as e:
                    st.error(f"AI Error: {e}")

    st.divider()
    
    st.header("Step 2: Backend & Commission Logic")
    col1, col2 = st.columns(2)
    
    with col1:
        insured_name = st.text_input("Insured Name", value=st.session_state.ai_data.get("insured_name"))
        p_class = st.text_input("Insurance Class", value=st.session_state.ai_data.get("policy_class"))
        client_code = st.text_input("Client Code (Manual)")
        agent_code = st.text_input("Agent Code (Manual)")

    with col2:
        premium_ex_levy = st.number_input("Premium (Excl. Levy)", value=float(st.session_state.ai_data.get("premium", 0) or 0))
        comm_rate_pct = st.number_input("Insurer Comm Rate %", value=15.0)
        total_insurer_comm = premium_ex_levy * (comm_rate_pct / 100)
        st.info(f"Total Comm from Insurer: ${total_insurer_comm:,.2f}")

    st.subheader("Internal Split & Discount")
    col_a, col_b = st.columns(2)
    with col_a:
        agent_split_pct = st.number_input("Agent Split % (e.g. 60)", value=60.0)
        discount = st.number_input("Client Discount ($)", value=0.0)
    
    with col_b:
        discount_target = st.radio("Deduct Discount From:", ["Company Profit Only", "Agent Share Only", "Proportional"])

    # --- CALCULATIONS ---
    raw_agent_share = total_insurer_comm * (agent_split_pct / 100)
    raw_co_share = total_insurer_comm - raw_agent_share

    if discount_target == "Company Profit Only":
        final_agent_payout = raw_agent_share
        final_co_profit = raw_co_share - discount
    elif discount_target == "Agent Share Only":
        final_agent_payout = raw_agent_share - discount
        final_co_profit = raw_co_share
    else: # Proportional
        final_agent_payout = raw_agent_share - (discount * (agent_split_pct/100))
        final_co_profit = total_insurer_comm - final_agent_payout - discount

    st.write(f"**Final Results:** Agent Payout: ${final_agent_payout:,.2f} | Company Profit: ${final_co_profit:,.2f}")

    if st.button("Save Record & Finalize"):
        data = (client_code, agent_code, insured_name, p_class, premium_ex_levy, 
                comm_rate_pct, total_insurer_comm, agent_split_pct, discount, 
                final_agent_payout, final_co_profit, datetime.now().strftime("%Y-%m-%d %H:%M"))
        save_to_db(data)
        st.success("Saved to SQLite Database!")

with tab2:
    st.header("📊 Accounting Report")
    conn = sqlite3.connect('sme_insurance.db')
    df = pd.read_sql_query("SELECT * FROM policies", conn)
    conn.close()
    
    if not df.empty:
        st.dataframe(df)
        st.download_button("Export to Excel (CSV)", df.to_csv(index=False), "accounting_report.csv")
    else:
        st.info("No records found yet.")

with tab3:
    st.header("⚙️ System Backup")
    st.write("Since this is an SME system, you can download the entire database file here for offline backup.")
    with open("sme_insurance.db", "rb") as f:
        st.download_button("Download Database File (.db)", f, "offline_backup.db")
