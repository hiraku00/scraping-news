# ニューススクレイピングとツイート投稿ツール

このリポジトリには、NHKとテレビ東京のニュースサイトから情報をスクレイピングし、その結果をX（旧Twitter）に投稿するためのPythonスクリプトが含まれています。スクリプトは、指定された日付のニュース番組情報を取得し、それをXにスレッド形式で投稿します。

## 概要

このツールは以下の5つの主要なスクリプトで構成されています。

1.  **`scraping-news.py`**: NHKとテレビ東京のウェブサイトからニュース番組情報をスクレイピングします。
2.  **`get-tweet.py`**: X (旧Twitter) から関連するツイートを検索します。
3.  **`merge-text.py`**: スクレイピング結果とツイート検索結果をマージします。
4.  **`split-text.py`**: マージされたテキストをツイート用に分割します。
5.  **`tweet.py`**: 分割されたテキストを基に、Xにツイートを投稿します。

これらのスクリプトは `common` ディレクトリ内の共通モジュール (`base_scraper.py`, `utils.py`) を利用します。

## スクリプトの詳細

### `scraping-news.py`

このスクリプトは、NHKとテレビ東京のウェブサイトから指定された日付のニュース番組情報を収集します。`ini`ディレクトリ内の設定ファイルに基づいて、スクレイピング対象の番組を定義します。

#### 機能

*   **設定ファイルの利用**: `ini` ディレクトリ内の設定ファイル (`nhk_config.ini`, `tvtokyo_config.ini`) に基づいてスクレイピング対象の番組を定義します。設定ファイルは `common/utils.py` の `load_config` 関数と、`parse_nhk_programs_config`、`parse_tvtokyo_programs_config` 関数を使って読み込まれ、設定エラー時にはログが出力されます。
*   **動的なウェブページスクレイピング**: SeleniumとChrome WebDriverを利用して、JavaScriptで動的に生成されるウェブページから情報を抽出します。
*   **クラス構成**: `NHKScraper` と `TVTokyoScraper` クラスが `common/base_scraper.py` の `BaseScraper` クラスを継承する形で実装されています。
*   **マルチプロセス**: 複数の番組情報を並行してスクレイピングすることで、処理時間を短縮します。
*   **ログ出力**: 処理の進行状況やエラーを詳細にログに記録します。ログ設定は `common/utils.py` の `setup_logger` 関数によって行われます。
*   **詳細な番組情報抽出**: 各番組のエピソードタイトル、URL、放送時間を抽出します。
*   **時間順のソート**: スクレイピングした番組情報を時間順にソートして出力します。

#### 依存ライブラリ

*   `selenium`: ウェブブラウザの自動操作に利用します。
*   `webdriver_manager`: ChromeDriverの管理に利用します。
*   `datetime`: 日付と時間の操作に利用します。
*   `os`: OS関連の操作に利用します。
*   `sys`: システム関連の操作に利用します。
*   `time`: 時間関連の操作に利用します。
*   `multiprocessing`: 並列処理に利用します。
*   `configparser`: 設定ファイルの解析に利用します。
*   `re`: 正規表現操作に利用します。
*   `selenium.common.exceptions`: Selenium関連の例外処理に利用します。
*   `logging`: ログ出力に利用します。

#### 使い方

1.  `ini`ディレクトリに設定ファイルを作成します（例：`nhk_config.ini`, `tvtokyo_config.ini`）。設定ファイルは `common/utils.py` の `load_config` 関数、および `parse_nhk_programs_config`, `parse_tvtokyo_programs_config` 関数を使って読み込まれます。

    *   `nhk_config.ini` の例:

    ```ini
    [program_1]
    name = 国際報道 2025
    url = https://www.nhk.jp/p/kokusaihoudou/ts/8M689W8RVX/list/
    channel = NHK BS

    [program_2]
    name = キャッチ!世界のトップニュース
    url = https://www.nhk.jp/p/catchsekai/ts/KQ2GPZPJWM/list/
    channel = NHK総合

    ; 他の番組も同様に定義
    ```

    *   `tvtokyo_config.ini` の例:

    ```ini
    [program_1]
    name = モーサテ
    url = https://txbiz.tv-tokyo.co.jp/nms/special
    time = 05:45~07:05

    [program_2]
    name = WBS
    url = https://txbiz.tv-tokyo.co.jp/wbs/feature
    time = 22:00~22:58

    ; 他の番組も同様に定義
    ```

