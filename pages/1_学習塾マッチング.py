import sys
from math import perm
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import iq_io  # noqa: E402
from matching_checks import find_profitable_misreport  # noqa: E402

st.set_page_config(page_title="学習塾マッチング (Internal Quota)", layout="wide")

# ==========================================
# 初期化
# ==========================================
if "iq_tables" not in st.session_state:
    st.session_state.iq_tables = iq_io.default_tables()


def reset_result():
    st.session_state.pop("iq_result", None)


# ==========================================
# サイドバー：CSV
# ==========================================
st.sidebar.header("📁 CSVインポート")
st.sidebar.caption("列名は画面の表と同じにしてください。")
names = ["生徒", "講師", "コマ"]
uploads = [st.sidebar.file_uploader(f"{n}表のCSV", type=["csv"], key=f"iq_csv_{i}") for i, n in enumerate(names)]
if any(uploads) and st.sidebar.button("読み込んだCSVで表を更新"):
    tables = list(st.session_state.iq_tables)
    for i, f in enumerate(uploads):
        if f:
            tables[i] = pd.read_csv(f)
    st.session_state.iq_tables = tuple(tables)
    reset_result()
    st.rerun()
st.sidebar.markdown("---")
if st.sidebar.button("デフォルトのデータに戻す"):
    st.session_state.iq_tables = iq_io.default_tables()
    reset_result()
    st.rerun()

# ==========================================
# 本文
# ==========================================
st.title("学習塾マッチング（Matching with Internal Quota）")
with st.expander("このモデルについて", expanded=False):
    st.markdown(
        """
- 契約は **(生徒, 講師, コマ)** の組です。生徒は契約（講師×コマ）に希望順位を付け、1つだけ受講します。
- 講師には **コマ別定員** $q_{tl}$ と **総定員** $Q_t$ があります（$|Y_{tl}| \\le q_{tl}$, $|Y_t| \\le Q_t$）。
- この制約は講師ごとの laminar matroid なので、講師は「優先順に見て、定員に空きがあれば受け入れる」貪欲法で選べば、
  一般化DAが **IQ安定・生徒最適・生徒にとって耐戦略的** なマッチングを返します（Kojima, Tamura and Yokoo 2018 の条件を適用）。
- 講師の優先順位は「生徒」単位でも「生徒@コマ」単位でも書けます。生徒だけ書いた場合は、その講師のコマ表の順で展開します。
"""
    )

tab_main, tab_ext = st.tabs(["マッチングの実行", "拡張：担当コマ数の上限（6.1）"])

