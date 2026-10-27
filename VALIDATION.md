# 検証結果

## 今回の実装の検証（2026-10-28）

環境: Windows / CPython 3.13、作業フォルダの`.venv/Scripts/python.exe`。

| 項目 | 実装 | 今回の確認 |
|---|---|---|
| LLM接続関数・公開Tool制限・JSON補正 | 済 | ローカルHTTP fixture。実LLMは接続先未指定で未確認 |
| execute / ask / finish と完了検証 | 済 | fixtureによる関数テストと別CLIプロセスで確認 |
| 自然言語CLI・対話・保存再開 | 済 | job起動→質問待ちで終了→別プロセスでresume --drive成功 |
| 実CSV・2つのvenv・日本語パス | 済 | Windows実機で60 mm／3件、内容、異なるsys.prefixを確認 |
| 知識保存・適用条件照合 | 済 | 不足・同条件・条件外・矛盾・仮説・例外をテスト |
| Workflow生成・検証・登録 | 済 | 固定生成応答から別runテスト・上位Workflowで呼出。実LLM生成は未確認 |
| Python Tool生成・検証・登録 | 済 | 固定生成応答、実別プロセス、通常／不正／境界、タイムアウト、不採用、版選択を確認 |
| 判断ループ候補の登録・選択 | 済 | 固定生成応答で2版を採用し、新runで実行。追加検証と失敗時停止を確認 |
| Git履歴・段階別commit | 済 | 同梱bundleの19f23afを基点にローカルブランチへ記録 |
| GitHub読み書き・push | 外部接続待ち | ユーザー確認済み。対象repoは404。作成APIなし、push未確認 |
| GUI・MCP・並列DAG・依存自動導入・実行核自己書換え | 未実装 | 今回の対象外 |

`python -m unittest discover -s tests -v`: **33件成功**。既存22件を今回再実行し、新規11件を追加。
`python -m examples.simple`、`python -m examples.demo`、`python -m examples.csv_demo`: **成功**。
`uv build --wheel --offline --out-dir dist`: **成功**。wheelは`dist/seed_harness_core-0.1.1-py3-none-any.whl`。
既存venvにはpipがないため`python -m pip wheel`は実行できず、uvのローカルキャッシュを使ったオフラインビルドで確認しました。
旧デモの寸法候補はサンプル、追加CSVデモは実ファイル処理です。
生成Toolはホストへimportせず、5秒上限の別プロセスで実行。不合格候補の非公開、旧版保持、候補改変検知を確認しました。
2種類の判断ループを同じ実行核でテスト・登録・新runで選択し、verifier実行が1回から2回になることをイベント履歴で確認しています。

Linuxでの追加実装、実LLM、実LLMによる自然言語からの候補生成、GitHub push、孫プロセス停止は今回未確認です。
以下は配布物に残っていた以前の検証履歴です。今回の実行結果とは区別してください。

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
