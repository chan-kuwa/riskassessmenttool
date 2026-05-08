import streamlit as st
import pandas as pd
from io import BytesIO
import PyPDF2
import google.generativeai as genai
import os
import json
import base64

# --- 1. ページ設定 ---
st.set_page_config(page_title="RBA Risk Assessment Pro", layout="wide", page_icon="🛡️")

# --- 2. URLパラメータ復元 ---
query_params = st.query_params
initial_config = None
if "data" in query_params:
    try:
        initial_config = json.loads(base64.b64decode(query_params["data"]).decode('utf-8'))
    except:
        st.error("配布データの復元に失敗しました。")

# --- 3. セッション管理 ---
if "protocol_text" not in st.session_state: st.session_state.protocol_text = ""
if "ai_highlights" not in st.session_state: st.session_state.ai_highlights = {}
if "api_ready" not in st.session_state: st.session_state.api_ready = False

# マスターデータの初期化
if "role_master" not in st.session_state:
    if initial_config and "roles" in initial_config:
        st.session_state.role_master = pd.DataFrame(initial_config["roles"])
    else:
        st.session_state.role_master = pd.DataFrame([
            {"role": "PI", "definition": "検査および医学的評価の実施、妥当性・安全性の責任者"},
            {"role": "CRC", "definition": "医師の支援、EDCデータ入力"},
            {"role": "CRA", "definition": "規定遵守・データ信頼性の視点"}
        ])

if "structured_risks" not in st.session_state:
    if initial_config and "risks" in initial_config:
        st.session_state.structured_risks = initial_config["risks"]
    else:
        st.session_state.structured_risks = [
            {"ctq": "主要評価項目の信頼性", "events": "画像データの欠測\n検査手順の逸脱"},
            {"ctq": "被験者の安全性確保", "events": "有害事象の報告遅延"}
        ]

