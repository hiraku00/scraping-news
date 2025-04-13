import tweepy
import os
import time
from dotenv import load_dotenv
from datetime import datetime, timedelta
import sys
import re
import json
import unicodedata
import logging # logging をインポート
from common.utils import to_jst_datetime, to_utc_isoformat, extract_time_info_from_text, setup_logger

# --- モジュールレベルのロガーを取得 ---
logger = logging.getLogger(__name__)

# 定数定義
USE_API = True  # API を使用する場合は True に変更

# 番組名の定義
PROGRAM_NAMES = [
    "アナザーストーリーズ",
    "ＢＳ世界のドキュメンタリー",
    "Asia Insight",
    "Ａｓｉａ　Ｉｎｓｉｇｈｔ",
    "英雄たちの選択"
]

# 環境変数の読み込み
load_dotenv()

# 環境変数名をXの開発者ポータルと一致させる
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
ACCESS_SECRET = os.getenv("ACCESS_SECRET")
BEARER_TOKEN = os.getenv("BEARER_TOKEN")

def create_search_queries(program_names, user):
    """
    APIクエリとX検索窓用のクエリを生成する
    """
    # APIクエリ用（スペースを含む番組名もそのまま使用可能）
    api_keyword = " OR ".join(program_names)
    api_query = f"from:{user} ({api_keyword})"

    # X検索窓用（番組名をダブルクォートで囲む）
    x_keyword = " OR ".join(f'"{name}"' for name in program_names)

    return api_query, x_keyword

