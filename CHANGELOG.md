# 変更履歴

本プロジェクトの主な変更点をこのファイルに記録します。

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.1.0/) に準拠し、
バージョン管理は [セマンティック バージョニング](https://semver.org/lang/ja/)
に従います。

## [Unreleased]

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

[Unreleased]: https://github.com/your-org/flight-hub/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/your-org/flight-hub/releases/tag/v1.0.0
