# トレカ抽選情報 自動収集ボット

ポケカ・ワンピカード・ドラゴンボール フュージョンワールドの抽選情報を自動で集め、
**X投稿 → WordPressまとめページ更新** までを無人で回します。実行環境は GitHub Actions（サーバー不要）。

```
30分ごと（7:00〜25:00）
 ① 収集   X（店舗の告知ポスト）・公式サイト・Googleニュースを見て、AI(Claude)で抽選情報を抽出
 ② 承認   自動承認（テスト用）/ GitHub Issueで手動承認 を切替可
 ③ X投稿  新着を締切が近い順に告知（店舗のポストを引用）＋締切24時間前にリマインド
          ＋1日1回、WPまとめページへのリンク付きまとめ投稿
 ④ WP更新 ゲーム別まとめページ＋弾ごとの記事（「〇〇 抽選・予約情報まとめ」）を自動作成・更新
          中身が変わった時だけ更新。Amazon検索アフィリンクも自動で差し込み
```

---

## セットアップ（初回 約30分）

### 1. GitHubにリポジトリを作る
1. github.com でアカウント作成 → 右上「＋」→ **New repository** → 名前は自由、**Private** を選択
2. 「uploading an existing file」から、このフォルダの中身を**全部**ドラッグ＆ドロップ
   - Macで `.github` フォルダが見えない場合は、Finderで `⌘ + Shift + .` を押すと表示されます

### 2. Claude APIキーを取る（AI抽出用）
- console.anthropic.com でキーを発行し、少額チャージしておく
- ページに変化があった時だけAIを呼ぶので、費用はかなり小さく抑えられます

### 3. テスト用XアカウントのAPIキーを取る
1. **テスト用アカウントでログインした状態で** developer.x.com を開き、Appを作成
2. App設定の User authentication で権限を **Read and Write** にする
3. **API Key / API Secret / Access Token / Access Token Secret / Bearer Token** の5つを発行
4. Developer Console でクレジットを少額チャージ（従量課金）
   - 権限を変えた後に Access Token を再発行しないと投稿できません
5. X本体の設定で「自動化されたアカウント」ラベルを付けておくと、凍結リスクが下がります
- 料金の目安（2026年7月時点の従量課金。最新は Developer Console で確認）

| 操作 | 単価 | このボットの使い方 |
|---|---|---|
| ポストの読み取り | 約$0.005/件 | 前回以降の新着だけ取得＋1日200件で打ち止め → 最大 約$1/日 |
| 投稿（リンクなし） | 約$0.015/件 | 個別の抽選告知はリンクなし＋店舗ポストを引用 |
| 投稿（リンクあり） | 約$0.20/件 | WPへのリンクは1日1回のまとめ投稿だけに集約 |

### 4. キーをGitHubに登録
リポジトリの **Settings → Secrets and variables → Actions**

| 種類 | 名前 | 中身 |
|---|---|---|
| Secret | `ANTHROPIC_API_KEY` | ClaudeのAPIキー |
| Secret | `X_API_KEY` / `X_API_SECRET` | XのAPI Key / Secret |
| Secret | `X_ACCESS_TOKEN` / `X_ACCESS_SECRET` | XのAccess Token / Secret |
| Secret | `X_BEARER_TOKEN` | XのBearer Token（検索用） |
| Variable | `AUTO_APPROVE` | `true`（完全自動） |
| Variable | `DRY_RUN` | 最初は `true`（投稿せずログだけ） |

### 5. 動作確認 → 本番
1. **Actions** タブ → `card-lottery-bot` → **Run workflow**
2. ログに「新規: …」「DRY_RUN 投稿: …」が出れば成功。投稿予定の文面がそのまま見られます
3. 中身が正しければ Variable の `DRY_RUN` を `false` に → 以後30分ごとに自動投稿

---

## 自作サイト「トレカ抽選ナビ」を公開する（メイン）
ボットが実行のたびに `site/` にサイト一式を書き出し、**中身が変わった時だけ** Cloudflare Pages（無料）に公開します。

作られるページ
- トップ / ゲーム別（`/pokeka/` `/onepiece/` `/fusionworld/`）
- 弾ごと（`/pokeka/s-xxxxxxxx/`）… 「〇〇 抽選」で検索されるページ
- 都道府県ごとの店頭抽選（`/pokeka/area/osaka/`）… 「ポケカ 抽選 大阪」で検索されるページ
- `sitemap.xml` / `robots.txt`

設定手順
1. cloudflare.com で無料アカウントを作る
2. 「Workers & Pages」→ 作成 →「Pages」→「直接アップロード」でプロジェクトを作る（名前は例 `toreca-chusen`）
3. 「マイプロフィール → APIトークン」で「Cloudflare Pages の編集」権限のトークンを作る
4. GitHubに登録
   - Secret：`CLOUDFLARE_API_TOKEN`、`CLOUDFLARE_ACCOUNT_ID`（ダッシュボード右側に表示）
   - Variable：`CF_PROJECT`（2で付けた名前）、`SITE_URL`（例 `https://toreca-chusen.pages.dev`）、`AMAZON_TAG`（アソシエイトのタグ）
