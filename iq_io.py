"""
学習塾モデル（Internal Quota）の表データ ⇔ IQInstance の変換と、結果表の作成
Streamlit に依存しないので単体でテストできる
"""
from typing import Dict, List, Optional, Tuple

import pandas as pd

from internal_quota import IQInstance, lesson_of
from matching_checks import iq_violations, is_feasible, is_hm_stable
from matching_engine import Contract, generalized_deferred_acceptance

SEP = "@"
COL_S_ID, COL_S_PREF = "Student_ID", "希望 (講師@コマ, 希望順)"
COL_T_ID, COL_T_TOTAL, COL_T_PRIO, COL_T_MAXL = "Tutor_ID", "総定員", "優先順位 (生徒 または 生徒@コマ)", "担当コマ数上限 (任意)"
COL_L_T, COL_L_ID, COL_L_Q = "Tutor_ID", "Lesson_ID", "コマ定員"


def default_tables() -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    students = pd.DataFrame({
        COL_S_ID: ["S1", "S2", "S3", "S4", "S5", "S6"],
        COL_S_PREF: [
            "講師A@月17, 講師B@月17",
            "講師A@月17, 講師A@月19",
            "講師A@月17, 講師B@水17",
            "講師A@月19, 講師A@月17, 講師B@水17",
            "講師B@月17, 講師A@月19",
            "講師A@月19, 講師B@水17",
        ],
    })
    tutors = pd.DataFrame({
        COL_T_ID: ["講師A", "講師B"],
        COL_T_TOTAL: [3, 2],
        COL_T_PRIO: ["S3, S1, S4, S2, S6, S5", "S5, S6, S1, S3"],
        COL_T_MAXL: [None, None],
    })
    lessons = pd.DataFrame({
        COL_L_T: ["講師A", "講師A", "講師B", "講師B"],
        COL_L_ID: ["月17", "月19", "月17", "水17"],
        COL_L_Q: [2, 2, 1, 2],
    })
    return students, tutors, lessons


def _clean(v) -> str:
    return "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v).strip()


def _split(v) -> List[str]:
    return [x.strip() for x in _clean(v).replace("、", ",").split(",") if x.strip()]


def build_instance(students_df: pd.DataFrame, tutors_df: pd.DataFrame, lessons_df: pd.DataFrame,
                   accept_unlisted: bool = True) -> Tuple[Optional[IQInstance], List[str], List[str]]:
    """戻り値: (インスタンス or None, エラー一覧, 注意一覧)"""
    errors: List[str] = []
    notes: List[str] = []

    # --- 講師とコマ ---
    tutors: Dict[str, dict] = {}
    max_lessons: Dict[str, int] = {}
    for _, row in tutors_df.iterrows():
        t = _clean(row.get(COL_T_ID))
        if not t:
            continue
        if t in tutors:
            errors.append(f"講師ID「{t}」が重複しています。")
            continue
        try:
            total = int(float(_clean(row.get(COL_T_TOTAL))))
        except ValueError:
            errors.append(f"講師「{t}」の総定員が数値ではありません。")
            continue
        tutors[t] = {"total": total, "lessons": {}, "priority_raw": _split(row.get(COL_T_PRIO))}
        ml = _clean(row.get(COL_T_MAXL))
        if ml:
            try:
                max_lessons[t] = int(float(ml))
            except ValueError:
                errors.append(f"講師「{t}」の担当コマ数上限が数値ではありません。")

    for _, row in lessons_df.iterrows():
        t, l = _clean(row.get(COL_L_T)), _clean(row.get(COL_L_ID))
        if not t and not l:
            continue
        if t not in tutors:
            errors.append(f"コマ表の講師「{t}」が講師表にありません。")
            continue
        if not l or SEP in l:
            errors.append(f"講師「{t}」のコマIDが空か「{SEP}」を含んでいます。")
            continue
        try:
            q = int(float(_clean(row.get(COL_L_Q))))
        except ValueError:
            errors.append(f"講師「{t}」コマ「{l}」の定員が数値ではありません。")
            continue
        if l in tutors[t]["lessons"]:
            errors.append(f"講師「{t}」のコマ「{l}」が重複しています。")
        tutors[t]["lessons"][l] = q

    for t, spec in tutors.items():
        for l, q in spec["lessons"].items():
            if q > spec["total"]:
                notes.append(f"講師「{t}」のコマ「{l}」の定員 {q} が総定員 {spec['total']} を超えています（実質的に総定員が上限になります）。")

    # --- 生徒 ---
    students: Dict[str, List[Tuple[str, str]]] = {}
    for _, row in students_df.iterrows():
        s = _clean(row.get(COL_S_ID))
        if not s:
            continue
        if s in students:
            errors.append(f"生徒ID「{s}」が重複しています。")
            continue
        pref: List[Tuple[str, str]] = []
        for item in _split(row.get(COL_S_PREF)):
            if SEP not in item:
                errors.append(f"生徒「{s}」の希望「{item}」は「講師{SEP}コマ」の形式ではありません。")
                continue
            t, l = [x.strip() for x in item.split(SEP, 1)]
            if t not in tutors or l not in tutors[t]["lessons"]:
                errors.append(f"生徒「{s}」の希望「{item}」に対応する講師・コマがありません。")
                continue
            if (t, l) in pref:
                notes.append(f"生徒「{s}」の希望「{item}」が重複しているため、2回目以降は無視しました。")
                continue
            pref.append((t, l))
        students[s] = pref

    # --- 講師の優先順位を (生徒, コマ) の順序に展開 ---
    for t, spec in tutors.items():
        prio: List[Tuple[str, str]] = []
        for item in spec.pop("priority_raw"):
            if SEP in item:
                s, l = [x.strip() for x in item.split(SEP, 1)]
                pairs = [(s, l)]
                if l not in spec["lessons"]:
                    errors.append(f"講師「{t}」の優先順位「{item}」のコマがありません。")
                    continue
            else:
                s = item
                pairs = [(s, l) for l in spec["lessons"]]
            if s not in students:
                errors.append(f"講師「{t}」の優先順位にある生徒「{s}」が生徒表にありません。")
                continue
            prio.extend(p for p in pairs if p not in prio)
        if accept_unlisted:
            rest = [(s, l) for s in students for l in spec["lessons"] if (s, l) not in prio]
            if rest:
                notes.append(f"講師「{t}」の優先順位に記載のない (生徒, コマ) {len(rest)} 件は、生徒表の順で最下位に加えました。")
            prio.extend(rest)
        spec["priority"] = prio

    if not students:
        errors.append("生徒が1人もいません。")
    if not tutors:
        errors.append("講師が1人もいません。")
    if errors:
        return None, errors, notes
    return IQInstance(students, tutors, {t: max_lessons.get(t, 10**9) for t in tutors} if max_lessons else None), errors, notes


