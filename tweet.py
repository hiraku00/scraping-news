import tweepy
import time
import sys
import os
from dotenv import load_dotenv
from datetime import datetime
from common.constants import TWEET_MAX_LENGTH, get_header_text
from common.utils import count_tweet_length

# 環境変数の読み込み
load_dotenv()

# 環境変数名をXの開発者ポータルと一致させる
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
ACCESS_SECRET = os.getenv("ACCESS_SECRET")
BEARER_TOKEN = os.getenv("BEARER_TOKEN")

# 環境変数チェック
if not all([API_KEY, API_SECRET, ACCESS_TOKEN, ACCESS_SECRET, BEARER_TOKEN]):
    print("❌ 必要な環境変数が正しく設定されていません。")
    exit(1)

# 認証
client = tweepy.Client(
    bearer_token=BEARER_TOKEN,
    consumer_key=API_KEY,
    consumer_secret=API_SECRET,
    access_token=ACCESS_TOKEN,
    access_token_secret=ACCESS_SECRET
)

# レート制限情報を取得する関数（リトライ処理付き）
def get_rate_limit_info(client, max_retries=3, base_delay=10):
    for attempt in range(max_retries):
        try:
            response = client.get_me(user_auth=True)

            # meta 属性をチェック
            if hasattr(response, 'meta'):
                rate_limit_remaining = response.meta.get('x-rate-limit-remaining')
                rate_limit_limit = response.meta.get('x-rate-limit-limit')
                rate_limit_reset = response.meta.get('x-rate-limit-reset')

                # None でなかったらintに変換
                if rate_limit_remaining is not None:
                    rate_limit_remaining = int(rate_limit_remaining)
                if rate_limit_limit is not None:
                    rate_limit_limit = int(rate_limit_limit)
                if rate_limit_reset is not None:
                    rate_limit_reset = int(rate_limit_reset)

                print(f"Remaining calls: {rate_limit_remaining}")
                print(f"Rate limit: {rate_limit_limit}")
                print(f"Reset time (UTC timestamp): {rate_limit_reset}")

                return rate_limit_remaining, rate_limit_limit, rate_limit_reset
            else:
                print("response.meta が存在しません")
                return None, None, None

        except tweepy.TweepyException as e:
            if isinstance(e, tweepy.errors.TooManyRequests):
                delay = base_delay * (2 ** attempt)
                print(f"レートリミット exceeded: {delay}秒待機...")
                time.sleep(delay)
            else:
                print(f"Error while getting rate limit info: {e}")
                return None, None, None

    print("Max retries reached while getting rate limit info.")
    return None, None, None

# レート制限情報を取得 (最初に実行)
rate_limit_remaining, rate_limit_limit, rate_limit_reset = get_rate_limit_info(client)

# 認証チェック
try:
    user_info = client.get_me(user_auth=True)
    print(f"✅ 認証成功: @{user_info.data.username}")
except tweepy.Unauthorized as e:
    print(f"❌ 認証失敗: {e}")
    print("⚠️ 認証に失敗しましたが、処理を継続します (認証情報の確認を推奨) ⚠️")  # 警告メッセージ
    # sys.exit(1)  # プログラムを停止しない
except Exception as e:
    print(f"❌ 認証チェック中に予期せぬエラーが発生しました: {e}")
    print("⚠️ 認証チェック中にエラーが発生しましたが、処理を継続します (API接続の確認を推奨) ⚠️")  # 警告メッセージ

# コマンドライン引数から日付を取得
if len(sys.argv) < 2:
    print("使用方法: python tweet.py <日付 (例: 20250129)>")
    sys.exit(1)

date = sys.argv[1]
file_path = f"output/{date}.txt"

# 指定された日付のファイルを読み込む
try:
    with open(file_path, "r", encoding="utf-8") as file:
        tweets = file.read().strip().split("\n\n")  # 空行で区切る
except FileNotFoundError:
    print(f"エラー: {file_path} が見つかりません。")
    sys.exit(1)

