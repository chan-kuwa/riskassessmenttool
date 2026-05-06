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

# --- API設定---
# バックエンド側でシークレットを取得
secret_key = st.secrets.get("GOOGLE_API_KEY") or os.getenv("GOOGLE_API_KEY")

with st.sidebar:
    st.title("⚙️ 設定 & マスター定義")

    mode = st.radio("接続モード", ["Gemini (Cloud)", "LM Studio (Local)"])

    if mode == "Gemini (Cloud)":
        # シークレットの存在チェックと設定をバックエンドで完結させる
        if secret_key:
            genai.configure(api_key=secret_key)
            st.success("✅ Gemini 認証済み (Cloud)")
            st.session_state.api_ready = True
        else:
            st.error("❌ APIキーがシステムに設定されていません。")
            st.session_state.api_ready = False
            
    else:
        # LM Studio 等のローカル接続
        local_url = st.text_input("LM Studio URL", "http://localhost:1234/v1")
        try:
            st.session_state.client_local = OpenAI(base_url=local_url, api_key="lm-studio")
            st.success("✅ Local Server 接続完了")
            st.session_state.api_ready = True
        except Exception as e:
            st.error(f"接続エラー: {e}")
            st.session_state.api_ready = False

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

default_factors = (
    "P: 患者の行動が要因\n"
    "..."
)

factor_input = st.text_area(
    label="要因リスト（改行区切り）",
    value=default_factors,
    height=160
)


factor_options = [item.strip() for item in factor_input.split('\n') if item.strip()]
    factor_options = [item.strip() for item in factor_input.split('\n') if item.strip()]

    # --- 修正箇所1：サイドバーで評価基準を自由記載できるように変更 ---
    st.divider()
    st.subheader("📊 評価基準の定義編集 (S/O/D)")
    st.caption("評価時にプルダウンに表示される内容を編集できます。")
    
    with st.expander("S: 影響度 (Severity) の定義"):
        s_def_1 = st.text_input("スコア1 (低)", value="安全性／試験結果の信頼性／被験者保護への影響は軽微", key="s_def_1")
        s_def_2 = st.text_input("スコア2 (中)", value="蓄積することで影響", key="s_def_2")
        s_def_3 = st.text_input("スコア3 (高)", value="即時影響", key="s_def_3")

    with st.expander("O: 発生頻度 (Occurrence) の定義"):
        o_def_1 = st.text_input("スコア1 (低)", value="ほとんど発生しない", key="o_def_1")
        o_def_2 = st.text_input("スコア2 (中)", value="偶発的に発生", key="o_def_2")
        o_def_3 = st.text_input("スコア3 (高)", value="繰り返して発生", key="o_def_3")

    with st.expander("D: 検出性 (Detectability) の定義"):
        d_def_1 = st.text_input("スコア1 (高)", value="発生時に即時検出可能", key="d_def_1")
        d_def_2 = st.text_input("スコア2 (中)", value="データで検出可能", key="d_def_2")
        d_def_3 = st.text_input("スコア3 (低)", value="検出が困難／オンサイトモニタリングで検出可能", key="d_def_3")
    # ------------------------------------------------------------------

# --- メインエリア：2カラム ---
col_left, col_right = st.columns([1.2, 1.8])

# --- 左カラム：AI解析結果 & プロトコル参照 ---
with col_left:
    st.subheader("🤖 AI解析結果：該当箇所の特定")
    
    if st.session_state.ai_highlights:
        for r_idx, h_text in st.session_state.ai_highlights.items():
            r_name_label = st.session_state.get(f"master_risk_{r_idx}", "Unknown")
            with st.chat_message("assistant"):
                st.caption(f"Risk #{r_idx}: {r_name_label}")
                st.write(h_text)
    else:
        st.info("右側の解析ボタンを押すと、ここに根拠規定が抽出されます。")

    st.divider()

    # プロトコル参照
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
    user_role = st.selectbox("評定者の職種を選択", ["CRA", "CRC", "DM", "PM", "PI", "STAT"])
    
    st.divider()
    
    if not risk_data_master:
        st.warning("サイドバーでCTQとリスク事象を入力してください。")
    
    for risk in risk_data_master:
        i = risk["id"]
        r_name = risk["name"]
        r_ctq = risk["ctq"]
        
        with st.expander(f"No.{i} : {r_name} ({r_ctq})", expanded=(i==1)):
            st.markdown(f"**CTQ:** {r_ctq}")
            
            if st.button(f"🔍 この事象の根拠を左カラムに抽出", key=f"ai_btn_{i}"):
                # 修正箇所：api_key 参照を st.session_state.api_ready に変更
                if mode == "Gemini (Cloud)" and not st.session_state.api_ready:
                    st.error("API認証が完了していません。Secretsの設定を確認してください。")
                elif not st.session_state.protocol_text:
                    st.warning("左側でPRTをアップロードしてください")
                else:
                    with st.spinner("プロトコルを解析中..."):
                        try:
                            prompt = f"プロトコルから「{r_name}」に関連するセクションと規定を抽出し理由を述べてください。\n\nPRT:\n{st.session_state.protocol_text[:15000]}"
                            
                            if mode == "Gemini (Cloud)":
                                model = genai.GenerativeModel("gemini-3-flash-preview")
                                response = model.generate_content(prompt)
                                result_text = response.text
                            else:
                                response = st.session_state.client_local.chat.completions.create(
                                    model="local-model",
                                    messages=[{"role": "user", "content": prompt}]
                                )
                                result_text = response.choices[0].message.content
                                
                            st.session_state.ai_highlights[i] = result_text
                            st.rerun()
                        except Exception as e:
                            st.error(f"解析失敗: {e}")

            st.divider()
            
            # --- 修正箇所2：サイドバーで定義した内容が反映されるように変更 ---
            st.caption("プルダウン内で定義を確認してスコアを選択してください。")
            d1, d2, d3, d4 = st.columns([1.2, 1.2, 1.2, 1.0]) # 幅を少し広げました
            
            with d1:
                # サイドバーの入力値を使って選択肢を動的に生成
                s_options = [
                    f"1: {s_def_1}",
                    f"2: {s_def_2}",
                    f"3: {s_def_3}"
                ]
                s_str = st.selectbox("S (影響度)", s_options, key=f"s_{i}")
                s = int(s_str[0]) # 先頭の数字を取得

            with d2:
                o_options = [
                    f"1: {o_def_1}",
                    f"2: {o_def_2}",
                    f"3: {o_def_3}"
                ]
                o_str = st.selectbox("O (発生頻度)", o_options, key=f"o_{i}")
                o = int(o_str[0])

            with d3:
                d_options = [
                    f"1: {d_def_1}",
                    f"2: {d_def_2}",
                    f"3: {d_def_3}"
                ]
                d_str = st.selectbox("D (検出性)", d_options, key=f"d_{i}")
                d = int(d_str[0])
            
            with d4:
                st.metric("RPN", s * o * d)
            # ------------------------------------------------------------------
            
            st.multiselect("要因の選択", options=factor_options, key=f"fact_{i}")

    # 集計出力
    st.divider()
    if st.button("📊 評価レポート(CSV)を生成"):
        results = []
        for risk in risk_data_master:
            i = risk["id"]
            # セッション状態には「数字: [自由記載の定義]」の文字列が入っているため、先頭の数字を取り出す
            s_str_v = st.session_state[f"s_{i}"]
            o_str_v = st.session_state[f"o_{i}"]
            d_str_v = st.session_state[f"d_{i}"]
            
            s_v = int(s_str_v[0])
            o_v = int(o_str_v[0])
            d_v = int(d_str_v[0])
            
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
