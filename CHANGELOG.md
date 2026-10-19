# 変更履歴

本プロジェクトの主な変更点をこのファイルに記録します。

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.1.0/) に準拠し、
バージョン管理は [セマンティック バージョニング](https://semver.org/lang/ja/)
に従います。

## [Unreleased]

## [2.0.0] - 2026-10-19

### 追加

- `/dashboard` — 予定フライト、参加人数、設定状況を1枚のカードに集約。
- `/export` — フライトログをCSV（Excel用BOM付き）またはJSONで書き出し。
- `/search` — 便名・ルート・機材でフライトを検索（予定／過去／全件）。
- `/poll` — ボタン式の投票。票数と割合をリアルタイムで更新し、作成者・マネージャーが締め切れる。
- `/onduty` — 勤務中ロールの付与／解除（`roles.on_duty` を設定で指定）。
- `/news` / `/news_list` — お知らせの予約投稿（時刻指定・一覧・取消）。
- `/help` に新カテゴリ「Dashboard, Data & Polls」を追加。
- `/setup` で **色と絵文字**を設定できるようになった。
  - **Colors** — 6色の埋め込みカラー（メインの濃い青 `#1B3444` ほか）を
    `#RRGGBB` 形式で変更。保存時にサンプルを見ながら確認でき、いつでも既定値へ戻せます。
  - **Emojis** — 16種類の絵文字を変更可能（チェック・ベル・リンク・ブランドなどの
    一般アイコン10種、募集見出しアイコン6種、`flight_approved` の承認ボタン）。
    Unicode 絵文字とカスタム絵文字（`<:name:id>`）の両対応、空欄で既定値に復帰。
  - 色と絵文字は保存した瞬間に Bot へ反映されます（起動時に登録されるボタンの
    絵文字のみ再起動が必要）。

### 保存

- 投票結果と予約投稿は `misc_data.json` のバックアップに追加され、再起動後も保持されます。

### 変更

- 募集メッセージ（社員向け告知）の見出しアイコンに既定の Unicode 絵文字を設定
  （✈️ 🛠️ 🧪 🔁 🔒 🎮 は通常／カスタム／テスト／定期便／プライベート／ゲームナイト）。
  カスタム絵文字を使わない環境でもそのままアイコンが表示されます。
  なお `emojis.signup_type` で `<:name:id>` に差し替え可能です。
- バス便機能を削除し、代わりにカスタム便を種別として扱うようになりました。
  - `/create_bus` / `/create_custom_bus` を廃止（`/create_custom_flight` がカスタム便）。
  - バス乗務ロール（`roles.bus_driver` / `roles.dispatcher`）と配置ロールを削除。
  - バス用テンプレート（`customer_post_bus` など）と `use_bus` 設定を削除。
  - `Bus (...)` の便名表記・`Bus Driver` 評価項目・関連 UI 表示を削除。
  - 保存済みの旧バス便データは通常のフライトとして表示されます。
- バージョン表記を `2.0.0`（`v2`）に更新。

## [1.0.0] - 2026-01-01

Flight Hub の最初のオープンソースリリースです。

### 追加

- サーバー・チャンネル・ロールを 1 つの `config/config.json` に保存する
  初回起動用の `/setup` ウィザード。
- 設定で駆動するブランド、色（既定はエアラインの青）、フッター、カスタム
  絵文字のサポート。
- オープンソース版であることとバージョンを表示する `/about` コマンド。
- セットアップ手順 `docs/SETUP.md` とコマンド一覧 `docs/COMMANDS.md`。

### 変更

- プロジェクト全体を **Flight Hub** に改名。ユーザーに表示されるテキストは
  英語のみに統一。
- Discord のサーバー／チャンネル／ロール ID をハードコードせず、すべて設定から
  読み込むように変更。
- 航空会社名・フッターの既定値を汎用的な値（`Airline` / `Flight Hub`）に変更。
- タイムゾーンを `options.timezone` で設定可能に（既定 `Asia/Tokyo`）。

### 削除

- **Miles** システム（ポイント、ランク、ショップ、取引）。
- **Roblox** 連携: アカウント連携、パスポート、アバター、および
  Google Apps Script バックエンド。便ごとの任意 URL フィールド
  `roblox_link` は維持しています。
- 企業固有のシークレット、サーバー ID、絵文字 ID。

[Unreleased]: https://github.com/your-org/flight-hub/compare/v2.0.0...HEAD
[2.0.0]: https://github.com/your-org/flight-hub/releases/tag/v2.0.0
[1.0.0]: https://github.com/your-org/flight-hub/releases/tag/v1.0.0
