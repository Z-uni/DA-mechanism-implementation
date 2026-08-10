from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class Contract:
    """
    あらゆる環境で使い回せる「契約」の抽象クラス
    """
    def __init__(self, contract_id: str, proposer_id: str, receiver_id: str, terms: Dict[str, Any] = None):
        self.id = contract_id
        self.proposer_id = proposer_id
        self.receiver_id = receiver_id
        # terms には、時間枠、給与、科目など、ドメイン特有の条件を辞書形式で自由に入れる
        self.terms = terms if terms is not None else {}

    def __repr__(self):
        return f"Contract({self.id}: {self.proposer_id} -> {self.receiver_id}, terms={self.terms})"

class Proposer:
    """
    提案側（生徒、研修医、求職者など）
    ※ 基本的なDAの前提として、Proposerは単一契約を希望する（Unit Demand）とします。
    """
    def __init__(self, proposer_id: str, pref_contract_ids: List[str]):
        self.id = proposer_id
        self.pref_contract_ids = pref_contract_ids
        self.proposal_idx = 0

    def get_next_best_contract(self) -> Optional[str]:
        """まだ拒否されていない最も希望順位の高い契約のIDを返す"""
        if self.proposal_idx < len(self.pref_contract_ids):
            c_id = self.pref_contract_ids[self.proposal_idx]
            self.proposal_idx += 1
            return c_id
        return None

class Receiver(ABC):
    """
    受入側（学習塾の講師、病院、企業など）の【抽象ベースクラス】
    このクラスを直接は使わず、環境ごとのルールを持たせた子クラスを作って使います。
    """
    def __init__(self, receiver_id: str):
        self.id = receiver_id

    @abstractmethod
    def choice_function(self, offered_contracts: List[Contract]) -> List[Contract]:
        """
        選択関数 C_h(X')
        ※ このメソッドは必ずサブクラス（子クラス）で実装しなければエラーになります。
        ※ IDではなく「Contractオブジェクトのリスト」を受け取ることで、
           terms（条件）の中身を見た複雑な制約判定ができるようにしています。
        """
        pass

# ==========================================
# マッチングエンジン本体（環境に依存しない）
# ==========================================
def generalized_deferred_acceptance(
    proposers: Dict[str, Proposer], 
    receivers: Dict[str, Receiver], 
    contracts: Dict[str, Contract]
) -> List[Contract]:
    """
    一般化DAアルゴリズム (Proposer-Proposing)
    """
    # 各Receiverが現在「保留」している契約オブジェクトのリスト
    held_contracts: Dict[str, List[Contract]] = {r_id: [] for r_id in receivers.keys()}
    
    # 未割当（提案可能）なProposerのリスト
    unassigned_proposers: List[Proposer] = list(proposers.values())

    while unassigned_proposers:
        # 1. 提案フェーズ
        new_proposals: Dict[str, List[Contract]] = {r_id: [] for r_id in receivers.keys()}
        
        for p in unassigned_proposers:
            next_contract_id = p.get_next_best_contract()
            if next_contract_id:
                contract = contracts[next_contract_id]
                new_proposals[contract.receiver_id].append(contract)

        # 2. 選択・拒否フェーズ
        rejected_contracts: List[Contract] = []
        
        for r_id, receiver in receivers.items():
            if new_proposals[r_id]: 
                # 保留中の契約と新規提案を合わせたプール
                pool = held_contracts[r_id] + new_proposals[r_id]
                
                # 環境固有の選択関数を実行（Receiverの子クラスで定義されたロジック）
                chosen = receiver.choice_function(pool)
                
                # 拒否された契約を特定
                chosen_ids = {c.id for c in chosen}
                for c in pool:
                    if c.id not in chosen_ids:
                        rejected_contracts.append(c)
                
                held_contracts[r_id] = chosen

        # 3. キューの更新
        unassigned_proposers = []
        for c in rejected_contracts:
            unassigned_proposers.append(proposers[c.proposer_id])

    # 結果の統合
    final_matching = []
    for chosen_list in held_contracts.values():
        final_matching.extend(chosen_list)
        
    return final_matching

# ==========================================
# 1. 環境固有の Receiver（受入側）の定義
# ==========================================
class SimpleReceiver(Receiver):
    """
    標準的な多対一マッチング（病院・研修医）および
    一対一マッチング（婚活市場）のための受入側クラス
    """
    def __init__(self, receiver_id: str, capacity: int, pref_proposer_ids: List[str]):
        super().__init__(receiver_id)
        self.capacity = capacity
        # 相手（Proposer）のIDの選好順リスト（インデックスが小さいほど高評価）
        self.pref_proposer_ids = pref_proposer_ids

    def choice_function(self, offered_contracts: List[Contract]) -> List[Contract]:
        """
        受入側の選択ロジック:
        「提案された契約の中から、自分の選好リストにある相手だけを残し、
        好きな順に並べ替えて、定員の数だけ選ぶ」
        """
        # 1. 許容可能（acceptable）な契約のみをフィルタリング
        acceptable_contracts = [
            c for c in offered_contracts 
            if c.proposer_id in self.pref_proposer_ids
        ]
        
        # 2. 受入側の選好順にソート
        acceptable_contracts.sort(
            key=lambda c: self.pref_proposer_ids.index(c.proposer_id)
        )
        
        # 3. 定員（capacity）の数だけ上位から採用して返す
        return acceptable_contracts[:self.capacity]

