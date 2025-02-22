import tweepy
import os
import time
from dotenv import load_dotenv
from datetime import datetime, timedelta
import sys  # sys モジュールをインポート
import pytz  # pip install pytz
import re # 正規表現
import json # JSON 処理のため

# API を使用するかダミーデータを使用するか (API 制限を回避するため)
USE_API = True  # API を使用する場合は True に変更

# 環境変数の読み込み
load_dotenv()

# 環境変数名をXの開発者ポータルと一致させる
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
ACCESS_SECRET = os.getenv("ACCESS_SECRET")
BEARER_TOKEN = os.getenv("BEARER_TOKEN")

def to_jst_datetime(date_str):
    """YYYYMMDD形式の文字列を日本時間(JST)のdatetimeオブジェクトに変換"""
    date_obj = datetime.strptime(date_str, "%Y%m%d")
    jst = pytz.timezone('Asia/Tokyo')
    jst_datetime = jst.localize(date_obj)
    return jst_datetime

def to_utc_isoformat(jst_datetime):
    """日本時間(JST)のdatetimeオブジェクトをUTCのISOフォーマット文字列に変換"""
    utc_datetime = jst_datetime.astimezone(pytz.utc)
    utc_iso = utc_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")
    return utc_iso

def search_tweets(keyword, target_date, user=None, count=10):
    """
    Twitter API v2を使ってツイートを検索し、整形されたテキストを返します。
    """

    if USE_API: # API を使用する場合
        try:
            client = tweepy.Client(bearer_token=BEARER_TOKEN)

            query = keyword
            if user:
                query += f" from:{user}"

            # 日本時間の日付と時刻を作成
            jst_datetime_start = to_jst_datetime(target_date)
            jst_datetime_end = to_jst_datetime(target_date) + timedelta(days=1, microseconds=-1) # 23:59:59.999

            # UTCに変換してISOフォーマットにする
            start_time = to_utc_isoformat(jst_datetime_start)
            end_time = to_utc_isoformat(jst_datetime_end)

            # max_results の範囲チェック
            if count < 10 or count > 100:
                print("max_results は 10 以上 100 以下の値を指定してください。")
                return None

            response = client.search_recent_tweets(
                query=query,
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
                print("\n待機完了。リトライします...")  # 改行を追加

                return search_tweets(keyword, target_date, user, count)  # 再帰的にリトライ
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
                "created_at": "2025-02-19 10:03:30+00:00",
                "text": "NHK BS 18日(火) 午後10:45\\nＢＳ世界のドキュメンタリー「ナイス・レディーズ　ウクライナ　私たちの人生」\\nhttps://t.co/CYDKGbaIUK",
                "author_id": 3022192682
            },
            {
                "created_at": "2025-02-19 10:03:30+00:00",
                "text": "NHK BS 18日(火) 午前9:25\\nＢＳ世界のドキュメンタリー選「アウシュビッツ　女たちの“サボタージュ”」\\nhttps://t.co/9cR5AREinr",
                "author_id": 3022192682
            },
            {
                "created_at": "2025-02-19 10:03:30+00:00",
                "text": "NHK BS 19日(水) 午後10:45\\nＢＳ世界のドキュメンタリー▽マルコムＸ　暗殺の真相～アメリカ社会に挑んだ男～\\nhttps://t.co/iOJ03NrVMq",
                "author_id": 3022192682
            },
            {
                "created_at": "2025-02-19 10:03:30+00:00",
                "text": "NHK BS 19日(水) 午前9:25\\nＢＳ世界のドキュメンタリー　選「ドイツの内なる脅威　躍進する“極右”政党」\\nhttps://t.co/EBrcrtGW6V",
                "author_id": 3022192682
            },
            {
                "created_at": "2025-02-19 10:03:30+00:00",
                "text": "NHK BS 19日(水) 午前0:25\\nＢＳ世界のドキュメンタリー　選「ドイツの内なる脅威　躍進する“極右”政党」\\nhttps://t.co/EBrcrtGW6V",
                "author_id": 3022192682
            },
             {
                "created_at": "2025-02-20 10:03:30+00:00",
                "text": "NHK BS 20日(木) 午後11:00\\nＢＳ世界のドキュメンタリー「ナイス・レディーズ　ウクライナ　私たちの「人生」」\\nhttps://t.co/CYDKGbaIUK",
                "author_id": 3022192682
            },
             {
                "created_at": "2025-02-20 10:03:30+00:00",
                "text": "NHK BS 20日(木) 午後11:00\\nＢＳ世界のドキュメンタリー「マルコムＸ　「暗殺」の真相～アメリカ社会に挑んだ男～」\\nhttps://t.co/iOJ03NrVMq",
                "author_id": 3022192682
            }
        ]
        """
        return json.loads(dummy_json_data) # JSONをパースしたPythonオブジェクトを返す

def format_tweet_data(tweet_data):
    """
    ツイートデータを受け取り、指定されたフォーマットで整形されたテキストを返します。
    """
    formatted_results = ""

    for tweet in tweet_data:
        text = tweet["text"]
        print(f"text: {text}")  # デバッグ: 元のツイートテキストを表示
        lines = text.splitlines()  # テキストを改行で分割
        time_info = ""
        program_info = ""
        url = ""  # URLを抽出するための変数

        # 1行目から番組名と時刻情報を抽出
        if len(lines) > 0:
            first_line = lines[0]
            parts = first_line.split()
            print(f"first_line: {first_line}")  # デバッグ: 1行目の内容を表示
            print(f"parts: {parts}")  # デバッグ: 分割された要素を表示

            if len(parts) > 3 and parts[0] == "NHK" and parts[1] == "BS":
                try:
                    time_str = parts[3]  # 時刻情報だけ取得
                    print(f"time_str: {time_str}")  # デバッグ: 時刻情報の文字列を表示

                    # 午前/午後を判定
                    if "午後" in time_str:
                        ampm = "午後"
                    elif "午前" in time_str:
                        ampm = "午前"
                    else:
                        ampm = None

                    # 時刻を分割
                    time_parts = re.findall(r'\d+', time_str)  # 数字だけを抽出
                    if len(time_parts) == 2:
                        hour = int(time_parts[0])
                        minute = int(time_parts[1])

                        # 午後なら12時間加算
                        if ampm == "午後" and hour != 12:
                            hour += 12
                        elif ampm == "午前" and hour == 12:
                            hour = 0 #午前0時は0時と表示するため

                        time_info = f"{hour:02}:{minute:02}"
                    else:
                        time_info = "時刻情報の抽出に失敗"
                except ValueError as e:
                    time_info = "時刻情報の抽出に失敗"
                    print(f"Error extracting time: {e}")  # デバッグ: エラー内容を表示

        program_info = f"●BS世界のドキュメンタリー（NHK BS {time_info}-）"

        #不要な文字列を削除
        content = ""
        if len(lines) > 1:
            content = lines[1]
            content = re.sub(r'ＢＳ世界のドキュメンタリー[▽　選「]*', '', content).strip() # 既存の処理
            content = re.sub(r'」$', '', content).strip() # ★ 行末の「」を削除する処理を追加

        # URLの抽出 (最終行にあると仮定)
        if len(lines) > 0:
            last_line = lines[-1]
            if last_line.startswith("https://t.co/"):  # URLの形式を確認
                url = last_line
            else:
                url = "URLの抽出に失敗"

        formatted_text = f"{program_info}\n{content}\n{url}\n\n"
        formatted_results += formatted_text  # 結果を連結

    return formatted_results

if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("使用方法: python get-tweet.py YYYYMMDD")
        exit()
    target_date = sys.argv[1]

    keyword = "ＢＳ世界のドキュメンタリー"
    user = "nhk_docudocu"
    count = 10

    tweets = search_tweets(keyword, target_date, user, count) # APIリクエスト or ダミーデータ取得

    if tweets: # データが存在する場合
        formatted_text = format_tweet_data(tweets) #ツイートを整形
        # ファイル名を作成
        now = datetime.now()
        filename = f"output/{target_date}_sekai-docu.txt"

        # outputディレクトリが存在しなければ作成
        if not os.path.exists("output"):
            os.makedirs("output")

        # テキストファイルに書き出し
        try:
            with open(filename, "w", encoding="utf-8") as f:  # utf-8でエンコード
                f.write(formatted_text)
            print(f"テキストファイルを {filename} に出力しました。")

        except Exception as e:
            print(f"ファイル書き込みエラー: {e}")
    else:
        print("ツイートの検索に失敗しました。")