with tab_main:
    s_df, t_df, l_df = st.session_state.iq_tables
    c1, c2 = st.columns([1.2, 1])
    with c1:
        st.subheader("生徒")
        ed_s = st.data_editor(s_df, num_rows="dynamic", use_container_width=True, key="ed_s", on_change=reset_result)
    with c2:
        st.subheader("講師")
        ed_t = st.data_editor(t_df, num_rows="dynamic", use_container_width=True, key="ed_t", on_change=reset_result)
        st.subheader("コマと定員")
        ed_l = st.data_editor(l_df, num_rows="dynamic", use_container_width=True, key="ed_l", on_change=reset_result)

    accept_unlisted = st.checkbox("講師の優先順位に書かれていない生徒も最下位として受け入れる（スライドの仮定）", value=True)

    if st.button("DAアルゴリズムを実行する", type="primary"):
        inst, errors, notes = iq_io.build_instance(ed_s, ed_t, ed_l, accept_unlisted)
        if errors:
            reset_result()
            st.error("入力に問題があります。\n\n" + "\n".join(f"- {e}" for e in errors))
        else:
            tutors, Y, trace = iq_io.run(inst)
            st.session_state.iq_result = {"inst": inst, "tutors": tutors, "Y": Y, "trace": trace, "notes": notes}

    res = st.session_state.get("iq_result")
    if res:
        inst, tutors, Y = res["inst"], res["tutors"], res["Y"]
        for n in res["notes"]:
            st.caption(f"ℹ️ {n}")
        if inst.max_lessons:
            st.warning("担当コマ数の上限が設定されています。この場合、制約が matroid でなくなるため、"
                       "安定性・耐戦略性・生徒最適性は保証されません（「拡張」タブを参照）。")

        matched, usage, unmatched = iq_io.result_tables(inst, tutors, Y)
        st.markdown("---")
        r1, r2 = st.columns([1, 1.3])
        with r1:
            st.subheader("🎉 成立したマッチング")
            st.dataframe(matched, hide_index=True, use_container_width=True)
            st.subheader("⚠️ あぶれた生徒")
            st.write(", ".join(unmatched) if unmatched else "なし")
        with r2:
            st.subheader("📊 講師・コマごとの充足状況")
            st.dataframe(usage, hide_index=True, use_container_width=True)

        st.subheader("✅ 性質の検証")
        chk = iq_io.checks(inst, tutors, Y)
        v1, v2, v3 = st.columns(3)
        v1.metric("実行可能性", "OK" if chk["feasible"] else "NG")
        v2.metric("IQ安定性", "OK" if not chk["iq_violations"] else f"NG ({len(chk['iq_violations'])}件)")
        v3.metric("HM安定性", "OK" if chk["hm_stable"] else "NG")
        for x, why in chk["iq_violations"]:
            st.error(f"{iq_io.label(x)}：{why}")

        with st.expander("DAの経過（ラウンドごと）"):
            st.dataframe(iq_io.trace_table(res["trace"]), hide_index=True, use_container_width=True)

        with st.expander("耐戦略性を総当たりで確認する（小規模向け）"):
            max_len = st.slider("虚偽申告で並べる希望の最大数", 1, 4, 2)
            n_opts = sum(len(spec["lessons"]) for spec in inst.tutors_spec.values())
            n_lies = sum(perm(n_opts, k) for k in range(min(max_len, n_opts) + 1)) * len(inst.students)
            st.caption(f"DAを約 {n_lies:,} 回実行します。")
            if st.button("確認する", disabled=n_lies > 50_000):
                with st.spinner("総当たり中..."):
                    found = find_profitable_misreport(inst, max_len)
                if found:
                    s, lie, before, after = found
                    st.error(f"{s} は希望を「{', '.join(f'{t}@{l}' for t, l in lie)}」と偽ると、"
                             f"{iq_io.label(before) if before else '未割当'} → {iq_io.label(after)} に改善できます。")
                else:
                    st.success("調べた範囲では、得をする虚偽申告は見つかりませんでした。")

with tab_ext:
    st.markdown(
        """
講師が「担当するコマ数」にも上限 $Q^L_t$ を持つと（時給制で勤務コマ数を抑えたい場合など）、
実行可能集合族は matroid でなくなり、一般化DAの良い性質が崩れます。
以下は講師1人・コマ3つ・**担当コマ数の上限1** の例で、生徒 S1 が希望を偽ると得をします。
"""
    )
    inst_x, lie = iq_io.lesson_cap_counterexample()
    st.dataframe(pd.DataFrame([
        {"生徒": s, "真の希望": ", ".join(l for _, l in p), "S1の虚偽申告": ", ".join(l for _, l in lie[s]) if s in lie else "—"}
        for s, p in inst_x.students.items()
    ]), hide_index=True, use_container_width=True)
    spec = inst_x.tutors_spec["講師"]
    st.caption("コマ定員：" + ", ".join(f"{l}={q}" for l, q in spec["lessons"].items())
               + f" ／ 総定員 {spec['total']} ／ 担当コマ数上限 1 ／ 講師の優先順位："
               + " ≻ ".join(f"{s}@{l}" for s, l in spec["priority"]))
    e1, e2 = st.columns(2)
    for col, title, ov in [(e1, "正直に申告", None), (e2, "S1 が虚偽申告", lie)]:
        with col:
            st.subheader(title)
            tutors_x, Y_x, _ = iq_io.run(inst_x, ov)
            m, _, un = iq_io.result_tables(inst_x, tutors_x, Y_x)
            st.dataframe(m[["生徒", "コマ"]], hide_index=True, use_container_width=True)
            st.write("あぶれた生徒：" + (", ".join(un) or "なし"))
    st.info("正直に申告すると S1 はあぶれますが、L3, L2 の順に申告すると L2 に入れます。"
            "S1 が先に L3 を押さえると、講師の担当コマが L3 で埋まり S3 の L2 が拒否されます。"
            "その後 S1 は L3 から外れますが、拒否された S3 は戻らないため、L2 に空きが残ります。"
            "選択肢が増えると S3@L2 が受け入れられるのに、減ると拒否される（代替性が成り立たない）ことが原因です。")
