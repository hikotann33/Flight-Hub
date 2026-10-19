# Flight Hub へのコントリビュート

Flight Hub に興味を持っていただきありがとうございます！このドキュメントでは、
開発環境の準備、守るべき規約、変更の提出方法を説明します。

本プロジェクトに参加することで、[行動規範](CODE_OF_CONDUCT.md) に同意したものと
みなされます。

## コントリビュートの方法

- [Issue テンプレート](.github/ISSUE_TEMPLATE) を使ってバグ報告・機能要望を送る。
- ドキュメント（`README.md`、`docs/`）を改善する。
- 修正や機能追加を Pull Request で送る。

## 開発環境の準備

1. リポジトリを fork して clone します:

   ```bash
   git clone https://github.com/<your-account>/Flight-Hub.git
   cd Flight-Hub
   ```

2. 仮想環境を作成して有効化します:

   ```bash
   python -m venv venv
   # Windows: venv\Scripts\activate
   # Linux/macOS: source venv/bin/activate
   ```

3. 依存関係をインストールします:

   ```bash
   pip install -r requirements.txt
   ```

4. 環境変数の雛形をコピーし、テスト用の Bot トークンを設定します:

   ```bash
   cp .env.example .env
   ```

5. Bot を起動します:

   ```bash
   python run.py
   ```

   開発には専用の使い捨てサーバーを使用してください。初回起動時は `/setup` で
   設定を行います。

## コーディング規約

- **Python スタイル** — Python 3.11 以上を対象とし、既存のスタイルを保ちます。
  1 行 120 文字まで（`pyproject.toml` を参照）。[ruff](https://docs.astral.sh/ruff/)
  を導入している場合は `ruff check .` を実行してください。
- **英語のみ** — ユーザーに表示される文字列（コマンド、説明、埋め込み、エラー）は
  すべて英語にしてください。
- **シークレットや ID を含めない** — Bot トークン、Webhook、Discord の
  サーバー／チャンネル／ロール ID をコミットしないでください。値はすべて設定
  ファイルから読み込みます。
- **設定で変更できる設計にする** — 新しいブランド、色、絵文字は
  `config/config.example.json` に追加し、`config_store.cfg` 経由で読み込みます。
- **コマンドは必ず文書化する** — スラッシュコマンドを追加・変更したら
  `docs/COMMANDS.md` を更新してください。

## Pull Request を出す前に

CI と同じチェックを実行してください:

```bash
python -m compileall -q flighthub run.py
python -c "import json; json.load(open('config/config.example.json'))"
```

変更が次の条件を満たしていることを確認してください:

- 問題なくコンパイルでき、`import flighthub.core` を壊していないこと。
- 元プロジェクトのブランドや企業固有の情報を持ち込んでいないこと。
- 関連するドキュメントを更新していること。

## コミットメッセージ

短く命令形の件名を付けてください（例: `Add /about command`）。関連する変更は
できるだけ 1 つのコミットにまとめてください。

## Pull Request

Pull Request テンプレートを使用してください。説明には **何を** 変更し
**なぜ** 変更したかを書き、関連する Issue をリンクし、再現・確認手順を添えて
ください。メンテナーが確認次第レビューします。

## ライセンス

コントリビュートすることで、あなたの貢献が
[MIT ライセンス](LICENSE) の下でライセンスされることに同意したものとみなされます。
