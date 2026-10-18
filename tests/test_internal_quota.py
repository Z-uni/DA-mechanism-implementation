"""
ランダムな小規模インスタンスで、スライドの主張を数値的に確認する
    pytest -q tests/test_internal_quota.py
"""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from matching_engine import Contract, generalized_deferred_acceptance  # noqa: E402
from internal_quota import IQInstance, PlatformReceiver  # noqa: E402
from matching_checks import (  # noqa: E402
    find_profitable_misreport, is_feasible, is_hm_stable, is_iq_stable,
    all_feasible_matchings, run_da, student_optimal_check,
)


def random_instance(rng, n_s=4, n_t=2, n_l=2, max_lessons=None):
    S = [f"s{i}" for i in range(1, n_s + 1)]
    T = [f"t{i}" for i in range(1, n_t + 1)]
    L = [f"l{i}" for i in range(1, n_l + 1)]
    tutors = {}
    for t in T:
        lessons = {l: rng.randint(1, 2) for l in L}
        total = rng.randint(1, sum(lessons.values()))
        prio = [(s, l) for s in S for l in L]
        rng.shuffle(prio)
        tutors[t] = {"total": total, "lessons": lessons, "priority": prio}
    students = {}
    all_opts = [(t, l) for t in T for l in L]
    for s in S:
        k = rng.randint(1, len(all_opts))
        students[s] = rng.sample(all_opts, k)
    ml = {t: max_lessons for t in T} if max_lessons else None
    return IQInstance(students, tutors, ml)


def test_da_is_feasible_iq_stable_and_hm_stable():
    rng = random.Random(0)
    for _ in range(300):
        inst = random_instance(rng)
        tutors = inst.build_tutors()
        Y = run_da(inst)
        assert is_feasible(inst, tutors, Y)
        assert is_iq_stable(inst, tutors, Y)
        assert is_hm_stable(inst, tutors, Y)


def test_iq_stability_equals_hm_stability():
    """Proposition 5：実行可能なマッチング全体で IQ 安定 ⇔ HM 安定"""
    rng = random.Random(1)
    for _ in range(60):
        inst = random_instance(rng, n_s=3)
        tutors = inst.build_tutors()
        for Y in all_feasible_matchings(inst, tutors):
            assert is_iq_stable(inst, tutors, Y) == is_hm_stable(inst, tutors, Y)


def test_student_optimal():
    rng = random.Random(2)
    for _ in range(80):
        assert student_optimal_check(random_instance(rng, n_s=3))


def test_strategy_proof_for_students():
    rng = random.Random(3)
    for _ in range(80):
        assert find_profitable_misreport(random_instance(rng, n_s=3), max_len=3) is None


def test_platform_choice_equals_per_tutor_choice():
    """講師をまたぐ全体順序 ≻_T を変えても結果は講師別の選択と同じ"""
    rng = random.Random(4)
    for _ in range(200):
        inst = random_instance(rng)
        per_tutor = {c.id for c in run_da(inst)}
        tutors = inst.build_tutors()
        order = list(tutors)
        rng.shuffle(order)
        platform = PlatformReceiver("platform", tutors, inst.platform_priority(order))
        contracts = {cid: Contract(cid, c.proposer_id, "platform", c.terms) for cid, c in inst.contracts.items()}
        res = generalized_deferred_acceptance(inst.build_proposers(), {"platform": platform}, contracts)
        assert {c.id for c in res} == per_tutor


def test_lesson_cap_extension_breaks_strategy_proofness():
    """6.1 の拡張（担当コマ数上限）では、耐戦略性が崩れる例が見つかる"""
    rng = random.Random(5)
    found = None
    for _ in range(3000):
        inst = random_instance(rng, n_s=3, n_t=1, n_l=3, max_lessons=1)
        found = find_profitable_misreport(inst, max_len=2)
        if found:
            break
    assert found is not None
