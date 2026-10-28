# 上位ハーネスの設定・API・制約

## 設定

接続設定は単一のJSONファイル（既定`harness.json`）だけから読みます。APIキーのみ環境変数です。コアへのモデル依存の変更はありません。

| 項目 | 指定場所 | 既定値 |
|---|---|---|
| base_url | JSON、必須 | なし。`http://localhost:8000/v1`等を利用者が設定 |
| model | JSON、必須 | なし |
| timeout | JSON、省略可 | LLM HTTP 60秒 |
| OPENAI_API_KEY | 環境変数 | なし。不要なローカルサーバーでは省略 |
| --db | CLIのサブコマンド前 | runs/state.sqlite3 |
| --max-steps | 既存CLI start | 1000、job/createも総上限1000 |
| --max-ticks | 既存CLI run | 100。readyで止まったら明示的にrun／talkで続行 |
| 生成Toolのtimeout | 候補spec | 5秒、独立テストrunは総100ステップ |
| JSON補正 | LLM関数 | 初回＋補正2回。通信障害や業務Toolを自動再実行しない |
| --root | CLI create | runs/extensions |

base_urlには`/chat/completions`を付けず、通常の`/v1`まで指定します。キーをURLやJSON設定へ含める設定は受け付けません。
構造化出力の専用APIを要求せず、通常のmessage.content内のJSON（またはJSONコードフェンス）を検証します。空本文・不正action・不正Schemaは完了扱いしません。

## 公開Toolと検証

`agent.build(config, business_specs, verifier, checked=False)`がRegistryとWorkflowを返します。
business_specsは明示的な公開リストです。内部の`agent.*`は公開リストから除外し、判断関数でTool名と入力Schemaを検証してから動的callへ渡します。
判断には目的・完了条件、Tool説明と入出力Schema、観測値、Tool名と引数・質問と回答の履歴、関連する知識を渡します。

verifierはユーザーが用意した信頼できる`module:function(state, result)`です。
`{"status":"pass|fail|unknown", "checks": [...]}`を返します。finish時にpass以外はrunを失敗させます。
checkedループでは業務Tool実行直後にも同じverifierを使います。中間結果も検証できるverifierを指定してください。
LLMのevidence文字列だけで業務成功とは判断しません。

## 知識

jobの`--requirements requirements.json`またはPython APIのrequest.knowledgeで、以下を指定します。

```json
[{"database":"C:/work/knowledge.sqlite3","scope":"measurements:sourceA","key":"unit"}]
```

scopeには適用条件を明示してください。Linuxでは`/work/knowledge.sqlite3`等の絶対パスにします。
未登録・条件外・仮説・例外付きの規則はunknownとして質問します。例外は自動解釈せず保守的に質問へ戻します。

回答例:

```json
{"knowledge":{"scope":"measurements:sourceA","key":"unit","value":"cm","exceptions":[]}}
```

保存するのはrequestで要求したscope/keyだけです。sourceには`kind:human`と回答由来のreferenceを記録します。
仮説を外部APIで保存する場合は`source:{"kind":"hypothesis","reference":"..."}`とし、実行を許可する知識としては採用しません。
旧形式のsource文字列は互換性のため保存可能ですが、agentの実行根拠としてはunknownになります。
同scope/keyで異なる回答は上書きせず失敗させます。確認後、新しいscope/keyを作って次のrunで選んでください。
必要条件の検出は明示的なrequirementsに限ります。一般的な未知検出や意味的な矛盾検出はありません。

## 候補の生成と版登録

`extensions.pipeline('workflow'|'tool')`もRegistryと通常のWorkflowを返します。
生成→専用ディレクトリへ保存→別runの受入テスト→版登録の順にcallします。
生成要求に`base_workflow`がある場合は、LLMが変更・追加ノードだけを返し、元の定義のコピーにマージして完全な候補を組み立てます。元のWorkflowは変更せず、組み立て後の候補全体を同じ検査と別runテストへ渡します。
依存Toolの一覧・入出力仕様は生成関数へ渡し、受入ケースは生成関数へ渡しません。
Toolでは通常・不正・境界ケースを呼び出し側が先に用意する必要があります。
候補ファイルはUUIDの専用ディレクトリへ保存し、登録ファイルは排他的に作成します。不合格候補は公開しません。
テスト後と版の読込時にファイルのSHA-256を照合します。候補・採用版をシステムが上書きすることはありません。

Workflowは不正遷移と未登録Toolを拒否します。動的callは、標準のagent.decideによる公開Tool検証を通す形式だけを候補として受け付けます。
Toolは標準ライブラリのimportだけを想定し、依存の自動インストールは行いません。
生成コードはホストへimportせず、既存のworkerを使ったタイムアウト付き別プロセスで実行します。
**これはセキュリティ上のサンドボックスではありません。** 生成コードは実行ユーザーの権限でファイルやネットワークへアクセスできます。ユーザー管理下のローカル利用を対象とします。
ASTのimport確認は依存範囲の確認であり、悪意あるコードを封じ込める検査ではありません。

採用済み版は`extensions.load_version(path)`でRegistryとして読み、新しいrunの上位Workflowから通常のcallで呼べます。
元の版も保存するため、旧版ファイルを選んで新runを開始できます。稼働中runのWorkflowとTool仕様スナップショットは変更しません。
コア同様、Python本体・依存Toolのソース・venv自体の完全な不変化はしません。公開ディレクトリの手動編集や削除は避けてください。

## 未確認・対象外

`192.168.11.12:8080`の`qwen3.8-flash-next`でexecute/ask/finish、実CSV、実LLMによるWorkflow／Tool／判断ループ候補の生成・テスト・登録・新run実行を確認しました。結果と失敗候補の履歴は[LIVE_VALIDATION.md](LIVE_VALIDATION.md)に記録しています。
HTTP fixtureの自動テストとは別に、実サーバーを呼ぶ`examples.live_validation`で検証しました。質問の回答は固定のテスト入力です。
Linuxでの今回の追加コードの実行、孫プロセスの停止は未確認です。
GUI、HTTPサーバー、MCP、Langflow、並列DAG、複数エージェント、依存自動導入、実行核の自己書換えは追加していません。

## Gitの引渡し

GitHub接続ユーザーはmiyokichiを確認しましたが、対象`miyokichi/seed-harness-core`は404で、接続には新規リポジトリ作成APIがありません。ローカルcommitは実施済み、リモート書き込みとpushは未確認です。
履歴を含む`dist/seed-harness-implemented.bundle`を用意しています。

```sh
git clone dist/seed-harness-implemented.bundle seed-harness-implemented
cd seed-harness-implemented
git log --oneline
```

privateリポジトリを用意し認証できた後、実際のURLをoriginへ設定して`implementation/llm-harness`をpushしてください。
元から存在した未追跡の`uv.lock`は変更・コミットしていません。