# ツイート投稿関数
def post_tweet_with_retry(text, in_reply_to_tweet_id=None, max_retries=3, base_delay=10):
    global rate_limit_remaining, rate_limit_reset

    for attempt in range(max_retries):
        try:
            # レートリミット確認
            if rate_limit_remaining is not None and rate_limit_remaining <= 1:
                if rate_limit_reset is not None:
                    wait_time = datetime.fromtimestamp(rate_limit_reset) - datetime.now()
                    wait_seconds = wait_time.total_seconds()
                    if wait_seconds > 0:
                        print(f"レートリミット残り回数不足。{wait_seconds:.1f}秒待機します...")
                        time.sleep(wait_seconds)
                else:
                    print("レートリミットのリセット時間が不明です。")

            tweet_length = count_tweet_length(text) #ここを修正
            print(f"投稿しようとしたツイートの文字数: {tweet_length}") #文字数表示

            if tweet_length > TWEET_MAX_LENGTH:
                error_msg = "エラー：ツイートが文字数制限を超えています。"
                print(error_msg)
                return None

            response = client.create_tweet(
                text=text,
                in_reply_to_tweet_id=in_reply_to_tweet_id,
                user_auth=True
            )
            tweet_id = response.data["id"]
            print(f"ツイート成功: ID={tweet_id}")
            print("=" * 100)
            return tweet_id

        except tweepy.errors.BadRequest as e: #400エラー
            print(f"Twitter APIエラー (BadRequest - 400): {e}")
            if e.response is not None:  # レスポンスがある場合
                try:
                    # レスポンスボディをJSONとして解析
                    error_data = e.response.json()
                    print("エラー詳細 (JSON):")
                    print(error_data)  # エラー詳細をそのまま出力

                    # エラーメッセージの取り出し (もしあれば)
                    if 'errors' in error_data and isinstance(error_data['errors'], list):
                        for error in error_data['errors']:
                            if 'message' in error:
                                print(f"エラーメッセージ: {error['message']}") #エラーメッセージ
                except Exception as json_error:
                    print(f"レスポンスのJSON解析に失敗しました: {json_error}")
                    print(f"レスポンスボディ(raw): {e.response.text}")
            return None

        except tweepy.errors.TooManyRequests as e: #レートリミット
            delay = base_delay * (2 ** attempt)
            print(f"レートリミット exceeded: {delay}秒待機...")
            time.sleep(delay)

        except tweepy.TweepyException as e:
            print(f"Tweepyエラー: {e}") #上記以外のtweepyエラー
            return None

        except Exception as e: #Tweepy以外
            print(f"予期せぬエラー: {e}")
            return None

    print("最大リトライ回数に達しました")
    return None

# ヘッダーの作成
header_text = get_header_text(date)
if not header_text:
    print("日付の形式が正しくありません。YYYYMMDDの形式で入力してください。")
    sys.exit(1)

# 最初のツイートにヘッダーを追加
if header_text and tweets:
    first_tweet = header_text + tweets[0]
    print("投稿: ")
    print(first_tweet)
    print("-" * 50)

    # 実際にツイート
    thread_id = post_tweet_with_retry(text=first_tweet)
    if not thread_id:
        print("最初の投稿に失敗したので終了します")
        exit()
else:
    print("エラー: ヘッダーテキストが空であるか、分割されたツイートが存在しません。")
    sys.exit(1)

# 2つ目以降のツイートをスレッドとして投稿
for i, text in enumerate(tweets[1:]):
    time.sleep(5)
    print("返信投稿: ")
    print(text)
    print(f"返信対象: {thread_id}")
    print("-" * 50)

    new_thread_id = post_tweet_with_retry(text=text, in_reply_to_tweet_id=thread_id)
    if new_thread_id:
        thread_id = new_thread_id
        rate_limit_remaining = rate_limit_remaining - 1 if rate_limit_remaining is not None else None
    else:
        print(f"{i+2}番目のツイート投稿に失敗しました。")
        # continue
        break
