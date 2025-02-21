import tweepy
import json
import os
import time
from dotenv import load_dotenv
from datetime import datetime
import sys  # sys モジュールをインポート

# 環境変数の読み込み
load_dotenv()

# 環境変数名をXの開発者ポータルと一致させる
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
ACCESS_SECRET = os.getenv("ACCESS_SECRET")
BEARER_TOKEN = os.getenv("BEARER_TOKEN")

def search_tweets(keyword, target_date, user=None, count=10):
    """
    Twitter API v2を使ってツイートを検索し、JSON形式で結果を返します。
    """

    try:
        client = tweepy.Client(bearer_token=BEARER_TOKEN)

        query = keyword
        if user:
            query += f" from:{user}"

        date_obj = datetime.strptime(target_date, "%Y%m%d")
        iso_date = date_obj.strftime("%Y-%m-%d")
        start_time = f"{iso_date}T00:00:00Z"
        end_time = f"{iso_date}T23:59:59Z"

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
        print(f'debug tweets: {tweets}')
        if tweets is None:
            print("該当するツイートが見つかりませんでした。")
            return None

        results = []
        for tweet in tweets:
            results.append({
                "created_at": str(tweet.created_at),
                "text": tweet.text,
                "author_id": tweet.author_id
            })

        return json.dumps(results, indent=4, ensure_ascii=False)

    except tweepy.TweepyException as e:
        if isinstance(e, tweepy.errors.TooManyRequests):
            reset_timestamp = int(e.response.headers.get('x-rate-limit-reset', 0))
            reset_datetime = datetime.fromtimestamp(reset_timestamp)
            now_datetime = datetime.now()
            wait_seconds = int((reset_datetime - now_datetime).total_seconds()) # 小数点以下を切り捨てる

            print(f"レート制限超過。リセットまで{wait_seconds}秒待機します。")
            for i in range(wait_seconds, 0, -1):  # カウントダウン
                print(f"\rリセットまで残り: {i}秒", end="", flush=True) #上書き表示
                time.sleep(1)
            print("\n待機完了。リトライします...")  # 改行を追加

            return search_tweets(keyword, target_date, user, count)  # 再帰的にリトライ
        else:
            print(f"エラーが発生しました: {e}")
            return None
    except Exception as e:
        print(f"予期せぬエラーが発生しました: {e}")
        return None


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("使用方法: python get-tweet.py YYYYMMDD")
        exit()
    target_date = sys.argv[1]

    keyword = "BS世界のドキュメンタリー"
    user = "NHK_BS1"
    count = 10

    json_output = search_tweets(keyword, target_date, user, count)

    if json_output:
        # ファイル名を作成
        now = datetime.now()
        filename = f"output/{target_date}_sekai-docu.json"

        # outputディレクトリが存在しなければ作成
        if not os.path.exists("output"):
            os.makedirs("output")

        # JSONファイルに書き出し
        try:
            with open(filename, "w", encoding="utf-8") as f:  # utf-8でエンコード
                f.write(json_output)
            print(f"JSONファイルを {filename} に出力しました。")

        except Exception as e:
            print(f"ファイル書き込みエラー: {e}")
    else:
        print("ツイートの検索に失敗しました。")
