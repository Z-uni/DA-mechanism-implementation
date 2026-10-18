"""
Internal Quota モデルの性質チェック
  - 実行可能性（Definition 1）
  - ブロッキング契約と IQ 安定性（Definition 2, 3）
  - HM 安定性（選択関数ベース）
  - 総当たりによる生徒最適性・耐戦略性の確認（小規模インスタンス用）
"""
from itertools import combinations, permutations, product
from typing import Dict, List, Optional, Tuple

from matching_engine import Contract, generalized_deferred_acceptance
from internal_quota import IQInstance, TutorReceiver, lesson_of


def group_by_tutor(Y: List[Contract]) -> Dict[str, List[Contract]]:
    out: Dict[str, List[Contract]] = {}
    for c in Y:
        out.setdefault(c.receiver_id, []).append(c)
    return out


def student_rank(inst: IQInstance, s: str) -> Dict[str, int]:
    return {c_id: i for i, c_id in enumerate(inst.student_pref_ids(s))}


def student_assignment(Y: List[Contract]) -> Dict[str, Contract]:
    return {c.proposer_id: c for c in Y}


def is_feasible(inst: IQInstance, tutors: Dict[str, TutorReceiver], Y: List[Contract]) -> bool:
    seen = set()
    for c in Y:
        if c.proposer_id in seen:
            return False
        seen.add(c.proposer_id)
        if c.id not in student_rank(inst, c.proposer_id):
            return False
    by_t = group_by_tutor(Y)
    return all(tutors[t].is_feasible(by_t.get(t, [])) for t in tutors)


def student_prefers(inst: IQInstance, x: Contract, Y_s: Optional[Contract]) -> bool:
    """x ≻_s Y_s（Y_s=None は未割当）"""
    rank = student_rank(inst, x.proposer_id)
    if x.id not in rank:
        return False
    return Y_s is None or rank[x.id] < rank[Y_s.id]


def blocking_contracts(inst: IQInstance, tutors: Dict[str, TutorReceiver], Y: List[Contract]) -> List[Contract]:
    """Definition 2 のブロッキング契約をすべて返す"""
    assign = student_assignment(Y)
    by_t = group_by_tutor(Y)
    Y_ids = {c.id for c in Y}
    out = []
    for x in inst.contracts.values():
        if x.id in Y_ids or not student_prefers(inst, x, assign.get(x.proposer_id)):
            continue
        t = tutors[x.receiver_id]
        if x.id not in t.rank:
            continue
        Y_t = by_t.get(t.id, [])
        n_tl = sum(1 for y in Y_t if lesson_of(y) == lesson_of(x))
        if n_tl < t.lesson_quotas.get(lesson_of(x), 0) or any(t.prefers(x, y) for y in Y_t):
            out.append(x)
    return out


def iq_violations(inst: IQInstance, tutors: Dict[str, TutorReceiver], Y: List[Contract]) -> List[Tuple[Contract, str]]:
    """Definition 3 に反するブロッキング契約と理由"""
    by_t = group_by_tutor(Y)
    out = []
    for x in blocking_contracts(inst, tutors, Y):
        t = tutors[x.receiver_id]
        Y_t = by_t.get(t.id, [])
        l = lesson_of(x)
        n_tl = sum(1 for y in Y_t if lesson_of(y) == l)
        q_tl = t.lesson_quotas.get(l, 0)
        worse = [y for y in Y_t if t.prefers(x, y)]
        if worse and (any(lesson_of(y) == l for y in worse) or n_tl != q_tl):
            out.append((x, "条件1違反：より低順位の契約と入れ替えて実行可能にできる"))
        elif n_tl < q_tl and len(Y_t) != t.total_quota:
            out.append((x, "条件2違反：コマにも総定員にも空きがある"))
    return out


def is_iq_stable(inst, tutors, Y) -> bool:
    return is_feasible(inst, tutors, Y) and not iq_violations(inst, tutors, Y)


def is_hm_stable(inst: IQInstance, tutors: Dict[str, TutorReceiver], Y: List[Contract]) -> bool:
    """Ch_T(Y)=Y かつ、x ≻_s Y_s で x ∈ Ch_t(Y_t ∪ {x}) となる x が存在しない"""
    by_t = group_by_tutor(Y)
    for t_id, t in tutors.items():
        Y_t = by_t.get(t_id, [])
        if {c.id for c in t.choice_function(Y_t)} != {c.id for c in Y_t}:
            return False
    assign = student_assignment(Y)
    Y_ids = {c.id for c in Y}
    for x in inst.contracts.values():
        if x.id in Y_ids or not student_prefers(inst, x, assign.get(x.proposer_id)):
            continue
        t = tutors[x.receiver_id]
        if x.id in {c.id for c in t.choice_function(by_t.get(t.id, []) + [x])}:
            return False
    return True


# ==========================================
# 実行と総当たり検証
# ==========================================
def run_da(inst: IQInstance, override=None) -> List[Contract]:
    tutors = inst.build_tutors()
    return generalized_deferred_acceptance(inst.build_proposers(override), tutors, inst.contracts)


def all_feasible_matchings(inst: IQInstance, tutors) -> List[List[Contract]]:
    """生徒ごとに『未割当 or 許容可能な契約』を総当たり（小規模専用）"""
    options = []
    for s in inst.students:
        options.append([None] + [inst.contracts[c] for c in inst.student_pref_ids(s)])
    out = []
    for combo in product(*options):
        Y = [c for c in combo if c is not None]
        if is_feasible(inst, tutors, Y):
            out.append(Y)
    return out


def student_optimal_check(inst: IQInstance) -> bool:
    """DA の結果が、全 IQ 安定マッチングの中で全生徒にとって最良か"""
    tutors = inst.build_tutors()
    da = student_assignment(run_da(inst))
    for Y in all_feasible_matchings(inst, tutors):
        if not is_iq_stable(inst, tutors, Y):
            continue
        other = student_assignment(Y)
        for s in inst.students:
            rank = student_rank(inst, s)
            r_da = rank[da[s].id] if s in da else len(rank)
            r_y = rank[other[s].id] if s in other else len(rank)
            if r_y < r_da:
                return False
    return True


def misreports(options: List[Tuple[str, str]], max_len: int):
    for k in range(0, min(max_len, len(options)) + 1):
        for sub in combinations(options, k):
            for perm in permutations(sub):
                yield list(perm)


def find_profitable_misreport(inst: IQInstance, max_len: int = 3):
    """
    生徒の虚偽申告で真の選好の下で得をするケースを探す。
    見つかれば (生徒, 虚偽の希望, 正直時の契約, 虚偽時の契約) を返す。
    """
    truthful = student_assignment(run_da(inst))
    all_options = [(t, l) for t, spec in inst.tutors_spec.items() for l in spec["lessons"]]
    for s in inst.students:
        rank = student_rank(inst, s)
        r_true = rank[truthful[s].id] if s in truthful else len(rank)
        for lie in misreports(all_options, max_len):
            res = student_assignment(run_da(inst, override={s: lie}))
            if s in res and res[s].id in rank and rank[res[s].id] < r_true:
                return s, lie, truthful.get(s), res[s]
    return None
