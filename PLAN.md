# 次の開発計画

## 今回の実装状況（2026-10-28）

1. `llm.py / agent.py`にChat Completions接続・公開Toolの制限・独立した完了検証を実装。実LLM接続は未確認。
2. `cli job / talk / resume --drive`を実装。HTTP fixtureと別CLIプロセスで起動・回答・継続を確認。
3. `examples.csv_demo`で実CSV・異なる2つのvenv・日本語パス・単位質問・値と件数の検証を確認。
4. scope/keyに一致する人の回答だけ再利用。不足・条件外・矛盾・仮説・例外をテスト。
5. `extensions.pipeline`でWorkflow／Toolの生成・保存・別runテスト・新版登録を実装。生成応答はfixtureで検証。
6. 通常・不正・境界ケース、生成Toolの5秒タイムアウト、依存制限、失敗候補の非公開、旧版保持を確認。
7. 同じ作成Workflowで2種類の判断ループを登録し、次のrunから呼べることと追加検証の実行・失敗時停止を確認。実LLMによる自己ループ生成は未確認。

次は利用者が指定するbase_url/modelで実LLMの3種類の判断と候補生成を実測し、利用先に合わせた独立した検証関数・受入ケースを整えます。
実行核自体の変更は不要でした。以前の計画と確認履歴は以下に残します。

各段階の完了条件を満たしてから次へ進む。GUI・MCP・並列実行は当面追加しない。

| 順番 | 追加するもの | 完了条件 |
|---|---|---|
| 1 | 実LLMを呼ぶ判断関数 | 同じagent_loop.jsonから、Tool選択・質問・完了ができる。不正な出力は実行せずエラーになる |
| 2 | 実際の業務Toolを2個登録 | 別venv間でファイルを受け渡し、検証まで1件完了する |
| 3 | 判断根拠と質問・知識検索 | 根拠不足の事例で質問し、適用条件つきで回答を保存。同条件の次回は再利用し、条件外には適用しない |
| 4 | Workflowを作成・登録する関数 | LLMが候補定義を生成し、構造検証とサンプル実行後、上位Workflowから呼べる |
| 5 | Toolを作成・登録するWorkflow | 別runで候補コードをテストし、新しい版として登録。旧版に戻せる |

## 第1段階の設定を小さく保つ

LLM接続時に増やす設定は`base_url`と`model`。キーは環境変数で渡す。
実行核にはLLM固有の設定を入れない。判断関数側だけで扱う。

## 自分自身を組み立てる到達点

最初のagent_loop.jsonは人間が記述する。
第4段階では、その定義の候補版を現在のハーネスが生成・検証できるようにする。
採用は次のrunから。実行中のrunを途中で書き換える機能は作らない。
実行核のソース変更は通常のコード変更・テストとして扱う。

## GitHub確認（2026-10-28）

今回の再確認: 接続ユーザーmiyokichi。`miyokichi/seed-harness-core`は404で読み書き権限を取得できませんでした。利用可能なGitHub接続にリポジトリ作成APIはなく、ghコマンドも未導入です。
リモート書き込み・pushは未確認です。無関係なリポジトリには変更していません。
展開先には.gitがなかったため、隣接するbundleのmain（19f23af）から履歴を復元し、既存ファイルを維持したまま`implementation/llm-harness`ブランチで段階別にコミットしました。
今回の引渡しbundleは`dist/seed-harness-implemented.bundle`です。

以下は配布物に残っていた以前の確認履歴です。

接続ユーザーmiyokichi、little_agentの権限admin、gitでHEAD取得を確認。
このセッションのGitHub接続には新規リポジトリ作成APIがない。
miyokichi/seed-harnessは404（存在しないか、接続から見えない）。
リモート書き込みは未検証。他のプロジェクトへ確認用コミットは行わない。
この配布物はローカルGitコミットと履歴bundleを用意する。

空のprivateリポジトリseed-harness-coreをGitHubで作成後、Git認証済みPCで以下を実行する。

```sh
git clone seed-harness-core.bundle seed-harness-core
cd seed-harness-core
git remote set-url origin https://github.com/miyokichi/seed-harness-core.git
git push -u origin main
```

bundleは配布ZIPに同梱。clone時にはbundleファイルの実際の場所を指定する。
