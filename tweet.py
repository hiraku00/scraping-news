import tweepy
import time
import sys
import os
import re
from dotenv import load_dotenv
from datetime import datetime, timedelta

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

# URLの文字数計算関数
def count_tweet_length(text):
    url_pattern = re.compile(r'https?://\S+')
    urls = url_pattern.findall(text)

    # 全角文字を2文字としてカウント
    text_length = 0
    for char in text:
        if ord(char) > 255:  # Unicodeコードポイントが255より大きい場合は全角とみなす
            text_length += 2
        else:
            text_length += 1

    # URLを11.5文字として計算
    url_length = 11.5 * len(urls)

    # 全角・半角文字とURLを考慮した長さを返す
    total_length = text_length - sum(len(url) for url in urls) + url_length
    return total_length

# 認証 (OAuth 2.0 Bearer Token と OAuth 1.0a の併用)
client = tweepy.Client(
    bearer_token=BEARER_TOKEN,
    consumer_key=API_KEY,
    consumer_secret=API_SECRET,
    access_token=ACCESS_TOKEN,
    access_token_secret=ACCESS_SECRET
)

# 認証チェック（user_auth=Trueを追加）
try:
    user_info = client.get_me(user_auth=True)
    print(f"✅ 認証成功: @{user_info.data.username}")
except tweepy.Unauthorized as e:
    print(f"❌ 認証失敗: {e}")
    sys.exit(1)

# コマンドライン引数から日付を取得
if len(sys.argv) < 2:
    print("使用方法: python tweet.py <日付 (例: 20250129)>")
    sys.exit(1)

date = sys.argv[1]

# 曜日を日本語で取得する関数
def get_japanese_weekday(date):
    weekdays = ["月", "火", "水", "木", "金", "土", "日"]
    return weekdays[date.weekday()]

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
    for attempt in range(max_retries):
        try:
            if count_tweet_length(text) > 280:
                print("エラー：ツイートが文字数制限を超えています。")
                return None

            response = client.create_tweet(
                text=text,
                in_reply_to_tweet_id=in_reply_to_tweet_id,
                user_auth=True  # ユーザーコンテキストを明示
            )
            return response.data["id"]

        except tweepy.HTTPException as e:
            if e.response.status_code == 429:
                delay = base_delay * (2 ** attempt)
                print(f"レートリミット exceeded: {delay}秒待機...")
                time.sleep(delay)
            else:
                print(f"HTTPエラー ({e.response.status_code}): {e}")
                return None
        except Exception as e:
            print(f"予期せぬエラー: {e}")
            return None

    print("最大リトライ回数に達しました")
    return None

# ヘッダーの作成
try:
    target_date_dt = datetime.strptime(date, '%Y%m%d')
    formatted_date = target_date_dt.strftime('%y/%m/%d')
    japanese_weekday = get_japanese_weekday(target_date_dt)
    header_text = f"{formatted_date}({japanese_weekday})の各ニュースの特集など\n\n" #改行追加
except ValueError:
    print("日付の形式が正しくありません。YYYYMMDDの形式で入力してください。")
    sys.exit(1)

# 最初のツイートにヘッダーを追加
first_tweet = header_text + tweets[0]  # ヘッダーを追加
print("投稿: ")
print(first_tweet)
print("-" * 50)

# 実際にツイート
thread_id = post_tweet_with_retry(text=first_tweet)
if not thread_id:
    print("最初の投稿に失敗したので終了します")
    exit()

# 2つ目以降のツイートをスレッドとして投稿
for text in tweets[1:]:
    time.sleep(5)  # API制限回避のため待機
    print("返信投稿: ")
    print(text)
    print(f"返信対象: {thread_id}")
    print("-" * 50)

    thread_id = post_tweet_with_retry(text=text, in_reply_to_tweet_id=thread_id)
    if not thread_id:
        print("返信投稿に失敗したので終了します。")
        break
