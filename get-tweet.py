import tweepy
import os
import time
from dotenv import load_dotenv
from datetime import datetime, timedelta
import sys
import pytz
import re
import json

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
    Twitter API v2を使ってツイートを検索し、整形前のツイートデータを返します。
    """

    if USE_API: # API を使用する場合
        try:
            client = tweepy.Client(bearer_token=BEARER_TOKEN)

            query = keyword
            if user:
                query += f" from:{user}"

            # 検索対象日を放送日の前日に設定
            jst_datetime_target = to_jst_datetime(target_date) - timedelta(days=1)

            # 日本時間の日付と時刻を作成 (検索期間は前日の00:00:00 から 23:59:59)
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
        lines = text.splitlines()  # テキストを改行で分割
        time_info = ""
        program_info = ""
        url = ""  # URLを抽出するための変数
        add_24_hour = False # フラグを追加

        # 1行目から番組名と時刻情報を抽出
        if len(lines) > 0:
            first_line = lines[0]
            parts = first_line.split()

            if len(parts) > 3 and parts[0] == "NHK" and parts[1] == "BS":
                try:
                    time_str = parts[3]  # 時刻情報だけ取得
                    date_str = parts[2] # 日付部分を取得

                    # ★★★ 修正: (深夜)表記の検出を正規表現による部分一致に変更
                    if re.search(r"\(.+深夜\)", first_line): # 正規表現で (任意の文字1文字以上 + 深夜) を検索
                        add_24_hour = True # フラグをTrueに設定
                        print(f"デバッグ: (深夜)表記を検出(正規表現)。add_24_hour = {add_24_hour}") # ★デバッグ出力1
                    else:
                        print(f"デバッグ: (深夜)表記を検出されず(正規表現)。add_24_hour = {add_24_hour}") # ★デバッグ出力1-2

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
                        print(f"デバッグ: 抽出された時刻 hour = {hour}, minute = {minute}, ampm = {ampm}") # ★デバッグ出力2

                        # 深夜フラグがTrueの場合、24時間加算
                        if add_24_hour:
                            hour += 24
                            print(f"デバッグ: 24時間加算実行。hour = {hour}") # ★デバッグ出力3

                        # 午後なら12時間加算 (深夜加算後に行う)
                        if ampm == "午後" and hour < 24: # 深夜加算された場合は24時以降になるので、ここでは加算しない
                            hour += 12
                        elif ampm == "午前" and hour == 12:
                            hour = 0 #午前0時は0時と表示するため

                        # ★★★ さらに修正:  add_24_hour フラグがTrueの場合は、24時間表記でフォーマット
                        if add_24_hour:
                            time_info = f"{hour:02d}:{minute:02d}" # 24時間表記でフォーマット
                        else:
                            time_info = f"{hour:02}:{minute:02}" # 既存の処理 (念のため残す)
                        print(f"デバッグ: time_info = {time_info}") # ★デバッグ出力4
                    else:
                        time_info = "時刻情報の抽出に失敗"
                except ValueError as e:
                    time_info = "時刻情報の抽出に失敗"

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
            if last_line.startswith("https://"):  # URLの形式を確認
                url = last_line
            else:
                url = "URLの抽出に失敗"

        formatted_text = f"{program_info}\n{content}\n{url}\n\n"
        formatted_results += formatted_text  # 結果を連結

    return formatted_results

if __name__ == '__main__':
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
