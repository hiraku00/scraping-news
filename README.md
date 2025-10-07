# ニューススクレイピングとツイート投稿ツール

このリポジトリには、NHK とテレビ東京のニュースサイトから情報をスクレイピングし、その結果を X（旧 Twitter）に投稿するための Python スクリプトが含まれています。スクリプトは、指定された日付のニュース番組情報を取得し、それを X にスレッド形式で投稿します。

## 主な機能

- ニュース番組情報のスクレイピング
- 関連ツイートの取得
- コンテンツのマージと最適化
- X（旧 Twitter）への投稿
- **WBS番組のコンテンツタイプ別ページオープン**（feature/oa/trend_tamago）

## インストール

1. リポジトリをクローンします：

   ```bash
   git clone [リポジトリURL]
   cd scraping-news
   ```

2. 必要なパッケージをインストールします：

   ```bash
   pip install -r requirements.txt
   ```

3. 環境変数を設定します（`.env`ファイルを作成）：
   ```
   # X (Twitter) API 認証情報
   BEARER_TOKEN=your_bearer_token
   API_KEY=your_api_key
   API_SECRET=your_api_secret
   ACCESS_TOKEN=your_access_token
   ACCESS_SECRET=your_access_token_secret
   ```

## 使い方

### メインコマンド

````bash
# 新しいサブコマンド形式（推奨）
python main.py <command> [YYYYMMDD]

# 従来のオプション形式（後方互換）
python main.py --<command> [--date YYYYMMDD]

# 例: 2025年10月3日のデータを処理
python main.py open 20251003
# または
python main.py open --date 20251003
````

### コマンド一覧

| コマンド | 説明 |
|----------|------|
| `all` | 全ステップを実行（スクレイピング→ツイート取得→マージ→分割→URLオープン） |
| `scrape` | スクレイピングのみ実行 |
| `get-tweets` | ツイート取得のみ実行 |
| `merge` | マージのみ実行 |
| `split` | 分割のみ実行 |
| `open` | URLをブラウザで開く（日付は位置引数または`--date`オプションで指定） |
| `tweet` | ツイート投稿のみ実行 |

### WBS番組の処理について

このツールは、テレビ東京の「WBS」番組に対して特別な処理を実装しています：

- **コンテンツタイプ自動検出**: ブロック内のURLからコンテンツタイプ（feature/oa/trend_tamago）を自動検出
- **複数ページ同時オープン**: 検出された複数のコンテンツタイプに対応するページを個別に開く
- **URLパターンマッチング**: URL構造（`/wbs/feature/`、`/wbs/oa/`、`/wbs/trend_tamago/`）に基づいて正確に判定

例：ブロック内にfeatureとoaの両方のURLが含まれる場合、両方のページが自動的に開かれます。

### 出力ファイル

- スクレイピング結果: `output/YYYYMMDD.txt`
- マージ前のバックアップ: `output/YYYYMMDD_before-merge.txt`
- 分割前のバックアップ: `output/YYYYMMDD_before-split.txt`
- ツイート用テキスト: `output/YYYYMMDD_tweet.txt`

### 実行例（サブコマンド形式）

#### 通常の実行（前日のデータを処理）
```bash
# 全ステップ実行
python main.py all

# 個別に実行する場合
python main.py scrape
python main.py get-tweets
python main.py merge
python main.py split
python main.py open

# ツイートを投稿する場合
python main.py tweet
```

#### 特定の日付を処理
```bash
# 2025-10-03 のデータを処理（全ステップ）
python main.py all 20251003

# URLのみを開く場合
python main.py open 20251003

# 特定のステップのみ実行
python main.py scrape 20251003
python main.py tweet 20251003
```

#### オプション形式（後方互換）
```bash
# 従来のオプション形式でも動作します
python main.py all --date 20251003
python main.py open --date 20251003
```

#### デバッグモード
```bash
# デバッグ情報を表示しながら実行
python main.py all 20251003 --debug
```

他番組/VOD/不正 URL のスキップ詳細ログは、DEBUG レベル時のみ表示されます（通常は非表示）。

### オプション

- `YYYYMMDD`: 処理する日付を位置引数で指定（サブコマンド形式）
- `--date YYYYMMDD`: 処理する日付をオプションで指定（後方互換）
- `--debug`: デバッグモードで実行（詳細なログを表示）
- `--help`: ヘルプを表示（全体/各コマンド）

### 実行例

#### 通常の実行（前日のデータを処理）

```bash
# 全ステップ実行（ツイート投稿は除く）
python main.py --all

# 個別に実行する場合
python main.py --scrape
python main.py --get-tweets
python main.py --merge
python main.py --split
python main.py --open

# ツイートを投稿する場合
python main.py --tweet
```

