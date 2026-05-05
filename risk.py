import streamlit as st
import pandas as pd
from io import BytesIO
import PyPDF2
import google.generativeai as genai
from openai import OpenAI  # 追加
import os  # 追加

st.set_page_config(page_title="RBA Risk Assessment Pro", layout="wide")

# --- セッション状態の管理 ---
if "protocol_text" not in st.session_state:
    st.session_state.protocol_text = ""
if "ai_highlights" not in st.session_state:
    st.session_state.ai_highlights = {}
if "api_ready" not in st.session_state:
    st.session_state.api_ready = False

# --- サイドバー：設定エリア ---
with st.sidebar:
    st.title("⚙️ 設定 & マスター定義")

    # 1. 接続モードの選択
    mode = st.radio("接続モード", ["Gemini (Cloud)", "LM Studio (Local)"])

    if mode == "Gemini (Cloud)":
        env_key = os.getenv("GOOGLE_API_KEY")
        api_key = st.text_input("Google API Key", value=env_key if env_key else "", type="password")
        if api_key:
            genai.configure(api_key=api_key)
            st.success("Gemini 準備完了")
            st.session_state.api_ready = True
        else:
            st.warning("API Keyを入力してください")
            st.session_state.api_ready = False
    else:
        # RTX 5070などのローカル環境用
        local_url = st.text_input("LM Studio URL", "http://localhost:1234/v1")
        st.info("LM StudioでServerを開始してください")
        try:
            st.session_state.client_local = OpenAI(base_url=local_url, api_key="lm-studio")
            st.success("Local Server 設定完了")
            st.session_state.api_ready = True
        except Exception as e:
            st.error(f"接続エラー: {e}")
            st.session_state.api_ready = False

    st.divider()
    # --- この後に 1. CTQ定義 / 2. リスク事象の特定 が続きます ---

    else:
        # RTX 5070環境などを想定したローカル接続
        local_url = st.text_input("LM Studio URL", "http://localhost:1234/v1")
        st.info("LM StudioでServerを開始してください。")
        # client_local をセッション等で保持して右側で使う
        st.session_state.client_local = OpenAI(base_url=local_url, api_key="lm-studio")
        st.success("Local Server 設定完了")

    st.divider()
    # 1. CTQ定義
    st.subheader("🎯 1. CTQの定義")
    ctq_raw = st.text_area("CTQ（1行に1つ）", 
                           value="CTQ-1: 主要評価項目の信頼性\nCTQ-2: 被験者の安全性確保", 
                           height=100)
    ctq_list = [c.strip() for c in ctq_raw.split('\n') if c.strip()]

    st.divider()

    # 2. CTQごとのリスク特定
    st.subheader("📝 2. リスク事象の特定")
    st.caption("定義したCTQごとに関連するリスクを入力してください。")
    
    risk_data_master = []
    risk_count = 1
    for ctq in ctq_list:
        with st.expander(f"📌 {ctq} のリスク", expanded=True):
            for j in range(3):
                r_name = st.text_input(f"リスク事象 {risk_count}", key=f"master_risk_{risk_count}", placeholder="事象を入力")
                if r_name:
                    risk_data_master.append({"id": risk_count, "name": r_name, "ctq": ctq})
                risk_count += 1

    st.divider()

    # 3. 要因マスター
    st.subheader("🔍 3. 要因マスター")
    factor_input = st.text_area("要因リスト（改行区切り）", 
                                value="P: 患者の認知機能\nS: 手順書の解釈相違\nH: システムUI\nE: リソース不足\nL: 手順遵守の失念", 
                                height=120)
    factor_options = [item.strip() for item in factor_input.split('\n') if item.strip()]

# --- メインエリア：2カラム ---
col_left, col_right = st.columns([1.2, 1.8])

