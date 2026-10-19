# セットアップガイド

このガイドでは、クローン直後の状態から Bot を起動するまでを説明します。

## 1. Discord アプリケーションを作成する

1. [Discord Developer Portal](https://discord.com/developers/applications) を開き、
   **New Application** を作成します。
2. **Bot** → **Add Bot** を開きます。
3. **Bot トークン** をコピーします（`.env` に記入します）。
4. **Privileged Gateway Intents** で次を有効にします:
   - `SERVER MEMBERS INTENT`
   - `MESSAGE CONTENT INTENT`
   - `PRESENCE INTENT`（任意ですが推奨）
5. **OAuth2 → URL Generator** でスコープ `bot` と `applications.commands` を選び、
   必要な権限（チャンネル管理、ロール管理、イベント管理、メッセージ送信、
   埋め込みリンク、ファイル添付、メッセージ履歴の閲覧、メッセージ管理、
   ボイスの接続／発話）を付与します。Bot は **スタッフサーバー** と
   **顧客サーバー** の両方に招待してください。

## 2. インストール

```bash
git clone <your-fork-url> Flight-Hub
cd Flight-Hub
python -m venv venv
# Windows: venv\Scripts\activate
# Linux/macOS: source venv/bin/activate
pip install -r requirements.txt
```

## 3. トークンを設定する

`.env.example` を `.env` にコピーしてトークンを設定します:

```
DISCORD_BOT_TOKEN=your-token-here
```

トークンが空の場合、Bot は起動しません。

## 4. 初回起動と `/setup`

```bash
python run.py
```

初回起動時は設定がまだないため、Bot は最小構成で動作します。
**スタッフサーバー** で次を実行してください:

```
/setup
```

ウィザードは Modmail 風のパネルで、次の操作ができます:

| 操作 | 説明 |
| --- | --- |
| **スタッフサーバーとして設定** | そのサーバーをスタッフサーバーとして保存します。 |
| **顧客サーバー** | 顧客サーバーとして使うサーバーを選択します。 |
| **チャンネルを自動検出** | 下記の名前でチャンネルを探して保存します。 |
| **ロールを自動検出** | 下記の名前でロールを探して保存します。 |
| **設定を表示** | 現在の設定内容を表示します。 |
| **Colors** 🎨 | 埋め込みの色を変更します（メインの濃い青 `#1B3444` ほか計6色）。 |
| **Emojis** 🎭 | 使う絵文字を変更します（既定は Unicode 絵文字、カスタム絵文字も可）。 |
| **Save & finish** | 設定を保存して完了にします。 |
| **リセット** | 設定内容はそのままに「完了」状態を解除します。 |

保存後は必ず Bot を再起動してください。多くの設定は再起動で反映されます。

### 色と絵文字の変更

**Colors** を押すと6色（`primary` = メインの濃い青、`private`, `success`,
`warning`, `danger`, `info`）を `#RRGGBB` 形式で編集できます（メイン2色と
ステータス4色の2画面に分かれています）。保存するとサンプル付きで反映結果が
表示され、**Reset colors** でいつでも既定値に戻せます。

**Emojis** を押すと、次の16種類を1つずつ編集できます。
入力できるのは **Unicode 絵文字**（例: ✅）と**カスタム絵文字**
（例: `<:name:123456789012345678>`）で、**空欄で送信すると既定値に戻ります**。

- 一般: `check` `x` `noti` `info` `search` `baggage` `tail` `link` `brand`
  `flight_approved`（承認ボタン用。カスタム絵文字のみ対応）
- 募集メッセージの見出しアイコン: `flight` `custom` `test` `recurring`
  `private` `gamenight`（`emojis.signup_type`）

色と絵文字は保存した瞬間に反映されます。ただし起動時に登録される絵文字
（`/flight_app` の承認ボタンなど）は再起動後に反映されます。

## 5. 自動検出が探す名前

自動検出を使う前に、下記の名前でチャンネルとロールを作成してください
（大文字小文字まで完全一致）。`config/config.json` を直接編集して ID を
指定することもできます。

### スタッフサーバーのチャンネル

| 設定キー | チャンネル名 | 種別 |
| --- | --- | --- |
| `channels.staff_announce` | `staff-announcements` | テキスト |
| `channels.flight_input` | `flight-input` | テキスト |
| `channels.flight_log` | `flight-log` | テキスト |
| `channels.flight_log_history` | `flight-log-history` | テキスト |
| `channels.manual_log` | `manual-log` | テキスト |
| `channels.briefing` | `briefing` | テキスト |
| `channels.remind_track` | `remind-track` | テキスト |
| `channels.command` | `commands` | テキスト |
| `channels.reflection` | `reflection` | テキスト |
| `channels.flight_app` | `flight-applications` | テキスト |
| `channels.eval_track` | `evaluations` | テキスト |
| `channels.audit_log` | `audit-log` | テキスト |
| `channels.loa_track` | `loa` | テキスト |
| `channels.misc_data` | `bot-data` | テキスト |
| `channels.test_json` | `bot-test-data` | テキスト |
| `channels.test_staff` | `test-flight` | テキスト |
| `channels.flight_channel_category` | `Flights` | カテゴリ |
| `channels.test_briefing_category` | `Test Briefings` | カテゴリ |

### 顧客サーバーのチャンネル

| 設定キー | チャンネル名 | 種別 |
| --- | --- | --- |
| `channels.customer_announce` | `announcements` | テキスト |
| `channels.test_customer_category` | `Test Flights` | カテゴリ |

### スタッフサーバーのロール

`Event Managers`, `Ground Ops`, `Cabin Crews`, `Flight Ops`,
`Chief`, `Flight Verifier`, `LOA`, `Staff`, `Notifications`,
`Join Notifications`, `DM Target`, `DM Staff`, `DM Exclude`,
`Exclude Reminders`。

## 6. 手動での設定

ウィザードで扱えないキーは `config/config.json` を直接編集してください。
`config/config.example.json` にサポートされる全キーがあります。省略した値は
コード側の既定値にフォールバックし、`null` は「未設定」を意味し、それに依存
する機能は無効になります。

セクション:

- `guilds` — `staff`, `customer`, `log`
- `channels` — すべてのチャンネル／カテゴリ ID
- `roles` — すべてのロール ID（イベントマネージャー、チーフ、警告ロール、
  部門ロール、認定、Bot ロールなど）。`on_duty` のみ自動検出の対象外で、
  `/onduty` を使う場合はロール ID を直接設定してください。
- `colors` — 埋め込みの色（`primary`, `private`, `success`, `warning`,
  `danger`, `info`）。**`/setup` の Colors からも変更できます。**
- `emojis` — カスタム絵文字の文字列（例: `<:name:id>`）と
  `flight_approved`（カスタム絵文字 ID）。
  **`/setup` の Emojis からも変更できます**（16種類を個別に設定可能）。
  `emojis.signup_type` は募集メッセージ（社員向け告知）の見出しアイコンで、
  **既定は Unicode 絵文字**（✈️ 🛠️ 🧪 🔁 🔒 🎮）。カスタム絵文字が使える環境なら
  `<:name:id>` に差し替えるだけで反映されます。
- `brand` — `name`, `footer`, `airline`
- `options` — `timezone`（`Asia/Tokyo` などの IANA 名。スケジュールに使用）
- `setup` — `completed`, `version`（`/setup` が管理）

環境変数 `FLIGHTHUB_CONFIG` で別の設定ファイルを指定することもできます。

## 7. トラブルシューティング

- **スラッシュコマンドが表示されない**: 起動後しばらく待つ（グローバル同期）
  か、`applications.commands` スコープを付けて Bot を再招待してください。
- **`DISCORD_BOT_TOKEN` エラー**: `.env` が `run.py` と同じ場所にあるか確認します。
- **自動検出が何も見つけない**: チャンネル名／ロール名が完全一致しているか、
  Bot に `Manage Server` / `Manage Roles` / `View Channels` 権限があるか確認します。
- **絵文字がテキストで表示される**: `emojis` セクションに独自のカスタム絵文字を
  設定するか、空のままにして内蔵の Unicode 絵文字を使います。
- **ボイス再生に失敗する**: `ffmpeg` と `libopus` をインストールしてください。
