import streamlit as st
import pandas as pd
from io import BytesIO
import PyPDF2
import google.generativeai as genai
from openai import OpenAI
import os

import streamlit as st

# --- ページ設定 (元のコード) ---
st.set_page_config(page_title="RBA Risk Assessment Pro", layout="wide")


# --- ヘッダーエリア (タイトルと画像の配置) ---

# 2つのカラムを作成します。
# 最初のカラム(col1)を小さく(1)、2番目のカラム(col2)を大きく(10)設定して、
# 画像をタイトルのすぐ左に寄せます。比率は好みに合わせて調整してください。
col1, col2 = st.columns([0.6, 10])

with col1:
    # タイトルの左側に画像を配置
    # riskass.pngは、このPythonファイルと同じディレクトリに置く必要があります。
    try:
        st.image("riskass.png", width=60) # widthで画像の大きさを調整します
    except FileNotFoundError:
        # 画像が見つからない場合のフォールバック（デバッグ用）
        st.warning("⚠️ riskass.png not found")

with col2:
    # メインのタイトルを配置
    # 画像の高さと合わせるため、少しMarkdownで調整することもあります。
    # ここでは単純にst.titleを使いますが、st.markdownでH1を使うとより細かく調整できます。
    st.title("RBA Risk Assessment Pro")

# --- アプリのメインコンテンツをここから下に記述 ---
st.write("---")
st.write("ここにリスクアセスメントのツール本体を実装していきます。")

# --- セッション状態の管理 ---
if "protocol_text" not in st.session_state:
    st.session_state.protocol_text = ""
if "ai_highlights" not in st.session_state:
    st.session_state.ai_highlights = {}
if "api_ready" not in st.session_state:
    st.session_state.api_ready = False

# --- API設定 (Secrets または 環境変数から取得) ---
secret_key = st.secrets.get("GOOGLE_API_KEY") or os.getenv("GOOGLE_API_KEY")

with st.sidebar:
    st.title("⚙️ 設定 & マスター定義")

    mode = st.radio("接続モード", ["Gemini (Cloud)", "LM Studio (Local)"])

    if mode == "Gemini (Cloud)":
        if secret_key:
            genai.configure(api_key=secret_key)
            st.success("✅ Gemini 認証済み (Cloud)")
            st.session_state.api_ready = True
        else:
            st.error("❌ APIキーがシステムに設定されていません。")
            st.session_state.api_ready = False
    else:
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
        "S: マニュアル、手順書が要因\n"
        "H: システムが要因\n"
        "E: リソース不足など環境要因\n"
        "L: 当事者の失念など\n"
        "L: 治験関係者以外の病院関係者や患者家族の行動が要因"
    )
    factor_input = st.text_area(label="要因リスト", value=default_factors, height=160)
    factor_options = [item.strip() for item in factor_input.split('\n') if item.strip()]

    st.divider()
    st.subheader("📊 評価基準の定義編集 (S/O/D)")
    with st.expander("S: 影響度 (Severity)"):
        s_def_1 = st.text_input("スコア1", value="安全性／信頼性への影響は軽微", key="s_def_1")
        s_def_2 = st.text_input("スコア2", value="蓄積することで影響", key="s_def_2")
        s_def_3 = st.text_input("スコア3", value="即時影響", key="s_def_3")

    with st.expander("O: 発生頻度 (Occurrence)"):
        o_def_1 = st.text_input("スコア1", value="ほとんど発生しない", key="o_def_1")
        o_def_2 = st.text_input("スコア2", value="偶発的に発生", key="o_def_2")
        o_def_3 = st.text_input("スコア3", value="繰り返して発生", key="o_def_3")

    with st.expander("D: 検出性 (Detectability)"):
        d_def_1 = st.text_input("スコア1", value="即時検出可能", key="d_def_1")
        d_def_2 = st.text_input("スコア2", value="データで検出可能", key="d_def_2")
        d_def_3 = st.text_input("スコア3", value="検出が困難", key="d_def_3")