# --- 左カラム：AI解析結果 & プロトコル参照（順序入れ替え） ---
with col_left:
    st.subheader("🤖 AI解析結果：該当箇所の特定")
    
    # 【位置入れ替え】AI推論結果を最上部に配置
    if st.session_state.ai_highlights:
        for r_idx, h_text in st.session_state.ai_highlights.items():
            r_name_label = st.session_state.get(f"master_risk_{r_idx}", "Unknown")
            with st.chat_message("assistant"):
                st.caption(f"Risk #{r_idx}: {r_name_label}")
                st.write(h_text)
    else:
        st.info("右側の解析ボタンを押すと、ここに根拠規定が抽出されます。")

    st.divider()

    # プロトコル参照を下に配置
    st.subheader("📜 プロトコル原本参照")
    uploaded_pdf = st.file_uploader("PDFをアップロード", type=["pdf"])
    if uploaded_pdf:
        try:
            pdf_reader = PyPDF2.PdfReader(BytesIO(uploaded_pdf.read()))
            text = "\n".join([page.extract_text() for page in pdf_reader.pages if page.extract_text()])
            st.session_state.protocol_text = text
        except Exception as e:
            st.error(f"Error: {e}")
    
    if st.session_state.protocol_text:
        st.text_area("PRT全文（確認用）", value=st.session_state.protocol_text, height=400, disabled=True)

# --- 右カラム：評価実行エリア ---
with col_right:
    st.subheader("📝 リスク評価実行")
    user_role = st.selectbox("評定者の職種を選択", ["CRA", "CRC", "DM", "PI", "その他"])
    
    st.divider()
    
    if not risk_data_master:
        st.warning("サイドバーでCTQとリスク事象を入力してください。")
    
    for risk in risk_data_master:
        i = risk["id"]
        r_name = risk["name"]
        r_ctq = risk["ctq"]
        
        with st.expander(f"No.{i} : {r_name} ({r_ctq})", expanded=(i==1)):
            st.markdown(f"**CTQ:** {r_ctq}")
            
            # 解析ボタン（結果は左カラム上部に表示される）
            if st.button(f"🔍 この事象の根拠を左カラムに抽出", key=f"ai_btn_{i}"):
                if not api_key:
                    st.error("サイドバーでAPIキーを設定してください")
                elif not st.session_state.protocol_text:
                    st.warning("左側でPRTをアップロードしてください")
                else:
                    with st.spinner("プロトコルを解析中..."):
                        try:
                            model = genai.GenerativeModel("gemini-3-flash-preview")
                            prompt = f"プロトコルから「{r_name}」に関連するセクションと規定を抽出し理由を述べてください。\n\nPRT:\n{st.session_state.protocol_text[:15000]}"
                            response = model.generate_content(prompt)
                            st.session_state.ai_highlights[i] = response.text
                            st.rerun()
                        except Exception as e:
                            st.error(f"解析失敗: {e}")

            st.divider()
            
            # 評価入力
            d1, d2, d3, d4 = st.columns([0.8, 0.8, 0.8, 1.2])
            with d1:
                s = st.selectbox("S", [1, 2, 3], key=f"s_{i}")
            with d2:
                o = st.selectbox("O", [1, 2, 3], key=f"o_{i}")
            with d3:
                d = st.selectbox("D", [1, 2, 3], key=f"d_{i}")
            with d4:
                st.metric("RPN", s * o * d)
            
            st.multiselect("要因の選択", options=factor_options, key=f"fact_{i}")

    # 集計出力
    st.divider()
    if st.button("📊 評価レポート(CSV)を生成"):
        results = []
        for risk in risk_data_master:
            i = risk["id"]
            s_v, o_v, d_v = st.session_state[f"s_{i}"], st.session_state[f"o_{i}"], st.session_state[f"d_{i}"]
            results.append({
                "Role": user_role,
                "No": i,
                "CTQ": risk["ctq"],
                "Risk_Event": risk["name"],
                "S": s_v, "O": o_v, "D": d_v, "RPN": s_v * o_v * d_v,
                "Factors": " | ".join(st.session_state[f"fact_{i}"])
            })
        
        if results:
            df = pd.DataFrame(results)
            st.table(df)
            csv = df.to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 CSVをダウンロード", csv, f"risk_eval_{user_role}.csv", "text/csv")
