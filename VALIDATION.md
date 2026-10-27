# 検証結果

環境: Linux / CPython 3.12.14。

## 自動テスト

`python -m unittest discover -s tests -v`: **22件成功**。

- 参照解決、通常呼び出し、分岐、反復、変数更新。
- 入出力Schema、未登録Tool拒否、不正遷移拒否、非有限数拒否。
- 入れ子Workflow、入れ子での回答待ち、親での例外処理。
- 定義のスナップショット、失敗時のフレーム保持。
- 新Engine／別CLIプロセスからの停止再開、古い質問IDの拒否。
- 再開時に成功済みの外部書き込みを繰り返さないこと。
- revision競合と同一ノードの同時呼び出し防止。
- 総ステップ上限、明示的な復旧・再試行。
- 実際にホストプロセスを強制終了し、結果不明状態が残ること。
- 別プロセスでの日本語パス・日本語ログ、結果JSONとの分離。
- Worker例外、タイムアウト、JSON化失敗。
- 知識の適用範囲、同一保存の冪等性、矛盾の拒否。

## 結合デモ

`python -m examples.demo`: **成功**。

独立したvenvを2個作成し、質問→停止→再起動したEngineで回答→知識保存→入れ子Workflow→別venvで処理→検証→完了を確認。
次回作業では質問せずに完了。日本語ログと、異なる`sys.prefix`での実行を確認。

## パッケージ

`pip wheel --no-deps --no-build-isolation .`: **成功**。

## 未確認の範囲

Windows実機、実LLM、little_agentとの直接接続、実PPT/Excel、Langflow/MCP、孫プロセスの停止。
これらを動作確認済みとはしていない。

## 2026-10-28 更新時の再検証（v0.1.1）

- 既存22件のテストを今回の環境で再実行し全件成功。
- `python -m examples.simple`成功。設定なしで停止・新Engineからの再開を確認。
- `python -m examples.demo`成功。2つのvenv、知識保存・再利用を確認。
- `pip wheel --no-deps --no-build-isolation .`成功。
- Windows実機・実LLM・GitHubへのリモート書き込みは未検証。