#### 特定の日付を処理

```bash
# 2025年7月25日のデータを処理
python main.py --all --date 20250725

# 特定のステップのみ実行
python main.py --scrape --date 20250725
python main.py --tweet --date 20250725
```

#### デバッグモード

```bash
# デバッグ情報を表示しながら実行
python main.py --all --debug
```

## スクリプトの詳細

### ツイート投稿機能

`python main.py tweet` を使用すると、指定された日付のテキストファイルを読み込み、X（旧 Twitter）に投稿します。

#### 主な機能

- テキストファイルの内容をツイートに変換
- 複数のツイートをスレッド形式で投稿
- レート制限を考慮したリトライ処理（最大 3 回）
- ツイート間の適切な間隔（5 秒）を自動で確保

#### 入力ファイル

- `output/YYYYMMDD.txt` または `output/YYYYMMDD_tweet.txt`
  - 空行でツイートを区切ります
  - 1 つ目のツイートには自動的にヘッダーが追加されます
  - 1 ツイートあたりの文字数制限（280 文字）を超える場合は自動で分割

#### エラーハンドリング

- ファイルが存在しない場合はエラーを表示して終了
- ツイートの投稿に失敗した場合は最大 3 回までリトライ
- レート制限に達した場合は自動的に待機
- エラー発生時は詳細なログを出力

## スクリプトの詳細

### スクレイピング機能

`main.py --scrape` オプションを使用すると、NHK とテレビ東京のウェブサイトから指定された日付のニュース番組情報を収集します。

このスクリプトは、NHK とテレビ東京のウェブサイトから指定された日付のニュース番組情報を収集します。`ini`ディレクトリ内の設定ファイルに基づいて、スクレイピング対象の番組を定義します。

#### 機能

- **設定ファイルの利用**: `ini` ディレクトリ内の設定ファイル (`nhk_config.ini`, `tvtokyo_config.ini`) に基づいてスクレイピング対象の番組を定義します。設定ファイルは `common.utils` の `load_config` 関数と、`common.utils`の`parse_nhk_programs_config`、`parse_tvtokyo_programs_config` 関数を使って読み込まれ、設定エラー時にはログが出力されます。
- **動的なウェブページスクレイピング**: Selenium と Chrome WebDriver を利用して、JavaScript で動的に生成されるウェブページから情報を抽出します。
- **クラス構成**: `NHKScraper` と `TVTokyoScraper` クラスが `common/base_scraper.py` の `BaseScraper` クラスを継承する形で実装されています。
- **マルチプロセス**: 複数の番組情報を並行してスクレイピングすることで、処理時間を短縮します。
- **ログ出力**: 処理の進行状況やエラーを詳細にログに記録します。ログ設定は `common/utils.py` の `setup_logger` 関数によって行われます。
- **詳細な番組情報抽出**: 各番組のエピソードタイトル、URL、放送時間を抽出します。
- **時間順のソート**: スクレイピングした番組情報を時間順にソートして出力します。

- **テレ東抽出の方針**: 対象番組の一覧コンテナー（`div[id^="News_Detail__Videos_"]`）配下のみを走査し、各カード内の `a[href*="/post_"]` を抽出します。抽出した URL は番組名とカテゴリ（例: `/oa` は必須、`/vod` は除外）で検証してから採用します。
- **待機戦略**: 一覧コンテナーの出現後、「コンテナー配下のアイテム件数 > 0」になるまで待機してから抽出を開始します（DOM 初期化のぶれに対する耐性向上）。
- **WebDriver タイムアウト**: `ini/tvtokyo_config.ini` の `webdriver_timeout`（秒）で待機時間を調整できます。

#### 使い方

1.  `ini`ディレクトリに設定ファイルを作成します（例：`nhk_config.ini`, `tvtokyo_config.ini`）。設定ファイルは `common.utils` の `load_config` 関数、および `parse_nhk_programs_config`, `parse_tvtokyo_programs_config` 関数を使って読み込まれます。

    - `nhk_config.ini` の例:

    ```ini
    [program_1]
    name = 国際報道 2025
    url = https://www.web.nhk/tv/an/kokusaihoudou/pl/series-tep-8M689W8RVX
    channel = NHK BS

    [program_2]
    name = キャッチ!世界のトップニュース
    url = https://www.web.nhk/tv/an/catchsekai/pl/series-tep-KQ2GPZPJWM
    channel = NHK総合

    ; 他の番組も同様に定義
    ```

    - `tvtokyo_config.ini` の例:

    ```ini
    [program_1]
    name = モーサテ
    url = https://txbiz.tv-tokyo.co.jp/nms/special
    time = 05:45-07:05

    [program_2]
    name = WBS
    url = https://txbiz.tv-tokyo.co.jp/wbs/feature
    time = 22:00-22:58

    ; 他の番組も同様に定義
    ```