def search_tweets(target_date, user=None, count=10):
    """
    Twitter API v2を使ってツイートを検索し、整形前のツイートデータを返します。
    """

    if USE_API: # API を使用する場合
        try:
            client = tweepy.Client(bearer_token=BEARER_TOKEN)

            # APIクエリとX検索窓用のクエリを生成
            api_query, x_keyword = create_search_queries(PROGRAM_NAMES, user)

            # 検索対象日を放送日の前日に設定
            jst_datetime_target = to_jst_datetime(target_date) - timedelta(days=1)

            # 日付文字列を作成 (YYYY-MM-DD形式)
            search_date = jst_datetime_target.strftime("%Y-%m-%d")

            # 検索クエリとXでの実際の検索内容を表示
            print("\n検索クエリ情報:")
            print(f"APIクエリ: {api_query}")
            print(f"Xでの検索窓入力内容: from:{user} {x_keyword} since:{search_date}_00:00:00_JST until:{search_date}_23:59:59_JST")

            # 日本時間の日付と時刻を作成 (検索期間は前日の00:00:00 から 23:59:59)
            #                                        ↑前日に Tweet されているため
            jst_datetime_start = jst_datetime_target.replace(hour=0, minute=0, second=0, microsecond=0)
            jst_datetime_end = jst_datetime_target.replace(hour=23, minute=59, second=59, microsecond=999999)

            # UTCに変換してISOフォーマットにする
            start_time = to_utc_isoformat(jst_datetime_start)
            end_time = to_utc_isoformat(jst_datetime_end)

            # max_results の範囲チェック
            if count < 10 or count > 100:
                print("max_results は 10 以上 100 以下の値を指定してください。")
                return None

            response = client.search_recent_tweets(
                query=api_query,
                max_results=count,
                tweet_fields=["created_at", "text", "author_id"],
                start_time=start_time,
                end_time=end_time
            )

            tweets = response.data
            if tweets is None:
                print("該当するツイートが見つかりませんでした。")
                return None

            return tweets # 整形前のtweetsデータを返す

        except tweepy.TweepyException as e:
            if isinstance(e, tweepy.errors.TooManyRequests):
                reset_timestamp = int(e.response.headers.get('x-rate-limit-reset', 0))
                reset_datetime = datetime.fromtimestamp(reset_timestamp)
                now_datetime = datetime.now()
                wait_seconds = int((reset_datetime - now_datetime).total_seconds())  # 小数点以下を切り捨てる
                wait_seconds += 3  # プラス3秒追加

                print(f"レート制限超過。リセットまで{wait_seconds}秒待機します。")
                for i in range(wait_seconds, 0, -1):  # カウントダウン
                    print(f"\rリセットまで残り: {i}秒", end="", flush=True)  # 上書き表示
                    time.sleep(1)
                print("\n待機完了。リトライ...")  # 改行を追加

                return search_tweets(target_date, user, count)  # 再帰的にリトライ
            else:
                print(f"エラーが発生しました: {e}")
                return None
        except Exception as e:
            print(f"予期せぬエラーが発生しました: {e}")
            return None
    else: # ダミーデータを使用する場合
        # ダミーJSONデータ（APIからのレスポンスを想定）
        dummy_json_data = """
        [
            {
                "created_at": "2025-02-11 10:03:30+00:00",
                "text": "NHK BS 14日(金) 午前0:45 (13日深夜)\\nＢＳ世界のドキュメンタリー「カラーでよみがえるアメリカ　１９６０年代」\\nhttps://t.co/EBrcrtGW6V",
                "author_id": 3022192682
            },
            {
                "created_at": "2025-02-11 10:03:30+00:00",
                "text": "NHK BS 13日(木) 午前1:35 (12日深夜)\\nＢＳ世界のドキュメンタリー「カラーでよみがえるアメリカ　１９５０年代」\\nhttps://t.co/EBrcrtGW6V",
                "author_id": 3022192682
            },
            {
                "created_at": "2025-02-11 10:03:30+00:00",
                "text": "NHK BS 12日(水) 午後10:45\\nＢＳ世界のドキュメンタリー　クィアな人生の再出発　ボリウッド式カミングアウト\\nhttps://www.nhk.jp/p/wdoc/ts/88Z7X45XZY/episode/te/GL6G38NLMM/",
                "author_id": 3022192682
            },
            {
                "created_at": "2025-02-11 10:03:30+00:00",
                "text": "NHK BS 12日(水) 午前9:25\\nＢＳ世界のドキュメンタリー　選「モダン・タイムス　チャップリンの声なき抵抗」\\nhttps://t.co/EBrcrtGW6V",
                "author_id": 3022192682
            },
            {
                "created_at": "2024-02-24 10:03:30+00:00",
                "text": "NHK 総合 25日(火) 午後11:35\\nアナザーストーリーズ「“怪物”に出会った日～井上尚弥×ノニト・ドネア～」\\nhttps://t.co/xxxxxxxxxxx",
                "author_id": 3022192682
            }

        ]
        """
        return json.loads(dummy_json_data) # JSONをパースしたPythonオブジェクトを返す

def format_program_info(text, time_info):
    """番組情報をフォーマットする"""
    program_info = "番組情報の抽出に失敗" # デフォルト値

    # 番組情報のフォーマット（PROGRAM_NAMESを使用）
    for program_name in PROGRAM_NAMES:
        if program_name in text:
            # Asia Insightの場合は英語表記を使用
            display_name = "Asia Insight" if "Asia" in program_name or "Ａｓｉａ" in program_name else program_name
            display_name = display_name.replace("ＢＳ世界のドキュメンタリー", "BS世界のドキュメンタリー")
            program_info = f"●{display_name}(NHK BS {time_info}-)"
            break

    return program_info

def extract_program_info(lines, text):
    """1行目から番組名と時刻情報を抽出する"""
    time_info = ""
    program_info = ""

    if len(lines) > 0:
        first_line = lines[0]
        parts = first_line.split()
        # 放送局と日付の基本部分を確認
        if len(parts) > 3 and parts[0] == "NHK" and parts[1] == "BS":
            time_info = extract_time_info_from_text(first_line) # utils.py の共通関数を使用
            program_info = format_program_info(text, time_info)

    return time_info, program_info

def extract_url_from_lines(lines):
    """ツイートの行からURLを抽出する"""
    if len(lines) > 0:
        last_line = lines[-1]
        if last_line.startswith("https://"):
            return last_line
    return "URLの抽出に失敗"

