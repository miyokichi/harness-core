# 設計メモ

## 小さな核に固定するもの

1. 登録された関数を呼ぶ。
2. 次のノードを決める。
3. 状態と履歴を保存する。
4. 待機・再開・例外を扱う。

業務知識やLLMの判断方針は固定しない。
エージェント自身も`examples/agent_loop.json`のWorkflowで構成する。
WorkflowをToolとして登録できるため、実行階層が増えても呼び出し側の形式は変わらない。

## モジュール

| ファイル | 責務 |
|---|---|
| `engine.py` | Workflowの解釈、フレームスタック、遷移、待機、復旧 |
| `registry.py` | Tool仕様、Workflow定義の検証、JSON Schema検証 |
| `executor.py` | 同一プロセス／別Python環境で関数を実行 |
| `worker.py` | 対象venvでimport・関数呼び出し。外部依存なし |
| `store.py` | SQLiteの状態・イベント・revision更新 |
| `values.py` | JSON値の複製、明示的な参照の解決 |
| `knowledge.py` | 上位Toolとして使う知識保存の小さな実装例 |
| `cli.py` | UI非依存の操作例 |
| `llm.py` | 通常JSON応答を検証するChat Completionsトランスポート、補正上限 |
| `agent.py` | 公開Toolの判断、条件照合、履歴、回答保存、独立検証、2種類の判断ループ |
| `csv_tools.py` | 実CSVの読込・単位変換集計・独立検証 |
| `extensions.py` | 候補生成・保存・別runテスト・不変な版登録を構成する関数とWorkflow |

これらの上位層の利用方法と制約は[HARNESS.md](HARNESS.md)を参照。
コアの命令・状態形式・Registry実装は今回変更していません。

## 実行フレーム

各フレームは`flow / pc / scope / parent / output_schema`を持つ。
`scope`は入力・直近ノード出力・変数で構成する。
子Workflow呼び出しではフレームを積み、returnで親のcall出力へ返す。
入れ子内のwaitでもスタック全体を永続化する。

## 状態更新と競合

ノード実行の前に`running`と試行tokenを保存する。
成功後に出力と次の位置、失敗時にエラーを保存する。
各更新は`WHERE revision = old_revision`を使う。
同じ状態を読んだ複数の実行器のうち、claimに成功した1個だけがそのノードを呼べる。
状態とイベントは同じSQLiteトランザクションに入る。

長時間の外部操作中はDBトランザクションを保持しない。
そのため、外部操作が成功してから状態保存までの間に落ちると結果は不明になる。
この場合に自動リプレイしないのが`running / recover / retry`の役割。
UI側も`running`を単なる「再開可能」と扱ってはいけない。

## バージョン

run開始時にWorkflowと全Tool仕様をJSONとして保存する。
開始後のRegistry変更はそのrunに反映しない。
コード・venvはスナップショット対象外なので、本番ではバージョン別ディレクトリやGitのcommitをTool仕様のメタデータへ追加する。
同じRegistry内のIDは重複登録できない。`tool.v1 / tool.v2`のように明示的に分ける。

## 上位層として追加できるもの

| 機能 | コアを変えずに実装する位置 |
|---|---|
| 実LLM | `agent.decide`関数 |
| 質問の質・未知検出 | Plannerの必要条件・根拠チェック |
| concept-learning | 証拠収集・仮説・検証を行うWorkflow |
| 検証 | Python関数／検証Workflow |
| Tool作成 | コード生成→別環境で検証→新Registryの公開Workflow |
| ロールバック | 過去の不変なRegistry/Workflow版を新runへ指定 |
| Langflow | Python APIを呼ぶコンポーネント、後にフロー変換 |
| MCP | Registryの公開・実行要求を扱うアダプター |

自己変更ではまず「候補版を別runで検証し、次のrunから採用する」。
稼働中のrunの定義を書き換えるAPIは提供していない。
実行核そのものの更新は、通常のコード変更・テスト・配布として扱う。