2.  以下のコマンドでスクリプトを実行します。

    ```bash
    python scraping-news.py <取得したい日付(例:20250125)>
    ```

3.  スクレイピング結果は `output` ディレクトリに日付ごとのテキストファイルとして保存されます。

### `get-tweet.py`

このスクリプトは、指定されたキーワードと日付に基づいて、X (旧 Twitter) から関連するツイートを検索し、取得したツイートを指定のフォーマットに整形してファイルに保存します。

#### 機能

##### コード構造
z bi
- **定数定義**: 番組名などの設定を`PROGRAM_NAMES`として定数化し、保守性を向上
- **ユーティリティ関数**:
  - `create_search_queries`: API 用と X 検索窓用のクエリを生成
  - `save_to_file`: ファイル保存処理を共通化
  - `format_program_info`: 番組情報のフォーマット処理
- **エラーハンドリング**: ファイル操作や API 呼び出し時のエラーを適切に処理

##### 検索機能

- **X API v2 の利用**: `tweepy`ライブラリを使用して X API v2 にアクセスし、ツイートを検索
- **ダミーデータの利用**: API レート制限回避用のダミーデータモード（`USE_API`変数で切り替え）
- **検索クエリ表示**:
  - API 用クエリ: X API v2 に送信される検索条件
  - X 検索窓用クエリ: X のウェブサイトで直接使用できる検索文字列（番組名をダブルクォートで囲み、since/until で日時指定）
- **検索期間**: 放送日の前日の 0 時 0 分から 23 時 59 分 59 秒までのツイートを検索
- **認証**: 環境変数から API キーなどの認証情報を読み込み

##### データ処理

- **ツイートデータ解析**: `format_tweet_data`関数で取得したツイートを解析し整形
- **レート制限対応**: `tweepy.errors.TooManyRequests`例外をキャッチし、リトライ処理を実装

#### 使い方

1. `.env`ファイルを作成し、以下の X API キーを設定します。

   ```
   API_KEY=<APIキー>
   API_SECRET=<APIシークレット>
   ACCESS_TOKEN=<アクセストークン>
   ACCESS_SECRET=<アクセスシークレット>
   BEARER_TOKEN=<ベアラートークン>
   ```

2. 以下のコマンドでスクリプトを実行します。

   ```bash
   python get-tweet.py <検索対象日付(例:20250125)>
   ```

3. 検索結果は `output` ディレクトリに `YYYYMMDD_tweet.txt` というファイル名で保存されます。

### `merge-text.py`

このスクリプトは、`scraping-news.py` によって生成されたテキストファイルと `get-tweet.py` によって生成されたテキストファイルを読み込み、時間でソートしてマージします。

#### 機能

- **2 つのテキストファイルのマージ**: `scraping-news.py` の出力 (`YYYYMMDD.txt`) と `get-tweet.py` の出力 (`YYYYMMDD_tweet.txt`) をマージします。
- **時間によるソート**: マージされたテキストを、`common/utils.py`の`sort_blocks_by_time`関数を使って時間順にソートします。
- **リネーム処理**: `YYYYMMDD.txt` は処理前に `YYYYMMDD_before-merge.txt` にリネーム（バックアップ）されます。
- **エラーハンドリング**: ファイルが存在しない場合や、ファイル読み書き中にエラーが発生した場合に、エラーメッセージを表示し、例外を発生させます。

#### 使い方

1.  `scraping-news.py` と `get-tweet.py` を実行して、`output` ディレクトリにそれぞれの出力ファイルを作成します。
2.  以下のコマンドでスクリプトを実行します。

    ```bash
    python merge-text.py <日付(例:20250125)>
    ```

3.  マージされたテキストは `output` ディレクトリの `YYYYMMDD.txt` に上書き保存されます。元のファイルは `YYYYMMDD_before-merge.txt` にリネームされます。

### `split-text.py`

このスクリプトは、`merge-text.py` によって生成されたテキストファイル（または `scraping-news.py` の出力ファイル）を Twitter の文字数制限に合わせて分割します。

#### 機能

- **文字数制限の考慮**: ツイートの文字数制限（280 文字、全角は 2 文字、半角は 1 文字、URL は 11.5 文字としてカウント）を考慮して、テキストを分割します。
- **`count_tweet_length`関数**: URL を考慮した文字数計算を、`common.utils`の`count_tweet_length`関数で行います。
- **番組ごとの分割**: `●` で始まる各番組のブロックを認識し、各ブロックを文字数制限内に収まるように分割します。最初のブロックでは、`common/constants.py`の`get_header_text`関数で生成されるヘッダーの長さも考慮します。
- **ファイルバックアップ**: 分割前のファイルは `YYYYMMDD_before-split.txt` にバックアップされます。
- **分割が不要な場合は何もしない**: 分割が必要ないと判断した場合は、ファイルを変更しません

