# Flight Hub

[![CI](https://github.com/hikotann33/Flight-Hub/actions/workflows/ci.yml/badge.svg)](https://github.com/hikotann33/Flight-Hub/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)

**v2** · オープンソース · [MIT ライセンス](LICENSE)

**🌐 公開サイト（英語）**: https://hikotann33.github.io/Flight-Hub/
（このリポジトリの `docs/index.html` を GitHub Pages で公開しています）

`discord.py` で作られた、Discord 向けのオープンソースなフライト運用ボットです。
どなたでも自分の Discord サーバーで運用できるようにクリーンアップしたリリースです。

> これは **オープンソース版（v2）** です。企業固有のシークレット、サーバー ID、
> Miles／Roblox のアカウント連携システムは削除されています。それ以外の機能
> （フライトイベント作成、ブリーフィング、フライトログ、アンケート、スタッフ評価、
> 休暇（LOA）管理、統計・ランキングなど）はそのまま利用できます。

## 主な特徴

- **初回の `/setup`** — サーバー・チャンネル・ロールの設定を 1 つの
  `config/config.json` に保存するガイド付きウィザード。
- **ID やシークレットのハードコードなし** — Bot トークンは `.env` から読み込み、
  Discord の ID はすべて設定ファイルから取得します。
- **Modmail 風の UI** — 埋め込み／カードのテーマ（色・フッター・ボタン）は
  `flighthub/ui_theme.py` にまとめられ、設定で駆動します。
- **Discord だけで完結するストレージ** — データは専用チャンネルに JSON
  添付として保存されるため、外部データベースなしで再起動後も状態を維持します。
- **英語** — ユーザー向けのテキストはすべて英語です。

## 削除された機能

- **Miles** システム（ポイント、ティア、ショップ、取引）。
- **Roblox** 連携: アカウント連携、パスポート、アバター、および接続していた
  Google Apps Script（GAS）バックエンド。
- ハードコードされていたサーバー／チャンネル／ロール ID、GAS の URL、
  手動連携用シークレット。

## 動作要件

- Python 3.11 以上（3.13／3.14 で動作確認済み）
- Discord アプリケーションと Bot トークン
- 必要なライブラリは `requirements.txt` を参照

音声再生には追加で `ffmpeg` と `libopus` が必要です。

## クイックスタート

```bash
git clone https://github.com/hikotann33/Flight-Hub.git Flight-Hub
cd Flight-Hub
python -m venv venv
# Windows: venv\Scripts\activate
# Linux/macOS: source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # .env に Bot トークンを記入
python run.py
```

起動後、Discord の **スタッフサーバー** で次を実行します:

```
/setup
```

スタッフサーバーと顧客サーバーを選び、チャンネルとロールを自動検出し、
**Save & finish** を押してから Bot を再起動してください。詳しい手順は
`docs/SETUP.md` を参照してください。

## プロジェクト構成

```
Flight-Hub/
├── run.py                     # エントリポイント（python run.py）
├── requirements.txt
├── pyproject.toml             # プロジェクト情報・ツール設定
├── README.md
├── LICENSE
├── CHANGELOG.md
├── CONTRIBUTING.md
├── CODE_OF_CONDUCT.md
├── SECURITY.md
├── .env.example               # DISCORD_BOT_TOKEN
├── .github/                   # CI ワークフロー・Issue/PR テンプレート
├── config/
│   └── config.example.json    # /setup がコピーする config/config.json の雛形
├── docs/
│   ├── index.html               # 公開サイト（英語ランディングページ）
│   ├── style.css                # サイトのスタイルシート
│   ├── favicon.svg              # サイトのアイコン
│   ├── .nojekyll                # GitHub Pages で Jekyll を無効化
│   ├── SETUP.md                 # セットアップ手順
│   └── COMMANDS.md              # コマンド一覧
└── flighthub/                 # Bot 本体のパッケージ
    ├── core.py                # データ層・埋め込み・共通ヘルパー・クライアント
    ├── config_store.py        # 設定の読み書き（ドット区切りでアクセス）
    ├── config_core.py         # 設定から読み込むロールグループ
    ├── ui_theme.py            # 共通の Modmail 風テーマ
    ├── setup_wizard.py        # /setup コマンド
    ├── admin_tools.py         # /aps などの管理ユーティリティ
    ├── flight_apps.py         # フライト申請フロー
    ├── log_survey.py          # イベント・on_ready・コマンド同期・アンケート
    ├── ops_features.py        # スタッフプロフィール・評価・LOA・統計
    ├── test_flight.py         # テストサーバー向けフライト作成
    ├── ui_flights.py          # 対話的なフライト UI
    ├── briefing.py              # ブリーフィングシート
    ├── eval_sheet.py            # 評価シート
    ├── templates.py             # フライトテンプレートの保存と一覧
    ├── v2_features.py           # /dashboard /export /search /poll などの v2 機能
    └── selftest.py              # 内蔵の動作診断
```

## 設定

設定は `config/config.json` に保存されます（`/setup` が作成。リポジトリには
コミットしません）。`config/config.example.json` に全キーの説明があります。
Bot は小さなドット区切りのヘルパー経由で値を読み込みます:

```python
from .config_store import cfg
STAFF_GUILD_ID = cfg("guilds.staff")
EMBED_COLOR   = cfg("colors.primary", 0x1B3444)
```

セクション: `brand`, `colors`, `guilds`, `channels`, `roles`, `emojis`, `options`。
省略した項目はコード側の既定値にフォールバックします。

## 補足

- `/setup` は設定を即時に保存しますが、多くの設定は次回の再起動で反映されます。
- サンプル設定の絵文字は空です。独自のカスタム絵文字
  （例: `"<:name:1234567890>"`）を設定するか、空のままにすると内蔵の
  Unicode 絵文字が使われます。

## 公開サイト（GitHub Pages）

英語のランディングページ（特徴・クイックスタート・コマンド一覧・
色と絵文字の設定）を `docs/` に同梱しています。公開手順:

1. GitHub のリポジトリで **Settings → Pages** を開く
2. **Source** で "Deploy from a branch" を選ぶ
3. Branch: `main` / Folder: `/docs` を指定して Save

数分後に `https://hikotann33.github.io/Flight-Hub/` で公開されます。

> `docs/.nojekyll` があるので Jekyll の変換は行われず、HTML がそのまま配信されます。

## コントリビュート

コントリビュートを歓迎します！開発環境の準備とガイドラインは
[CONTRIBUTING.md](CONTRIBUTING.md) を参照してください。本プロジェクトは
[行動規範](CODE_OF_CONDUCT.md) に従います。

## セキュリティ

脆弱性を報告する場合は、公開 Issue ではなく [SECURITY.md](SECURITY.md) の
手順に従ってください。

## 変更履歴

リリース履歴は [CHANGELOG.md](CHANGELOG.md) を参照してください。

## ライセンス

MIT — [LICENSE](LICENSE) を参照してください。
