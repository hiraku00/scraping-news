# スクレイピングとツイート投稿ツール

このリポジトリには、特定のニュースサイトから情報をスクレイピングし、その結果をX（旧Twitter）に投稿するPythonスクリプトが含まれています。

## 概要

このツールは以下の2つの主要なスクリプトで構成されています。

1.  **`scraping-news.py`**: NHKとテレビ東京のウェブサイトからニュース記事の情報をスクレイピングします。
2.  **`tweet.py`**: スクレイピングされた情報を基に、Xにツイートを投稿します。

## `scraping-news.py`

このスクリプトは、NHKとテレビ東京のウェブサイトから、指定された日付の番組情報を収集します。

### 機能

-   **設定ファイルの利用**: `ini`ディレクトリ内の設定ファイル（`nhk_config.ini`, `tvtokyo_config.ini`）に基づいてスクレイピング対象の番組を定義します。
-   **動的なウェブページスクレイピング**: SeleniumとChrome WebDriverを利用して、JavaScriptで動的に生成されるウェブページから情報を抽出します。
-   **マルチプロセス**: 複数の番組情報を並行してスクレイピングすることで、処理時間を短縮します。
-   **ログ出力**: 処理の進行状況やエラーを詳細にログに記録します。
-   **詳細な番組情報抽出**: 各番組のエピソードタイトル、URL、放送時間を抽出します。
-   **時間順のソート**: スクレイピングした番組情報を時間順にソートして出力します。

### 依存ライブラリ

-   `requests`: HTTPリクエストを送信します。
-   `selenium`: ウェブブラウザの自動操作に利用します。
-   `webdriver_manager`: ChromeDriverの管理に利用します。
-   `datetime`: 日付と時間の操作に利用します。
-   `os`: OS関連の操作に利用します。
-   `sys`: システム関連の操作に利用します。
-   `time`: 時間関連の操作に利用します。
-   `multiprocessing`: 並列処理に利用します。
-   `logging`: ログ出力に利用します。
-   `configparser`: 設定ファイルの解析に利用します。
-    `re`: 正規表現操作に利用します。

### 使い方

1.  `ini`ディレクトリに設定ファイルを作成します（例：`nhk_config.ini`, `tvtokyo_config.ini`）。
    -   `nhk_config.ini`の例:
        ```ini
        [program_1]
        name = BSスペシャル
        url = https://www.nhk.jp/p/bssp/ts/X7WJ4Z9R3G/episode/
        [program_2]
        name = 国際報道2025
        url = https://www.nhk.jp/p/kokusaihoudou/ts/24W8XN12ZJ/episode/
        ```
    - `tvtokyo_config.ini`の例:
        ```ini
        [program_1]
        name = WBS（トレたまneo）
        url = https://www.tv-tokyo.co.jp/news/toretama/
        time = 22:54
        [program_2]
        name = モーサテ
        url = https://www.tv-tokyo.co.jp/news/morningsatellite/
        time = 05:45
        ```
2.  以下のコマンドでスクリプトを実行します。
    ```bash
    python scraping-news.py <取得したい日付(例:20250125)>
    ```
3.  スクレイピング結果は `output` ディレクトリに日付ごとのテキストファイルとして保存されます。

### 主要な関数

-   `parse_nhk_programs_config()`: `nhk_config.ini`からNHKの番組情報を読み込みます。
-   `extract_nhk_episode_info()`: 特定の番組ページの指定日付のエピソードURLを抽出します。
-   `get_nhk_formatted_episode_info()`: 抽出したURLから番組の詳細情報を整形します。
-    `_extract_program_time()`: 番組詳細ページから放送時間を抽出します。
-   `parse_tvtokyo_programs_config()`: `tvtokyo_config.ini`からテレビ東京の番組情報を読み込みます。
-   `extract_tvtokyo_episode_urls()`: テレビ東京のニュース記事一覧ページから、特定の日付の記事URLを抽出します。
-   `fetch_tvtokyo_episode_details()`: 抽出した記事URLから詳細情報を取得します。
-   `fetch_program_info()`: 並列処理用のラッパー関数です。

## `tweet.py`

このスクリプトは、`scraping-news.py`によって生成されたテキストファイルを読み込み、その内容をX（旧Twitter）に投稿します。

### 機能

-   **X APIの利用**: `tweepy`ライブラリを使用してX APIにアクセスし、ツイートを投稿します。
-   **環境変数**: APIキーなどの認証情報は環境変数から読み込みます。
-   **スレッド形式での投稿**: スクレイピング結果をスレッド形式で投稿します。
-   **エラーハンドリング**: レート制限やHTTPエラーを適切に処理します。
-   **文字数制限**: ツイートが文字数制限を超えないようにチェックします。

### 依存ライブラリ

-   `tweepy`: X APIクライアントとして利用します。
-   `time`: 時間関連の操作に利用します。
-   `sys`: システム関連の操作に利用します。
-   `os`: OS関連の操作に利用します。
-   `dotenv`: 環境変数の管理に利用します。
-   `re`: 正規表現操作に利用します。

### 使い方

1.  `.env`ファイルを作成し、以下のX APIキーを設定します。
    ```env
    API_KEY=<APIキー>
    API_SECRET=<APIシークレット>
    ACCESS_TOKEN=<アクセストークン>
    ACCESS_SECRET=<アクセスシークレット>
    BEARER_TOKEN=<ベアラートークン>
    ```
2.  以下のコマンドでスクリプトを実行します。
    ```bash
    python tweet.py <投稿したい日付(例:20250125)>
    ```
   投稿したい日付は、`scraping-news.py`でスクレイピングした日付と合わせる必要があります。

### 主要な関数

-   `count_tweet_length()`: ツイートの文字数を計算します（URLを考慮）。
-   `post_tweet_with_retry()`: ツイートを投稿し、エラー発生時にはリトライします。

---

## 注意事項

-   このツールを使用する前に、各ウェブサイトの利用規約を必ず確認してください。
-   スクレイピングはサイトに負荷をかける可能性があるため、頻繁なアクセスは避けてください。
-   X APIの利用制限を守り、過度な投稿を避けてください。
-   環境変数は適切に管理し、漏洩しないように注意してください。
-    chromedriver は事前にインストールし、パスを通すか、`webdriver_manager`を利用してインストールする必要があります。