# --- メインエリア ---
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
    
    # --- 修正後の職種・役割設定セクション ---
    st.subheader("📝 リスク評価実行")
    
    # ベースとなる職種を選択
    role_base = st.selectbox("評定者のベース職種を選択", ["PI", "CRC", "DM", "CRA", "STAT", "その他"])
    
    # 選択した職種を初期値として、自由に編集・追記できる入力欄を表示
    user_role = st.text_input("役割の詳細（自由に編集・記載してください）", value=role_base)
    
    
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
                if mode == "Gemini (Cloud)" and not st.session_state.api_ready:
                    st.error("API認証が完了していません。")
                elif not st.session_state.protocol_text:
                    st.warning("左側でPRTをアップロードしてください")
                else:
                    with st.spinner("プロトコルを解析中..."):
                        try:
                            # 職種情報は含めず、解析の純度を保つ
                            prompt = f"プロトコルから「{r_name}」に関連するセクションと規定を抽出すること。その際はセクション番号とページ数を記載し、規定は推論を加えず原文を忠実に記述すること。また理由を簡潔述べてください。\n\nPRT:\n{st.session_state.protocol_text[:15000]}"
                            if mode == "Gemini (Cloud)":
                                model = genai.GenerativeModel("gemini-1.5-flash")
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
            d1, d2, d3, d4 = st.columns([1.2, 1.2, 1.2, 1.0])
            with d1:
                s_options = [f"1: {s_def_1}", f"2: {s_def_2}", f"3: {s_def_3}"]
                s_str = st.selectbox("S (影響度)", s_options, key=f"s_{i}")
                s = int(s_str[0])
            with d2:
                o_options = [f"1: {o_def_1}", f"2: {o_def_2}", f"3: {o_def_3}"]
                o_str = st.selectbox("O (発生頻度)", o_options, key=f"o_{i}")
                o = int(o_str[0])
            with d3:
                d_options = [f"1: {d_def_1}", f"2: {d_def_2}", f"3: {d_def_3}"]
                d_str = st.selectbox("D (検出性)", d_options, key=f"d_{i}")
                d = int(d_str[0])
            with d4:
                st.metric("RPN", s * o * d)
            
            st.multiselect("要因の選択", options=factor_options, key=f"fact_{i}")

    # 集計出力・エクスポート
    st.divider()
   # --- 集計出力・エクスポート（ここから差し替え） ---
    st.divider()
    
    # keyを追加して重複エラーを回避
    if st.button("📊 評価レポートを生成", key="btn_generate_report"):
        results = []
        # テキストレポート用のヘッダー
        full_text_report = f"--- RBA Risk Assessment Report ({user_role}) ---\n\n"
        
        for risk in risk_data_master:
            i = risk["id"]
            # セッションからスコアを取得（インデックス0の数字を取得）
            s_v = int(st.session_state[f"s_{i}"][0])
            o_v = int(st.session_state[f"o_{i}"][0])
            d_v = int(st.session_state[f"d_{i}"][0])
            factors = " | ".join(st.session_state[f"fact_{i}"])
            
            # 分析アプリの仕様に合わせてキーをすべて「小文字」に設定
            # 分析アプリのコードと100%整合させるためのキー構成
            results.append({
                "role": user_role,        # 小文字
                "risk_event": risk["name"], # 小文字
                "S": s_v,                 # 66行目のために大文字
                "O": o_v,                 # 66行目のために大文字
                "D": d_v,                 # 66行目のために大文字
                "ctq": risk["ctq"],
                "no": i,
                "factors": factors
            
            })

            # テキストレポート用の詳細も蓄積
            if i in st.session_state.ai_highlights:
                full_text_report += f"【Risk {i}: {risk['name']}】\nRPN: {S_v*O_v*D_v}\n要因: {factors}\nAI抽出根拠:\n{st.session_state.ai_highlights[i]}\n\n"

        if results:
            df = pd.DataFrame(results)
            st.table(df)
            
            # ダウンロードボタンを横並びに配置
            ex_col1, ex_col2 = st.columns(2)
            with ex_col1:
                csv = df.to_csv(index=False).encode('utf-8-sig')
                st.download_button("📥 CSVダウンロード", csv, f"risk_eval_{user_role}.csv", "text/csv")
            with ex_col2:
                st.download_button("📝 根拠付きレポート(TXT)", full_text_report, f"full_report_{user_role}.txt", "text/plain")