2.  以下のコマンドでスクリプトを実行します。

    ```bash
    python scraping-news.py <取得したい日付(例:20250125)>
    ```

3.  スクレイピング結果は `output` ディレクトリに日付ごとのテキストファイルとして保存されます。

### `get-tweet.py`

このスクリプトは、指定されたキーワードと日付に基づいて、X (旧Twitter) から関連するツイートを検索し、取得したツイートを指定のフォーマットに整形してファイルに保存します。

#### 機能

- **X API v2 の利用**: `tweepy` ライブラリを使用して X API v2 にアクセスし、ツイートを検索します。
- **ダミーデータの利用**: API レート制限を回避するため、API を使用しない場合はダミーデータを使用できます。`USE_API` 変数で切り替え可能です。
- **環境変数**: API キーなどの認証情報は環境変数から読み込みます。
- **レート制限対応**:  `tweepy.errors.TooManyRequests` 例外をキャッチし、リトライ処理を行います。
- **検索期間**:  放送日の前日の0時0分から23時59分59秒までのツイートを検索します。
- **`search_tweets` 関数**:  X API v2 を使用してツイートを検索します。キーワード、ユーザー、検索件数を指定できます。
- **`format_tweet_data` 関数**:  取得したツイートデータを解析し、指定されたフォーマットに整形します。
- **エラーハンドリング**:  API 呼び出し時のエラーや例外を適切に処理します。

#### 依存ライブラリ

-   `tweepy`: X API クライアントとして利用します。
-   `python-dotenv`: 環境変数の読み込みに利用します。
-   `datetime`: 日付と時間の操作に利用します。
-   `sys`: システム関連の操作に利用します。
-   `pytz`: タイムゾーンの変換に利用します。
-   `re`: 正規表現操作に利用します。
-   `json`: JSON データのパースに利用します (ダミーデータ使用時)。
-   `unicodedata`: 全角文字の判定に利用します。

#### 使い方

1.  `.env` ファイルを作成し、以下の X API キーを設定します。

    ```
    API_KEY=<APIキー>
    API_SECRET=<APIシークレット>
    ACCESS_TOKEN=<アクセストークン>
    ACCESS_SECRET=<アクセスシークレット>
    BEARER_TOKEN=<ベアラートークン>
    ```

2.  以下のコマンドでスクリプトを実行します。

    ```bash
    python get-tweet.py <検索対象日付(例:20250125)>
    ```

3.  検索結果は `output` ディレクトリに `YYYYMMDD_tweet.txt` というファイル名で保存されます。

### `merge-text.py`

このスクリプトは、`scraping-news.py` によって生成されたテキストファイルと `get-tweet.py` によって生成されたテキストファイルを読み込み、時間でソートしてマージします。

#### 機能

- **2つのテキストファイルのマージ**: `scraping-news.py` の出力 (`YYYYMMDD.txt`) と `get-tweet.py` の出力 (`YYYYMMDD_tweet.txt`) をマージします。
- **時間によるソート**: マージされたテキストを、`common/utils.py`の`sort_blocks_by_time`関数を使って時間順にソートします。
- **リネーム処理**:  `YYYYMMDD.txt` は処理前に `YYYYMMDD_before-merge.txt` にリネーム（バックアップ）されます。
- **エラーハンドリング**: ファイルが存在しない場合や、ファイル読み書き中にエラーが発生した場合に、エラーメッセージを表示し、例外を発生させます。

#### 使い方

1.  `scraping-news.py` と `get-tweet.py` を実行して、`output` ディレクトリにそれぞれの出力ファイルを作成します。
2.  以下のコマンドでスクリプトを実行します。

    ```bash
    python merge-text.py <日付(例:20250125)>
    ```

3.  マージされたテキストは `output` ディレクトリの `YYYYMMDD.txt` に上書き保存されます。元のファイルは `YYYYMMDD_before-merge.txt` にリネームされます。

### `split-text.py`

このスクリプトは、`merge-text.py` によって生成されたテキストファイル（または `scraping-news.py` の出力ファイル）をツイート用に分割します。

#### 機能