def run(inst: IQInstance, override=None):
    tutors = inst.build_tutors()
    trace: List[dict] = []
    Y = generalized_deferred_acceptance(inst.build_proposers(override), tutors, inst.contracts, trace)
    return tutors, Y, trace


def label(c: Contract) -> str:
    return f"{c.proposer_id}→{c.receiver_id}{SEP}{lesson_of(c)}"


def result_tables(inst: IQInstance, tutors, Y: List[Contract]):
    pref_rank = {s: {(t, l): i + 1 for i, (t, l) in enumerate(p)} for s, p in inst.students.items()}
    matched = pd.DataFrame([
        {"生徒": c.proposer_id, "講師": c.receiver_id, "コマ": lesson_of(c),
         "生徒の希望順位": f"{pref_rank[c.proposer_id][(c.receiver_id, lesson_of(c))]}位"}
        for c in sorted(Y, key=lambda c: list(inst.students).index(c.proposer_id))
    ])
    rows = []
    for t, spec in inst.tutors_spec.items():
        Y_t = [c for c in Y if c.receiver_id == t]
        for l, q in spec["lessons"].items():
            names = [c.proposer_id for c in Y_t if lesson_of(c) == l]
            rows.append({"講師": t, "コマ": l, "割当": len(names), "コマ定員": q, "生徒": ", ".join(names)})
        rows.append({"講師": t, "コマ": "（合計）", "割当": len(Y_t), "コマ定員": spec["total"], "生徒": ""})
    usage = pd.DataFrame(rows)
    unmatched = [s for s in inst.students if s not in {c.proposer_id for c in Y}]
    return matched, usage, unmatched


def trace_table(trace: List[dict]) -> pd.DataFrame:
    return pd.DataFrame([
        {"ラウンド": i + 1,
         "新たな提案": ", ".join(label(c) for c in r["proposed"]),
         "拒否": ", ".join(label(c) for c in r["rejected"]) or "—",
         "保留中": ", ".join(label(c) for c in r["held"])}
        for i, r in enumerate(trace) if r["proposed"]
    ])


def checks(inst: IQInstance, tutors, Y: List[Contract]) -> dict:
    return {
        "feasible": is_feasible(inst, tutors, Y),
        "iq_violations": iq_violations(inst, tutors, Y),
        "hm_stable": is_hm_stable(inst, tutors, Y),
    }


def lesson_cap_counterexample() -> Tuple[IQInstance, Dict[str, List[Tuple[str, str]]]]:
    """スライド 6.1：担当コマ数上限で耐戦略性が崩れる例（ランダム探索で発見したもの）"""
    students = {
        "S1": [("講師", "L1"), ("講師", "L3"), ("講師", "L2")],
        "S2": [("講師", "L1"), ("講師", "L2"), ("講師", "L3")],
        "S3": [("講師", "L2")],
    }
    tutors = {"講師": {"total": 4, "lessons": {"L1": 2, "L2": 2, "L3": 1},
                       "priority": [("S2", "L2"), ("S3", "L1"), ("S2", "L3"), ("S3", "L3"), ("S1", "L3"),
                                    ("S3", "L2"), ("S1", "L2"), ("S1", "L1"), ("S2", "L1")]}}
    lie = {"S1": [("講師", "L3"), ("講師", "L2")]}
    return IQInstance(students, tutors, {"講師": 1}), lie
