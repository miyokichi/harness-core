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

## この初版の限界

LLMは未接続。自己変更も未実装です。今あるのは、それらを通常の関数・Workflowとして載せる実行核です。
`completed`はreturn到達を意味します。業務上の正しさは別の検証関数で確認します。