5. 独自ドメインを使う場合は、Pagesの「カスタムドメイン」で設定し、`SITE_URL` をそのドメインに変更
6. Google Search Console にサイトを登録し、`/sitemap.xml` を送信

商品画像は `config/images.yaml` に「弾名: 画像URL」で追加します（Amazonアソシエイトの画像リンク推奨）。

## 新着の抽選を Discord に届ける（手でXに投稿する用・無料）
新しい抽選がサイトに載ると、Xにそのまま貼れる投稿文が Discord に届きます（30分ごとの実行のたび・サイト公開のあと）。
Xの有料の仕組み（API）は使わないので、費用はかかりません。
1. Discord で自分だけのサーバーを作る（スマホアプリの左の「＋」→「オリジナルの作成」）
2. 通知を受けたいチャンネルの ⚙ →「連携サービス」→「ウェブフック」→「新しいウェブフック」→「ウェブフックURLをコピー」
3. GitHub の **Settings → Secrets and variables → Actions** に Secret `DISCORD_WEBHOOK_URL` として貼る
4. 次の実行で「新着お知らせを始めました」と届けば完了（その時点で載っている抽選は送らず、以後の新着だけ届きます）
- 投稿文は1通に10店まで。1回の実行で1ゲーム3通まで（残りは次の回）
- 同じ店・同じ商品は7日間は二度送りません

## アクセス数を見る（Googleアナリティクス）
1. analytics.google.com で「測定を開始」→ アカウント名・プロパティ名（例 トレカ抽選ナビ）を入れる
2. 「データストリーム」で「ウェブ」を選び、URLに `https://tcg-chusen.com` を入れて作成
3. 表示される **測定ID**（`G-` で始まる）をコピー
4. GitHub の **Settings → Secrets and variables → Actions → Variables** に `GA_ID` として登録
→ 次の公開からすべてのページにタグが入り、フッターに注意書きが出ます（下書きページ x-draft は数えません）
- 応募ページ（お店のサイト）へのクリックは、GA4の「拡張計測機能」で自動で「click」イベントとして数えられます

## WordPressをつなぐ（任意）（Xのテストで精度を確認してから）
1. レンタルサーバー（エックスサーバー、ConoHa WINGなど）でWordPressを開設
2. WP管理画面 → ユーザー → プロフィール → **アプリケーションパスワード** を発行
3. Secretに追加：`WP_URL`（例 `https://example.com`）、`WP_USER`、`WP_APP_PASSWORD`
4. Amazonアソシエイトに登録したら、トラッキングタグ（xxxx-22）を `settings.yaml` の `amazon_tag` に入れる
   （もしもアフィリエイト等の固定リンクは `affiliate:` に貼る）
5. 投稿カテゴリー「ポケカ抽選」「ワンピカード抽選」「フュージョンワールド抽選」を作り、IDを `wp_categories` に入れる（任意）
→ 次回実行時から自動で以下が作られ、以後ずっと自動更新されます
   - ゲーム別まとめページ（固定ページ）×3
   - 弾ごとの記事（投稿）… 新しい弾の抽選が見つかるたびに1記事増える。タイトルの「◯件受付中」も自動更新
   - X投稿のリンク先は、その弾の記事に自動で切り替わります

## 承認制に切り替える（本番アカウントに移る時）
- Variable `AUTO_APPROVE` を `false` に
- 新着ごとに Issue が立つので、スマホのGitHubアプリで **`approved` ラベルを付ける＝投稿** / **そのままClose＝却下**
- 完全自動モードでも、AIの自信度が低いものや締切が不明なものは自動でこの承認待ちに回ります

## Xの監視先を増やす（いちばん効く）
`config/sources.yaml` の `x_store_accounts` に、普段チェックしている店舗・カードショップのXアカウントIDを並べて `enabled: true` にします。
キーワード検索より誤検知が少なく、読み取り費用も安くなります（その店の「抽選」ポストしか返ってこないため）。

## Webの監視先を増やす
`config/sources.yaml` に店舗の抽選ページを追記します（ヨドバシ、ビック、セブンネット、ポケセンオンラインなど）。
追加したら一度 `DRY_RUN=true` で動かし、正しく拾えるか確認してください。

## 設定ファイル
- `config/settings.yaml` … 投稿上限、X読み取り上限、リンクの有無、ハッシュタグ、アフィリンク
- `state/lotteries.json` … 集めた抽選の一覧（自動更新。中身を見れば何を拾ったか分かる）

## 注意
- 店舗によっては規約で自動取得を禁止しています。追加する前に規約を確認し、アクセス頻度は今の設定（30分おき・1ページ1回）から上げないでください
- Xのデータは公式APIでのみ取得しています（Xのスクレイピングは規約違反で凍結対象なので行いません）
- 公式のカード画像は使わず、テキストとリンクで運用してください
- 動作テスト：`python tests/test_pipeline.py`（ネット接続なしで流れを確認）
