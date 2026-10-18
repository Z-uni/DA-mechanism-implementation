注：
　本プログラムはGale and Shapley (1962)にて提案されたDA(Defferred Acceptance) Mechanismを実装しています。なお、標準的DAについてはプログラムの構築・確認にあたっては栗野・熊野 (2024)を参考にしています。
　AIと共同でコーディングを行っているため、もしプログラムが標準的なDAアルゴリズムと異なる挙動を示す(SPを満たさない、安定性マッチングを生まない等々)場合は、以下アドレスまでご連絡ください。確認の上修正いたします。

"alex01.miyazawa@gmail.com"

[2026/10/18追記]：新たに学習塾モデルを実装しました。アルゴリズムはHatfield and Milgrom (2005)の generalized DA mechanismを参考にしていますが、安定配分・提案側SP・提案側最適性などはKojima et al. (2018)を参考に保証しています。余裕があるときに証明や想定適用状況を記載したmdファイルを掲載しておきます。

References:
栗野盛光, 熊野太郎 (2024) 『マーケットデザイン総論』 共立出版
Gale, D., Shapley, L.S., 1962. College admissions and the stability of marriage. Am. Math. Mon.69 (1), 9–15.
Kojima, F., Tamura, A., Yokoo, M., 2018. Designing matching mechanisms under constraints: An approach from discrete convex analysis. J. Econ. Theory 176, 803–833.
Hatfield, J.W., Milgrom, P.R., 2005. Matching with contracts. Am. Econ. Rev. 95 (4), 913–935.


――――――――――――――――――――
学習塾モデル（Matching with Internal Quota）
　pages/1_学習塾マッチング.py   Streamlit ページ（streamlit run app.py で左メニューに表示）
　internal_quota.py            講師の選択関数（コマ別定員・総定員の下での貪欲法）
　matching_checks.py           実行可能性・IQ安定性・HM安定性・耐戦略性/生徒最適性の総当たり検証
　iq_io.py                     表データの読み込みと結果表の作成
　tests/test_internal_quota.py ランダムな小規模例での数値検証（python -m pytest -q）
References（追加）:
