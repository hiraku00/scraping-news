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
#
# OAuth 2.0 Bearer Token:
#   - 目的: API へのアクセスを認証し、主に public なエンドポイント (データの読み取り) へのアクセスを許可します。
#   - 必須: API を利用するためには必須です。これがなければAPIにアクセスできません。
#
# OAuth 1.0a (API Key, API Secret, Access Token, Access Secret):
#   - 目的: 特定のユーザーアカウント (あなたのアカウント) として、ツイートの投稿やユーザー情報の変更など、
#          ユーザーコンテキストが必要な操作を行うことを認証します。
#   - 必須: ツイートを投稿するためには必須です。
#
# まとめ:
#   - Bearer Token は API へのアクセスを許可し、
#   - OAuth 1.0a 認証は特定のアカウントとして操作することを許可します。
client = tweepy.Client(
    bearer_token=BEARER_TOKEN,  # API へのアクセス認証 (必須)
    consumer_key=API_KEY,         # OAuth 1.0a 認証用 (必須)
    consumer_secret=API_SECRET,    # OAuth 1.0a 認証用 (必須)
    access_token=ACCESS_TOKEN,      # OAuth 1.0a 認証用 (必須)
    access_token_secret=ACCESS_SECRET # OAuth 1.0a 認証用 (必須)
)

# レート制限情報を取得する関数（リトライ処理付き）
def get_rate_limit_info(client, max_retries=3, base_delay=10):
    for attempt in range(max_retries):
        try:
            response = client.get_me(user_auth=True)  # 最初のAPI呼び出し

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

# 認証チェック (OAuth 1.0a 認証情報の有効性確認)
#
# 目的: OAuth 1.0a 認証情報 (API Key, API Secret, Access Token, Access Secret) が有効であることを確認します。
#       これにより、ツイートの投稿時に認証エラーが発生する可能性を減らすことができます。
#
# 必須: 本来は必須ですが、レート制限が厳しい場合、このチェックをスキップすることがあります。
#       ただし、スキップする場合は、OAuth 1.0a 認証情報が有効であることを確認する必要があります。
#
# なぜやらなくても Tweet できるか:
#   - `client.create_tweet` 時に `user_auth=True` を指定することで、Tweepy は OAuth 1.0a 認証情報を利用して Tweet を投稿します。
#   - つまり、認証チェックをスキップしても、OAuth 1.0a 認証情報が有効であれば Tweet は投稿できます。
#   - ただし、認証情報が無効な場合、`client.create_tweet` はエラーを返します。
try:
    user_info = client.get_me(user_auth=True)  # 2回目のAPI呼び出し (OAuth 1.0a 認証情報の有効性確認)
    print(f"✅ 認証成功: @{user_info.data.username}")
except tweepy.Unauthorized as e:
    print(f"❌ 認証失敗: {e}")
    print("⚠️ 認証に失敗しましたが、処理を継続します (認証情報の確認を推奨) ⚠️")  # 警告メッセージ
    # sys.exit(1)  # プログラムを停止しない
except Exception as e:  # その他の例外もキャッチ
    print(f"❌ 認証チェック中に予期せぬエラーが発生しました: {e}")
    print("⚠️ 認証チェック中にエラーが発生しましたが、処理を継続します (API接続の確認を推奨) ⚠️")  # 警告メッセージ

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

# ツイート投稿関数 (改善版)
def post_tweet_with_retry(text, in_reply_to_tweet_id=None, max_retries=3, base_delay=10):
    global rate_limit_remaining, rate_limit_reset  # レートリミット情報をグローバル変数として参照

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

            if count_tweet_length(text) > 280:
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
            return tweet_id

        except tweepy.TweepyException as e:  # Tweepy関連の例外をまとめてキャッチ
            if isinstance(e, tweepy.errors.TooManyRequests): # レートリミット超過
                delay = base_delay * (2 ** attempt)
                print(f"レートリミット exceeded: {delay}秒待機...")
                time.sleep(delay)
            else:
                print(f"Tweepyエラー: {e}")
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
    header_text = f"{formatted_date}({japanese_weekday})のニュース・ドキュメンタリー番組など\n\n" #改行追加
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

# 2つ目以降のツイートをスレッドとして投稿 (改善)
for i, text in enumerate(tweets[1:]):  # インデックスも取得
    time.sleep(5)
    print("=" * 100)
    print("返信投稿: ")
    print(text)
    print(f"返信対象: {thread_id}")
    print("-" * 50)

    new_thread_id = post_tweet_with_retry(text=text, in_reply_to_tweet_id=thread_id)
    if new_thread_id:
        thread_id = new_thread_id  # 成功したら thread_id を更新
        rate_limit_remaining = rate_limit_remaining - 1 if rate_limit_remaining is not None else None #残り回数を減らす
    else:
        print(f"{i+2}番目のツイート投稿に失敗しました。")
        # スレッドの継続性要件に応じて、break するか、continue で次のツイートに進むかを決定

        # continue # 失敗を無視して次のツイートに進む場合
        break # 失敗したら処理を中断する場合