def cleanup_content(text, content):
    """不要な文字列を削除する # ★追加: 不要文字列削除関数"""
    # ＢＳ世界のドキュメンタリーの場合
    if "ＢＳ世界のドキュメンタリー" in text:
        content = re.sub(r'ＢＳ世界のドキュメンタリー[▽　選「]*', '', content).strip()
        content = re.sub(r'」$', '', content).strip()
    # アナザーストーリーズの場合
    elif "アナザーストーリーズ" in text:
        content = re.sub(r'アナザーストーリーズ[▽　選「]*', '', content).strip()
        content = re.sub(r'」$', '', content).strip()
    return content

def extract_content_from_lines(lines, text):
    """ツイートの本文を抽出して整形する"""
    content = ""
    if len(lines) > 1:
        content = lines[1]
        content = cleanup_content(text, content)
    return content

def format_tweet_data(tweet_data):
    """
    ツイートデータを受け取り、指定されたフォーマットで整形されたテキストを返します。
    """
    formatted_results = [] # 文字列ではなくリストで返すように変更
    # logger = setup_logger(__name__) # <-- 削除、モジュールレベルの logger を使用

    if not tweet_data:
        logger.warning("フォーマット対象のツイートデータがありません。")
        return []

    for tweet in tweet_data:
        text = tweet.get("text", "") # .getでキー存在確認
        if not text:
            logger.warning("テキストが空のツイートデータをスキップします。")
            continue
        lines = text.splitlines()

        time_info, program_info = extract_program_info(lines, text)
        content = extract_content_from_lines(lines, text)
        url = extract_url_from_lines(lines)

        # 各要素が取得できたか確認
        if program_info == "番組情報の抽出に失敗" or not content or url == "URL抽出失敗":
            logger.warning(f"フォーマットに必要な情報が不足しているためスキップ: {text[:50]}...")
            continue

        # 結果を整形してリストに追加
        formatted_text = f"{program_info}\n・{content}\n{url}\n" # 末尾の改行を削除
        formatted_results.append(formatted_text.strip()) # 前後の空白を削除して追加

    logger.info(f"{len(formatted_results)}件のツイートをフォーマットしました。")
    return formatted_results

def save_to_file(formatted_list: list[str], target_date: str):
    """フォーマットされたテキストのリストをファイルに保存する"""
    if not formatted_list:
        logger.warning("保存するフォーマット済みデータがありません。ファイルは作成されません。")
        return

    filename = f"output/{target_date}_tweet.txt"
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)

    try:
        # リストの各要素を改行2つで結合して書き込む
        content_to_write = "\n\n".join(formatted_list) + "\n" # 最後に改行を1つ追加
        with open(filename, "w", encoding="utf-8") as f:
            f.write(content_to_write)
        logger.info(f"テキストファイルを {filename} に出力しました。")
    except Exception as e:
        logger.error(f"ファイル書き込みエラー: {e}", exc_info=True)

if __name__ == '__main__':
    # --- Logger Setup ---
    # main 関数の最初で一度だけ呼び出す
    global_logger = setup_logger(level=logging.INFO)
    # ---------------------

    if len(sys.argv) < 2:
        global_logger.error("日付引数がありません。")
        print("使用方法: python get-tweet.py YYYYMMDD")
        exit(1)
    target_date = sys.argv[1]
    global_logger.info("=== get-tweet 処理開始 ===")
    global_logger.info(f"対象日付: {target_date}")

    user = "nhk_docudocu" # 定数化推奨
    count = 20 # 検索件数を少し増やす (API上限は100)

    tweets = search_tweets(target_date, user, count)

    if tweets:
        # format_tweet_data はリストを返す
        formatted_list = format_tweet_data(tweets)
        # save_to_file でファイル保存
        save_to_file(formatted_list, target_date)
    else:
        global_logger.warning("ツイートデータの取得に失敗したか、データがありませんでした。")

    global_logger.info("=== get-tweet 処理終了 ===")
