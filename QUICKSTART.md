# 最初の5分

Python 3.11以上。展開したフォルダで、普段使うPythonから実行します。

```sh
python -m pip install -e .
python -m examples.simple
```

Windowsで`python`が使えなければ`py`に置き換えてください。
APIキー・モデル指定・設定ファイルの作成は不要です。
「質問して停止 → Engineを作り直す → 固定の回答で再開 → 関数実行」が動きます。
デモは自動実行で、実際の入力画面やLLMはまだ接続しません。

次に、ハーネス自身の判断ループと別venv連携を試します。

```sh
python -m examples.demo
```

## 編集するものは2つ

| ファイル／定義 | 何を書くか |
|---|---|
| Registry | 利用できる関数の名前と場所 |
| Workflow | 呼ぶ順序・分岐・質問・返す値 |

最小の関数登録はこれだけです。

```json
{"greet": {"kind": "python", "entry": "examples.simple:greet"}}
```

| 項目 | 意味 | 必要な場面 |
|---|---|---|
| `kind` | `python` / `subprocess` / `workflow` | 必須 |
| `entry` | `モジュール名:関数名` | 関数の場合 |
| `python` | 実行するPythonの絶対パス | 別venvの場合 |
| `cwd` | 対象プロジェクトの絶対パス | 別venvの場合 |
| `workflow` | 子Workflowの定義 | Workflowの場合 |
| `timeout` | 秒数。省略時300 | 別venv、必要なとき |
| `input_schema` / `output_schema` | 入出力の形式 | 必要なとき |

Workflowの命令は4つだけです。

| 命令 | 意味 |
|---|---|
| `call` | 登録した関数またはWorkflowを呼ぶ |
| `branch` | 値に応じて次の処理を選ぶ |
| `wait` | 質問と状態を保存し、回答まで停止 |
| `return` | 結果を返して終了 |

`examples/simple.py`が最小例、`examples/agent_loop.json`が判断ループです。
参照`{"$ref":"steps.ask"}`はaskノードの回答を意味します。
実運用ではStoreの保存先を固定してください。デモは一時保存のため終了時に消えます。

## 実CSVを2つのvenvで処理する

```sh
python -m examples.csv_demo
```

日本語CSVを読み取り、単位の質問で停止し、別CLIプロセスから回答して集計・検証します。
60 mm／3件、異なるvenv、出力ファイル内容、成功済み読込の非再実行を確認します。API設定は不要です。

## LLMで仕事を開始する

以下は実LLM向け手順です。`http://192.168.11.12:8080/v1`のモデル一覧で`qwen3.8-flash-next`を確認し、Tool実行・質問・再開・完了を実接続で検証しました。
この作業フォルダの`harness.json`はその接続先に設定済みです。別環境では次のように設定ファイルを用意します。

Windows PowerShell:

```powershell
Copy-Item harness.example.json harness.json
# harness.jsonのbase_urlとmodelを編集。base_urlは通常 /v1 まで。
# 認証が必要なサーバーのみ環境変数OPENAI_API_KEYを設定してください。
$env:PYTHONIOENCODING = 'utf-8'
.\.venv\Scripts\python.exe -m seed_harness.cli job "sevenを1回実行してから人に承認を質問し、承認後に結果7を返す" --config harness.json --registry examples/llm-registry.json --completion "Toolの観測値7と人のapproved=trueを確認" --verifier examples.llm_tools:verify --interactive
```

Linux:

```bash
cp harness.example.json harness.json
# harness.jsonのbase_urlとmodelを編集。認証時はOPENAI_API_KEYを環境変数へ設定。
.venv/bin/python -m seed_harness.cli job 'sevenを1回実行してから人に承認を質問し、承認後に結果7を返す' --config harness.json --registry examples/llm-registry.json --completion 'Toolの観測値7と人のapproved=trueを確認' --verifier examples.llm_tools:verify --interactive
```

質問への回答はJSONオブジェクトです。この例では`{"approved":true}`を入力します。
`--interactive`を省くと質問待ちでプロセスを終了します。`--json`で機械向けの状態全体を返します。

再開はWindows／Linux共通です。`python`は上記のvenvのPythonに読み替えてください。

```sh
python -m seed_harness.cli talk RUN_ID
```

ファイルから回答する場合、`answer.json`へUTF-8で`{"approved":true}`を保存します。

```sh
python -m seed_harness.cli status RUN_ID
python -m seed_harness.cli resume RUN_ID --pending-id PENDING_ID --answer answer.json --drive
```

状態は既定で`runs/state.sqlite3`へ保存します。変更するときはすべての操作で同じ`--db`をサブコマンドの前に指定します。
APIキーは状態に保存しないため、再開プロセスでも環境変数を渡してください。

## 小さなToolを生成する

以下は接続設定後に実行します。受入ケースは人が先に用意し、LLMには送信しません。

```sh
python -m seed_harness.cli create tool "valuesという数値リストを合計するrun(values)を標準ライブラリのみで作成。空リストは0、不正入力は拒否" --name sum.v1 --dependencies examples/empty-registry.json --cases examples/sum-cases.json --input-schema examples/sum-input-schema.json --output-schema examples/number-schema.json
```

候補は`runs/extensions/candidates/`へ保存します。通常・不正・境界ケースを別run／別プロセスで通過した版だけが`runs/extensions/versions/sum.v1.json`へ登録されます。

```sh
python -m seed_harness.cli export-version runs/extensions/versions/sum.v1.json --output sum-registry.json
```

`sum-registry.json`を`job --registry`や既存の`start --registry`へ指定できます。保存したToolの利用に生成LLMは不要です。
旧版へ戻すには旧版のファイルをexportしてください。版名は重複させず`sum.v2`のように増やします。

Workflowも同じ方法です。

```sh
python -m seed_harness.cli create workflow "sevenを1回呼び、その結果の整数7を返すWorkflowを作成" --name seven.flow.v1 --dependencies examples/llm-registry.json --cases examples/seven-workflow-cases.json --input-schema examples/empty-registry.json --output-schema examples/number-schema.json
```

登録されたWorkflowは通常のToolとして上位Workflowから呼べます。判断ループの候補版にも同じ生成・テスト・登録Workflowを使います。
`job --checked`はTool実行直後の検証を追加したループを選びます。この選択肢自体は事前に実装した版です。生成による候補版の登録と新runでの選択も実LLMで確認しました。既存Workflowの変更では、LLMが変更ノードを生成し、元の定義のコピーへ組み立てて候補全体を検証します。

## 実LLMの結合検証を再実行する

```powershell
.\.venv\Scripts\python.exe -m examples.live_validation
```

CLIの質問・別プロセス再開、実CSV、Workflow生成、Python Tool生成、判断ループ候補生成を実サーバーで検証し、`runs/live-UUID/report.json`へ保存します。質問への承認と単位は固定の検証用回答を渡します。Linuxでは`.venv/bin/python`を使います。
`--checks workflow_generation`などで項目を選べます。今回の実測結果と修正内容は[LIVE_VALIDATION.md](LIVE_VALIDATION.md)にまとめています。

`completed`はコア上ではreturn到達です。LLMの判断ループでは独立した検証関数が`pass`を返すまで完了させません。
生成コードの別プロセス実行はセキュリティ上のサンドボックスではありません。ユーザー管理下のローカル利用を対象とします。
