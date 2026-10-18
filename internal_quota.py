"""
Matching with Internal Quota（学習塾モデル）の環境定義

契約 x = (s, t, l) : 生徒 s が講師 t のコマ（lesson）l を受講する
  - Contract.proposer_id = s
  - Contract.receiver_id = t
  - Contract.terms = {"lesson": l}

講師 t の実行可能性（tutor-feasible）:
  |Y_tl| <= q_tl  (コマ別定員)  かつ  |Y_t| <= Q_t^S  (総定員)
この実行可能集合族は講師ごとの laminar matroid であり、
契約価値の和を最大化する選択関数は「優先順に見て、入れられるなら入れる」貪欲法で計算できる
（Kojima, Tamura and Yokoo 2018 の条件1）。

※ 講師ごとの制約は互いに独立（直和）なので、スライドの「プラットフォーム」が
   講師をまたいでどう順位付けしても選択結果は変わらない。
   PlatformReceiver はその同値性を確認するために用意している。
"""
from typing import Dict, List, Optional, Tuple

from matching_engine import Contract, Proposer, Receiver


def contract_id(student_id: str, tutor_id: str, lesson_id: str) -> str:
    return f"c_{student_id}_{tutor_id}_{lesson_id}"


def lesson_of(c: Contract) -> str:
    return c.terms["lesson"]


# ==========================================
# 講師（受入側）
# ==========================================
class TutorReceiver(Receiver):
    """
    コマ別定員 q_tl と総定員 Q_t をもつ講師。
    priority: 契約IDの優先順リスト（先頭ほど高評価）。リストにない契約は受け入れない。
    """

    def __init__(self, tutor_id: str, total_quota: int,
                 lesson_quotas: Dict[str, int], priority: List[str]):
        super().__init__(tutor_id)
        self.total_quota = total_quota
        self.lesson_quotas = dict(lesson_quotas)
        self.rank = {c_id: i for i, c_id in enumerate(priority)}

    def is_feasible(self, contracts: List[Contract]) -> bool:
        if len(contracts) > self.total_quota:
            return False
        counts: Dict[str, int] = {}
        for c in contracts:
            l = lesson_of(c)
            counts[l] = counts.get(l, 0) + 1
            if counts[l] > self.lesson_quotas.get(l, 0):
                return False
        return True

    def can_add(self, chosen: List[Contract], counts: Dict[str, int], c: Contract) -> bool:
        l = lesson_of(c)
        return (len(chosen) < self.total_quota
                and counts.get(l, 0) < self.lesson_quotas.get(l, 0))

    def choice_function(self, offered_contracts: List[Contract]) -> List[Contract]:
        acceptable = [c for c in offered_contracts if c.id in self.rank]
        acceptable.sort(key=lambda c: self.rank[c.id])
        chosen: List[Contract] = []
        counts: Dict[str, int] = {}
        for c in acceptable:
            if self.can_add(chosen, counts, c):
                chosen.append(c)
                counts[lesson_of(c)] = counts.get(lesson_of(c), 0) + 1
        return chosen

    def prefers(self, x: Contract, y: Contract) -> bool:
        """x ≻_t y"""
        return self.rank.get(x.id, float("inf")) < self.rank.get(y.id, float("inf"))


class LessonCapTutorReceiver(TutorReceiver):
    """
    スライド 6.1 の拡張：担当するコマ数の上限 Q_t^L を追加した講師。
    実行可能集合族が matroid にならないため、DA の耐戦略性・生徒最適性は保証されない。
    （貪欲法で選ぶ「素朴な」選択関数。比較・反例探索用）
    """

    def __init__(self, tutor_id: str, total_quota: int, lesson_quotas: Dict[str, int],
                 priority: List[str], max_lessons: int):
        super().__init__(tutor_id, total_quota, lesson_quotas, priority)
        self.max_lessons = max_lessons

    def is_feasible(self, contracts: List[Contract]) -> bool:
        if not super().is_feasible(contracts):
            return False
        return len({lesson_of(c) for c in contracts}) <= self.max_lessons

    def can_add(self, chosen, counts, c) -> bool:
        if not super().can_add(chosen, counts, c):
            return False
        used = {l for l, n in counts.items() if n > 0}
        return lesson_of(c) in used or len(used) < self.max_lessons