*   **文字数制限の考慮**: ツイートの文字数制限（280文字、全角は2文字、半角は1文字、URLは11.5文字としてカウント）を考慮して、テキストを分割します。
*   **`count_tweet_length` 関数**: URL を考慮した文字数計算を行います。
*   **番組ごとの分割**:  `●` で始まる各番組のブロックを認識し、各ブロックを文字数制限内に収まるように分割します。
*   **ファイルバックアップ**: 分割前のファイルは `YYYYMMDD_before-split.txt` にバックアップされます。
* 　**分割が不要な場合は何もしない**: 分割が必要ないと判断した場合は、ファイルを変更しません

#### 使い方

1.  `merge-text.py` (または `scraping-news.py`) を実行して、`output` ディレクトリにテキストファイルを作成します。
2.  以下のコマンドでスクリプトを実行します。

    ```bash
    python split-text.py <日付(例:20250125)>
    ```
3.  分割されたテキストは `output` ディレクトリの元のファイル (`YYYYMMDD.txt`) に書き戻されます。 分割前のファイルは `YYYYMMDD_before-split.txt` にバックアップされます。

### `tweet.py`

このスクリプトは、`split-text.py` によって生成されたテキストファイルを読み込み、その内容をX（旧Twitter）に投稿します。

#### 機能

-   **X API v2 の利用**: `tweepy` ライブラリを使用して X API v2 にアクセスし、ツイートを投稿します。
-   **OAuth 2.0 および OAuth 1.0a 認証**: API へのアクセスには Bearer Token (OAuth 2.0) を使用し、ツイートの投稿には OAuth 1.0a 認証 (API Key, API Secret, Access Token, Access Secret) を使用します。
-   **環境変数**: API キーなどの認証情報は環境変数から読み込みます。
-   **スレッド形式での投稿**: スクレイピング結果をスレッド形式で投稿します。
-   **レート制限処理**: レート制限を考慮し、`tweepy.errors.TooManyRequests` 例外をキャッチしてリトライします。 レート制限の残り回数とリセット時間も表示します。
-   **エラーハンドリング**: レート制限以外のエラーも適切に処理します。
-   **文字数制限**: ツイートが文字数制限を超えないようにチェックします。`count_tweet_length` 関数で URL を考慮した文字数計算を行います。

#### 依存ライブラリ

-   `tweepy`: X API クライアントとして利用します。
-   `python-dotenv`: 環境変数の読み込みに利用します。
-   `time`: 時間関連の操作に利用します。
-   `sys`: システム関連の操作に利用します。
-   `os`: OS関連の操作に利用します。
-   `re`: 正規表現操作に利用します。
-   `datetime`

#### 使い方

1.  `.env` ファイルを作成し、以下の X API キーを設定します。

    ```
    API_KEY=<APIキー>
    API_SECRET=<APIシークレット>
    ACCESS_TOKEN=<アクセストークン>
    ACCESS_SECRET=<アクセスシークレット>
    BEARER_TOKEN=<ベアラートークン>
    ```

2.  `split-text.py` を実行して、`output` ディレクトリにツイート用のテキストファイルを作成します。
3.  以下のコマンドでスクリプトを実行します。

    ```bash
    python tweet.py <投稿したい日付(例:20250125)>
    ```

## 注意事項

-   このツールを使用する前に、各ウェブサイト（NHK, テレビ東京, X）の利用規約を必ず確認してください。
-   スクレイピングはサイトに負荷をかける可能性があるため、頻繁なアクセスは避けてください。 特に、Selenium を使用する際は、`time.sleep()` などで適切な間隔を設けることを推奨します。
-   X API の利用制限を守り、過度な投稿を避けてください。`tweet.py` ではレート制限に対応していますが、短時間に大量のツイートを投稿するとアカウントが凍結される可能性があります。
-   環境変数 (`.env` ファイル) は適切に管理し、公開リポジトリにコミットしないように注意してください。`.gitignore` ファイルに `.env` を追加することを推奨します。
-   `chromedriver` は事前にインストールし、パスを通すか、`webdriver_manager` を利用してインストールする必要があります。
-   このツールは、予告なく仕様が変更される可能性があります。
-   このツールの使用によって生じたいかなる損害に対しても、作者は責任を負いません。自己責任でご利用ください。
