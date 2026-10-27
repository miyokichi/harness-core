# 次の開発計画

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