class PlatformReceiver(Receiver):
    """
    スライドの「プラットフォーム」：全講師を代表し、全契約上の強順序 ≻_T で貪欲に選ぶ。
    使うときは全契約の receiver_id をこのIDにそろえ、terms["tutor"] に講師IDを入れる。
    """

    def __init__(self, platform_id: str, tutors: Dict[str, TutorReceiver], global_priority: List[str]):
        super().__init__(platform_id)
        self.tutors = tutors
        self.rank = {c_id: i for i, c_id in enumerate(global_priority)}

    def choice_function(self, offered_contracts: List[Contract]) -> List[Contract]:
        acceptable = [c for c in offered_contracts if c.id in self.rank]
        acceptable.sort(key=lambda c: self.rank[c.id])
        chosen: List[Contract] = []
        chosen_by_t: Dict[str, List[Contract]] = {}
        counts_by_t: Dict[str, Dict[str, int]] = {}
        for c in acceptable:
            t = self.tutors[c.terms["tutor"]]
            ch = chosen_by_t.setdefault(t.id, [])
            cnt = counts_by_t.setdefault(t.id, {})
            if t.can_add(ch, cnt, c):
                ch.append(c)
                cnt[lesson_of(c)] = cnt.get(lesson_of(c), 0) + 1
                chosen.append(c)
        return chosen


# ==========================================
# インスタンス生成
# ==========================================
class IQInstance:
    """
    students : {s: [(t, l), ...]}           生徒の希望順（許容可能な契約のみ）
    tutors   : {t: {"total": Q_t, "lessons": {l: q_tl}, "priority": [(s, l), ...]}}
    """

    def __init__(self, students: Dict[str, List[Tuple[str, str]]],
                 tutors: Dict[str, dict], max_lessons: Optional[Dict[str, int]] = None):
        self.students = students
        self.tutors_spec = tutors
        self.max_lessons = max_lessons  # None なら通常の Internal Quota

        self.contracts: Dict[str, Contract] = {}
        for t, spec in tutors.items():
            for l in spec["lessons"]:
                for s in students:
                    c_id = contract_id(s, t, l)
                    self.contracts[c_id] = Contract(c_id, s, t, {"lesson": l, "tutor": t})

    def student_pref_ids(self, s: str, pref: Optional[List[Tuple[str, str]]] = None) -> List[str]:
        pref = self.students[s] if pref is None else pref
        return [contract_id(s, t, l) for t, l in pref]

    def build_tutors(self) -> Dict[str, TutorReceiver]:
        out: Dict[str, TutorReceiver] = {}
        for t, spec in self.tutors_spec.items():
            prio = [contract_id(s, t, l) for s, l in spec["priority"]]
            if self.max_lessons is not None:
                out[t] = LessonCapTutorReceiver(t, spec["total"], spec["lessons"], prio, self.max_lessons[t])
            else:
                out[t] = TutorReceiver(t, spec["total"], spec["lessons"], prio)
        return out

    def build_proposers(self, override: Optional[Dict[str, List[Tuple[str, str]]]] = None) -> Dict[str, Proposer]:
        override = override or {}
        return {s: Proposer(s, self.student_pref_ids(s, override.get(s))) for s in self.students}

    def platform_priority(self, tutor_order: List[str]) -> List[str]:
        """
        各講師の順位を尊重する全体順序 ≻_T の一例：
        (講師内の順位, 講師の並び順) の辞書式。講師内の順序は保たれる。
        """
        keyed = []
        for t, spec in self.tutors_spec.items():
            for r, (s, l) in enumerate(spec["priority"]):
                keyed.append((r, tutor_order.index(t), contract_id(s, t, l)))
        keyed.sort()
        return [c for _, _, c in keyed]
