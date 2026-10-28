# 実LLM検証（2026-10-28）

## 接続確認

- base_url: `http://192.168.11.12:8080/v1`
- モデル一覧: `GET /v1/models`
- 正式モデルID: `qwen3.8-flash-next`
- サーバーのaliasesも同じ文字列。owned_byは`llamacpp`。
- `harness.json`へ設定済み。ファイルはGit管理対象外。

## 再実行

```powershell
$env:PYTHONIOENCODING = 'utf-8'
.\.venv\Scripts\python.exe -m examples.live_validation
```

Linuxでは`.venv/bin/python -m examples.live_validation`を使用します。
出力は既定で`runs/live-UUID/`へ保存します。`--checks`で検証を選択でき、`--output`は既存フォルダを上書きしません。
すべて実サーバーを呼び、モックは使用しません。承認`approved=true`と単位`cm`は検証ドライバーが渡す固定のテスト回答です。

## 確認済みの動作

| 検証 | 結果 | 根拠 |
|---|---|---|
| Tool実行→質問→別CLIプロセスで回答→完了 | pass | run `3d1a3f5e5b1b406eb18bb16950d99fbf`。sevenは1回だけ実行し、独立verifierがpass |
| 実CSV処理 | pass | run `c0522bef9a034962934f72e625014a68`。日本語CSV、2つのvenv、単位質問、60 mm／3件、ファイル内容を確認 |
| Python Tool実生成→別プロセステスト→登録→新runで利用 | pass | 生成run `402820eb62b34a2b9d4f278607a6a05e`。新run `593c76f4b91a474fb72eb0510f76c42d`で`[4,5]`→9 |
| Workflow実生成→テスト→登録→上位Workflowから利用 | pass | 生成run `b6de2c2c36a6451aac19a199e235403f`。新run `0ba707a7343041e9be572613fe0e87f2`で7 |
| 判断ループ候補の実生成→登録→新runから実行 | pass | 生成run `5f68363b491b427d8842c201458a893e`。新run `0c400fdf8bf949f5bf930ba8009826cc`。Tool実行直後とfinish前にverifierを2回実行 |

最終5項目の集約結果は`runs/live-qwen-final-report.json`です。
詳細は`runs/live-qwen-validation-v2/report.json`、`runs/live-qwen-workflow-v3/report.json`、`runs/live-qwen-loop-v3/report.json`と各ディレクトリの`state.sqlite3`、`extensions/`、`csv/`に保存しています。
生成Toolは呼び出し側が用意した通常・不正入力・境界ケースを通過してから公開しました。

## 検証中に見つかった問題

1. 業務ToolがWorkflowの場合、判断関数へ渡す定義内の`$ref`を親Workflowの参照として解決してしまっていました。Tool定義をJSON文字列として受け渡し、判断関数内で読み戻すよう修正しました。Workflow内の参照とJSON Schemaの参照の回帰テストを追加しました。
2. 最初のWorkflow候補は形式が不正で、次の候補はノード`work`の出力を`steps.seven`で参照していました。いずれも公開されていません。生成指示に具体的なWorkflow形式とTool ID／ノードIDの区別を追加し、存在しないノードへの参照を候補検査で拒否するようにしました。
3. 判断ループ全体を再出力させる生成は3回ともJSONとして受理できませんでした。既存Workflowを変更するときは、変更ノードだけを実LLMに生成させ、元の定義のコピーへ組み立てる方式を追加しました。元の版を保持したうえで、完成した候補全体を同じ検査・別runテスト・新版登録Workflowで扱います。この方式で実生成・検証・登録・新runからの選択が成功しました。

初回の失敗も`runs/live-qwen-validation/report.json`に保持しています。
自動テストは35件成功しました。実LLMの動作にはモデルの出力による揺れがあるため、候補の検証と受入テストは毎回実行します。
