import streamlit as st
import pandas as pd
from matching_engine import Contract, Proposer, SimpleReceiver, generalized_deferred_acceptance

st.set_page_config(page_title="DA Matching Engine", layout="wide")

# ==========================================
# 1. 初期データ（デフォルト値）の生成関数
# ==========================================
def get_default_p_df():
    return pd.DataFrame({
        "Proposer_ID": ["Proposer_1", "Proposer_2", "Proposer_3", "Proposer_4", "Proposer_5"],
        "希望順位 (カンマ区切り)": ["Receiver_A, Receiver_B, Receiver_C", 
                                "Receiver_A, Receiver_C, Receiver_B",
                                "Receiver_A, Receiver_B, Receiver_C",
                                "Receiver_B, Receiver_A, Receiver_C",
                                "Receiver_C, Receiver_B, Receiver_A"]
    })

def get_default_r_df():
    return pd.DataFrame({
        "Receiver_ID": ["Receiver_A", "Receiver_B", "Receiver_C"],
        "定員": [2, 1, 1],
        "希望順位 (カンマ区切り)": ["Proposer_3, Proposer_2, Proposer_1, Proposer_4, Proposer_5",
                                "Proposer_1, Proposer_4, Proposer_2, Proposer_3, Proposer_5",
                                "Proposer_5, Proposer_3, Proposer_2, Proposer_1, Proposer_4"]
    })

# session_stateの初期化
if "p_df" not in st.session_state:
    st.session_state.p_df = get_default_p_df()

if "r_df" not in st.session_state:
    st.session_state.r_df = get_default_r_df()


# ==========================================
# 2. サイドバー：CSVアップロード機能
# ==========================================
st.sidebar.header("📁 CSVインポート")
st.sidebar.write("CSVを読み込むと、メイン画面の表が上書きされます。読み込み後に画面上で微調整することも可能です。")

# 提案側CSVのアップロード
p_file = st.sidebar.file_uploader("提案側 (Proposer) のCSV", type=["csv"])
if p_file and st.sidebar.button("提案側データを更新"):
    st.session_state.p_df = pd.read_csv(p_file)
    st.rerun() # 画面を再読み込みして表を更新

# 受入側CSVのアップロード
r_file = st.sidebar.file_uploader("受入側 (Receiver) のCSV", type=["csv"])
if r_file and st.sidebar.button("受入側データを更新"):
    st.session_state.r_df = pd.read_csv(r_file)
    st.rerun()

st.sidebar.markdown("---")
if st.sidebar.button("デフォルトのテストデータに戻す"):
    st.session_state.p_df = get_default_p_df()
    st.session_state.r_df = get_default_r_df()
    st.rerun()


# ==========================================
# 3. UIの構築とデータ編集 (メイン画面)
# ==========================================
st.title("マッチング・アルゴリズム デモ画面")
st.write("左のメニューからCSVをアップロードするか、下の表を直接クリックして編集してください。")

st.header("📝 データの入力・編集")
col1, col2 = st.columns(2)

with col1:
    st.subheader("提案側 (Proposer)")
    edited_p_df = st.data_editor(st.session_state.p_df, num_rows="dynamic", use_container_width=True)

with col2:
    st.subheader("受入側 (Receiver)")
    edited_r_df = st.data_editor(st.session_state.r_df, num_rows="dynamic", use_container_width=True)

st.markdown("---")

# ==========================================
# 4. 入力データからオブジェクトを生成して実行
# ==========================================
st.header("⚙️ アルゴリズムの実行")
run_button = st.button("現在の表のデータでDAアルゴリズムを実行する", type="primary")

if run_button:
    with st.spinner("マッチングを計算中..."):
        # 1. 辞書の初期化
        proposers = {}
        receivers = {}
        contracts = {}

        # 2. 提案側のオブジェクト生成
        for _, row in edited_p_df.iterrows():
            p_id = str(row["Proposer_ID"]).strip()
            raw_prefs = str(row["希望順位 (カンマ区切り)"]).split(",")
            pref_r_ids = [r.strip() for r in raw_prefs if r.strip()]
            
            pref_c_ids = []
            for r_id in pref_r_ids:
                c_id = f"c_{p_id}_{r_id}"
                if c_id not in contracts:
                    contracts[c_id] = Contract(c_id, p_id, r_id)
                pref_c_ids.append(c_id)
                
            proposers[p_id] = Proposer(p_id, pref_c_ids)

        # 3. 受入側のオブジェクト生成
        for _, row in edited_r_df.iterrows():
            r_id = str(row["Receiver_ID"]).strip()
            capacity = int(row["定員"])
            raw_prefs = str(row["希望順位 (カンマ区切り)"]).split(",")
            pref_p_ids = [p.strip() for p in raw_prefs if p.strip()]
            
            for p_id in pref_p_ids:
                c_id = f"c_{p_id}_{r_id}"
                if c_id not in contracts:
                    contracts[c_id] = Contract(c_id, p_id, r_id)
                    
            receivers[r_id] = SimpleReceiver(r_id, capacity, pref_p_ids)

        # 4. アルゴリズム実行
        final_matching = generalized_deferred_acceptance(proposers, receivers, contracts)
    
    # === 結果の表示 ===
    st.success("マッチングが完了しました！")
    res_col1, res_col2, res_col3 = st.columns(3)
    
    with res_col1:
        st.subheader("🎉 成立したマッチング")
        for match in final_matching:
            st.info(f"**{match.proposer_id}** ➔ **{match.receiver_id}**")
            
    with res_col2:
        st.subheader("⚠️ あぶれた提案側")
        matched_p_ids = {m.proposer_id for m in final_matching}
        unmatched_p = set(proposers.keys()) - matched_p_ids
        if unmatched_p:
            for p in sorted(unmatched_p):
                st.error(f"{p}")
        else:
            st.write("なし")
            
    with res_col3:
        st.subheader("🈳 定員割れした受入側")
        matched_r_counts = {r_id: 0 for r_id in receivers.keys()}
        for m in final_matching:
            matched_r_counts[m.receiver_id] += 1
            
        has_underfilled = False
        for r_id, count in matched_r_counts.items():
            empty_slots = receivers[r_id].capacity - count
            if empty_slots > 0:
                st.warning(f"{r_id} (残り {empty_slots} 枠)")
                has_underfilled = True
        if not has_underfilled:
            st.write("なし")