# --- 4. サイドバー（設定集約） ---
with st.sidebar:
    st.title("⚙️ RBA Master Control")
    
    if st.button("🔗 配布URLを発行"):
        current_config = {
            "roles": st.session_state.role_master.to_dict(orient='records'),
            "risks": st.session_state.structured_risks,
            "factors": st.session_state.get("f_raw", "")
        }
        b64 = base64.b64encode(json.dumps(current_config).encode('utf-8')).decode('utf-8')
        st.code(f"https://your-app-url.streamlit.app/?data={b64}")
        st.caption("このURLをコピーして評価者に共有してください。※APIキーは含まれません。")

    st.divider()

    with st.expander("👤 1. 職種・役割の定義", expanded=False):
        st.session_state.role_master = st.data_editor(st.session_state.role_master, num_rows="dynamic")
        role_dict = dict(zip(st.session_state.role_master["role"], st.session_state.role_master["definition"]))

    with st.expander("🎯 2. CTQ & リスク定義", expanded=True):
        updated_risks = []
        current_groups = list(st.session_state.structured_risks)
        for i, group in enumerate(current_groups):
            st.markdown(f"**Group {i+1}**")
            c_val = st.text_input(f"CTQ {i}", value=group["ctq"], key=f"c_in_{i}", label_visibility="collapsed")
            e_val = st.text_area(f"Risk {i}", value=group["events"], key=f"e_in_{i}", height=80, label_visibility="collapsed")
            updated_risks.append({"ctq": c_val, "events": e_val})
            if st.button(f"🗑️ 削除", key=f"del_g_{i}"):
                st.session_state.structured_risks.pop(i)
                st.rerun()
        
        if st.button("➕ CTQを追加"):
            st.session_state.structured_risks.append({"ctq": "", "events": ""})
            st.rerun()
        st.session_state.structured_risks = updated_risks

    with st.expander("🔍 3. 要因マスター", expanded=False):
        f_raw = st.text_area("要因", value="P: 患者要因\nS: 手順書要因\nH: システム要員\nE: リソース不足や時間等の環境要因\nL:対応者自身が要因（失念など）\nL: 治験関係者以外（分担医師・協力者以外の医療関係者や患者家族）要因", height=100)
        st.session_state.f_raw = f_raw
        factor_options = [f.strip() for f in f_raw.split('\n') if f.strip()]

    st.divider()
    
    st.subheader("🔑 API認証")
    mode = st.radio("接続モード", ["Gemini", "Local"], label_visibility="collapsed")
    
    if mode == "Gemini":
        env_key = st.secrets.get("GOOGLE_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if env_key:
            st.success("✅ APIキー：Secretsより読込済")
            genai.configure(api_key=env_key)
            st.session_state.api_ready = True
        else:
            user_key = st.text_input("Google API Key を入力", type="password")
            if user_key:
                genai.configure(api_key=user_key)
                st.session_state.api_ready = True
    else:
        st.session_state.api_ready = True

# --- 5. メインエリア ヘッダー ---
head_col1, head_col2 = st.columns([0.1, 0.9])
with head_col1:
    if os.path.exists("riskass.png"):
        st.image("riskass.png", width=70)
    else:
        st.markdown("<h1 style='text-align: center;'>🛡️</h1>", unsafe_allow_html=True)
with head_col2:
    st.markdown("<h1 style='margin-bottom: 0;'>RBA Risk Assessment Pro</h1>", unsafe_allow_html=True)
    st.markdown("<p style='color: gray; margin-top: 0;'>Clinical Research Risk-Based Approach Support Tool</p>", unsafe_allow_html=True)

st.write("---")

eval_items = []
for g in st.session_state.structured_risks:
    for e in g["events"].split('\n'):
        if e.strip(): eval_items.append({"ctq": g["ctq"], "risk": e.strip()})

col_left, col_right = st.columns([1, 1.5])

# --- 6. 左カラム：解析根拠 ---
with col_left:
    st.subheader("🤖 AI分析・原本確認")
    up = st.file_uploader("プロトコル原本（PDF）", type="pdf")
    if up:
        reader = PyPDF2.PdfReader(BytesIO(up.read()))
        st.session_state.protocol_text = "\n".join([p.extract_text() for p in reader.pages if p.extract_text()])
    
    if st.session_state.ai_highlights:
        for k, v in st.session_state.ai_highlights.items():
            with st.chat_message("assistant"):
                st.caption(f"【{k}】の抽出根拠")
                st.write(v)

# --- 7. 右カラム：評価実行 ---
with col_right:
    st.subheader("📝 評価スコアリング")
    role_opts = list(role_dict.keys())
    if role_opts:
        sel_role = st.selectbox("あなたの職種を選択", role_opts)
        st.info(f"**担当役割:** {role_dict[sel_role]}")
        
    for i, item in enumerate(eval_items):
        with st.expander(f"No.{i+1} | {item['ctq']} : {item['risk']}", expanded=(i==0)):
            if st.button(f"🔍 プロトコルから根拠を抽出", key=f"ai_b_{i}"):
                if st.session_state.api_ready and st.session_state.protocol_text:
                    with st.spinner("解析中..."):
                        try:
                            # プレビュー版モデル名を明示的に指定（3.0 Flash Preview）
                            # 2026年現在のプレビュー用識別子 'gemini-3-flash-preview' を使用
                            model = genai.GenerativeModel("models/gemini-3-flash-preview")
                            prompt = f"リスク「{item['risk']}」に関連するプロトコルの規定（セクション番号、ページ、原文）を抽出せよ。\n\nPROTOCOL:\n{st.session_state.protocol_text[:12000]}"
                            res = model.generate_content(prompt).text
                            st.session_state.ai_highlights[f"{item['ctq']}_{item['risk']}"] = res
                            st.rerun()
                        except Exception as e:
                            st.error(f"解析エラー: {e}")
                            st.info("API Studioで利用可能なモデル名を確認してください（例: gemini-3-flash-preview-xxxx）")
            
            c1, c2, c3, c4 = st.columns([1,1,1,1])
            s = c1.selectbox("S (影響)", [1,2,3], key=f"s_{i}", help="1:低, 2:中, 3:高")
            o = c2.selectbox("O (頻度)", [1,2,3], key=f"o_{i}", help="1:低, 2:中, 3:高")
            d = c3.selectbox("D (検出)", [1,2,3], key=f"d_{i}", help="1:容易, 2:困難, 3:極めて困難")
            c4.metric("RPN", s*o*d)
            st.multiselect("リスク要因 (Factors)", factor_options, key=f"f_{i}")

    st.divider()
    if st.button("📊 評価完了・CSV生成"):
        final_data = []
        for j, it in enumerate(eval_items):
            final_data.append({
                "role": sel_role,
                "role_definition": role_dict[sel_role],
                "ctq": it["ctq"],
                "risk_event": it["risk"],
                "S": st.session_state[f"s_{j}"],
                "O": st.session_state[f"o_{j}"],
                "D": st.session_state[f"d_{j}"],
                "factors": " | ".join(st.session_state[f"f_{j}"])
            })
        df = pd.DataFrame(final_data)
        st.table(df)
        st.download_button(
            label="📥 分析ツール用CSVをダウンロード",
            data=df.to_csv(index=False).encode('utf-8-sig'),
            file_name=f"RBA_{sel_role}.csv",
            mime="text/csv"
        )