#### 使い方

1.  `merge-text.py` (または `scraping-news.py`) を実行して、`output` ディレクトリにテキストファイルを作成します。
2.  以下のコマンドでスクリプトを実行します。

    ```bash
    python split-text.py <日付(例:20250125)>
    ```

3.  分割されたテキストは `output` ディレクトリの元のファイル (`YYYYMMDD.txt`) に書き戻されます。 分割前のファイルは `YYYYMMDD_before-split.txt` にバックアップされます。

### `tweet.py`

このスクリプトは、`split-text.py` によって生成されたテキストファイルを読み込み、その内容を X（旧 Twitter）に投稿します。

#### 機能

- **X API v2 の利用**: `tweepy`ライブラリを使用して X API v2 にアクセスし、ツイートを投稿します。
- **OAuth 2.0 および OAuth 1.0a 認証**: API へのアクセスには Bearer Token（OAuth 2.0）を使用し、ツイートの投稿には OAuth 1.0a 認証（API Key、API Secret、Access Token、Access Secret）を使用します。
- **環境変数**: API キーなどの認証情報は環境変数から読み込みます。
- **スレッド形式での投稿**: スクレイピング結果をスレッド形式で投稿します。
- **レート制限処理**: レート制限を考慮し、`tweepy.errors.TooManyRequests` 例外をキャッチしてリトライします。 レート制限の残り回数とリセット時間も表示します。
- **エラーハンドリング**: レート制限以外のエラーも適切に処理します。
- **文字数制限**: ツイートが文字数制限を超えないようにチェックします。`common/utils`の`count_tweet_length`関数で URL を考慮した文字数計算を行います。
- **ヘッダーテキスト**: `common/constants.py`の`get_header_text`関数でヘッダーテキストを生成します。

#### 使い方

1. `.env`ファイルを作成し、以下の X API キーを設定します。

   ```
   API_KEY=<APIキー>
   API_SECRET=<APIシークレット>
   ACCESS_TOKEN=<アクセストークン>
   ACCESS_SECRET=<アクセスシークレット>
   BEARER_TOKEN=<ベアラートークン>
   ```

2. `split-text.py` を実行して、`output` ディレクトリにツイート用のテキストファイルを作成します。
3. 以下のコマンドで実行します（サブコマンド）

   ```bash
   python main.py tweet --date 20250125
   ```

   注意: テスト時は必ず Twitter API をモック化し、実 API を呼ばないようにしてください（レート・規約・誤投稿対策）。

#### 依存ライブラリ

- **`scraping-news.py`**

  - `selenium`
  - `webdriver_manager`
  - `datetime`
  - `os`
  - `sys`
  - `time`
  - `multiprocessing`
  - `configparser`
  - `re`
  - `selenium.common.exceptions`
  - `logging`

- **`get-tweet.py`**

  - `tweepy`
  - `python-dotenv`
  - `datetime`
  - `sys`
  - `pytz`
  - `re`
  - `json`（ダミーデータ利用時）
  - `unicodedata`

- **`merge-text.py`**

  - `sys`
  - `os`
  - `common.utils`

- **`split-text.py`**

  - `sys`
  - `os`
  - `re`
  - `common.constants`
  - `common.utils`

- **`tweet.py`**
  - `tweepy`
  - `time`
  - `sys`
  - `os`
  - `dotenv`
  - `datetime`
  - `common.constants`
  - `common.utils`

## 注意事項

- このツールを使用する前に、各ウェブサイト（NHK、テレビ東京、X）の利用規約を必ず確認してください。
- スクレイピングはサイトに負荷をかける可能性があるため、頻繁なアクセスは避けてください。とくに、Selenium を使用する際は、`time.sleep()`などで適切な間隔を設けることを推奨します。
- X API の利用制限を守り、過度な投稿を避けてください。`tweet.py`ではレート制限に対応していますが、短時間に大量のツイートを投稿するとアカウントが凍結される可能性があります。
- 環境変数（`.env`ファイル）は適切に管理し、公開リポジトリにコミットしないように注意してください。`.gitignore`ファイルに`.env`を追加することを推奨します。
- `chromedriver`は事前にインストールし、パスを通すか、`webdriver_manager`を利用してインストールする必要があります。
- このツールは、予告なく仕様が変更される可能性があります。
- このツールの使用によって生じたいかなる損害に対しても、作者は責任を負いません。自己責任でご利用ください。
