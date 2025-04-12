import tweepy
import time
import sys
import os
from dotenv import load_dotenv
from datetime import datetime
import logging # logging をインポート
from common.constants import TWEET_MAX_LENGTH, get_header_text
from common.utils import count_tweet_length, setup_logger

# --- モジュールレベルのロガーを取得 ---
logger = logging.getLogger(__name__)

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

# --- グローバル変数としてレート制限情報を保持 ---
# これらは post_tweet_with_retry で更新される可能性があるため global 宣言が必要になる
rate_limit_remaining = None
rate_limit_reset = None

# レート制限情報を取得する関数（リトライ処理付き）
def get_rate_limit_info(client, max_retries=3, base_delay=10):
    """レート制限情報を取得する関数（リトライ処理付き）"""
    global rate_limit_remaining, rate_limit_reset # グローバル変数を更新する宣言
    # モジュールレベルの logger を使用

    for attempt in range(max_retries):
        try:
            # user_auth=True が必要（アプリケーション認証ではレート情報が返らない場合がある）
            response = client.get_me(user_auth=True) # 自分自身の情報を取得してヘッダーを見る

            if hasattr(response, 'rate_limit'): # v2 では response.rate_limit に情報が入る場合がある
                rate_limit_remaining = response.rate_limit.remaining
                rate_limit_limit = response.rate_limit.limit
                rate_limit_reset = response.rate_limit.reset
                logger.info(f"レート制限情報 (v2): 残り={rate_limit_remaining}, 上限={rate_limit_limit}, リセット={datetime.fromtimestamp(rate_limit_reset) if rate_limit_reset else 'N/A'}")
                return rate_limit_remaining, rate_limit_limit, rate_limit_reset
            # v1.1 API 互換のヘッダー情報もチェック ( tweepy v4 でも取得できる場合がある )
            elif hasattr(response, 'resp') and hasattr(response.resp, 'headers'):
                 headers = response.resp.headers
                 rate_limit_remaining = int(headers.get('x-rate-limit-remaining', -1))
                 rate_limit_limit = int(headers.get('x-rate-limit-limit', -1))
                 rate_limit_reset = int(headers.get('x-rate-limit-reset', -1))
                 logger.info(f"レート制限情報 (Header): 残り={rate_limit_remaining}, 上限={rate_limit_limit}, リセット={datetime.fromtimestamp(rate_limit_reset) if rate_limit_reset > 0 else 'N/A'}")
                 return rate_limit_remaining, rate_limit_limit, rate_limit_reset
            else:
                logger.warning("レート制限情報の取得に失敗しました (レスポンス形式不明)。")
                return None, None, None

        except tweepy.TweepyException as e:
            if isinstance(e, tweepy.errors.TooManyRequests):
                delay = base_delay * (2 ** attempt)
                logger.warning(f"レートリミット超過 (情報取得時): {delay}秒待機...")
                time.sleep(delay)
            else:
                logger.error(f"レート制限情報取得中にエラー: {e}", exc_info=True)
                return None, None, None
        except Exception as e:
             logger.error(f"レート制限情報取得中に予期せぬエラー: {e}", exc_info=True)
             return None


    logger.error("レート制限情報取得のリトライ上限に達しました。")
    return None, None, None


def post_tweet_with_retry(client, text, in_reply_to_tweet_id=None, max_retries=3, base_delay=10):
    """ツイート投稿関数 (リトライ、レート制限考慮)"""
    global rate_limit_remaining, rate_limit_reset # グローバル変数を参照・更新
    # モジュールレベルの logger を使用

    for attempt in range(max_retries):
        try:
            # レートリミット事前チェック
            if rate_limit_remaining is not None and rate_limit_remaining <= 1:
                logger.warning("レートリミットの残り回数が少ないため、リセットまで待機します。")
                if rate_limit_reset is not None and rate_limit_reset > 0:
                    # UTCタイムスタンプからdatetimeオブジェクト(naive)を作成し、現在時刻(naive)と比較
                    reset_dt_naive = datetime.utcfromtimestamp(rate_limit_reset)
                    now_dt_naive = datetime.utcnow()
                    wait_time = reset_dt_naive - now_dt_naive
                    wait_seconds = max(0, wait_time.total_seconds()) + 5 # 5秒のマージン
                    logger.info(f"リセットまで {wait_seconds:.1f} 秒待機します...")
                    time.sleep(wait_seconds)
                    # 待機後にレート情報を再取得
                    get_rate_limit_info(client)
                else:
                    logger.warning("リセット時間が不明なため、{base_delay}秒待機します。")
                    time.sleep(base_delay)

            # 文字数チェック
            tweet_length = count_tweet_length(text)
            logger.info(f"ツイート投稿試行 (試行 {attempt+1}/{max_retries}): 文字数={tweet_length}, 返信先={in_reply_to_tweet_id}")
            logger.debug(f"ツイート内容:\n{text}")

            if tweet_length > TWEET_MAX_LENGTH:
                logger.error(f"エラー：ツイートが文字数制限 ({TWEET_MAX_LENGTH}) を超えています ({tweet_length}文字)。")
                return None # リトライせずに失敗

            # 投稿実行
            response = client.create_tweet(
                text=text,
                in_reply_to_tweet_id=in_reply_to_tweet_id,
                user_auth=True # ユーザー認証コンテキストで投稿
            )
            tweet_id = response.data["id"]
            logger.info(f"ツイート成功: ID={tweet_id}")
            # レート制限情報を更新 (レスポンスヘッダーから取得できる場合)
            get_rate_limit_info(client) # 投稿後のレート情報を取得
            return tweet_id

        except tweepy.errors.BadRequest as e:
            logger.error(f"Twitter APIエラー (BadRequest - 400): {e}", exc_info=True)
            # エラー詳細を出力
            if hasattr(e, 'response') and e.response is not None:
                 try:
                     error_data = e.response.json()
                     logger.error(f"エラー詳細 (JSON): {error_data}")
                 except Exception as json_error:
                     logger.error(f"レスポンスのJSON解析失敗: {json_error}")
                     logger.error(f"レスポンスボディ(raw): {e.response.text}")
            return None # リトライせずに失敗

        except tweepy.errors.Forbidden as e: # 403エラー (権限不足、重複投稿など)
            logger.error(f"Twitter APIエラー (Forbidden - 403): {e}", exc_info=True)
            # 重複投稿エラー (Duplicate content) の可能性がある
            if hasattr(e, 'api_codes') and 187 in e.api_codes:
                 logger.error("エラー: 重複ツイートの可能性があります。")
            return None # リトライせずに失敗

        except tweepy.errors.TooManyRequests as e:
            delay = base_delay * (2 ** attempt)
            logger.warning(f"レートリミット超過: {delay}秒待機...")
            time.sleep(delay)
            # 待機後にレート情報を再取得してからリトライ
            get_rate_limit_info(client)

        except tweepy.TweepyException as e:
            logger.error(f"Tweepyエラー: {e}", exc_info=True)
            # リトライするかどうかはエラー内容によるが、一旦リトライする
            delay = base_delay * (2 ** attempt)
            logger.warning(f"Tweepyエラー発生、{delay}秒待機してリトライします...")
            time.sleep(delay)

        except Exception as e:
            logger.error(f"予期せぬエラー: {e}", exc_info=True)
            # 予期せぬエラーの場合はリトライしない
            return None

    logger.error("ツイート投稿のリトライ上限回数に達しました。")
    return None

if __name__ == "__main__":
    # --- Logger Setup ---
    global_logger = setup_logger(level=logging.INFO)
    # ---------------------

    # 環境変数チェック
    if not all([API_KEY, API_SECRET, ACCESS_TOKEN, ACCESS_SECRET, BEARER_TOKEN]):
        global_logger.critical("❌ 必要な環境変数が正しく設定されていません。処理を終了します。")
        sys.exit(1)
    else:
         global_logger.info("APIキー/トークン環境変数を読み込みました。")


    # 認証クライアント作成
    try:
        client = tweepy.Client(
            bearer_token=BEARER_TOKEN, # search など読み取り系API用
            consumer_key=API_KEY,      # 以下は投稿など書き込み系API用
            consumer_secret=API_SECRET,
            access_token=ACCESS_TOKEN,
            access_token_secret=ACCESS_SECRET
        )
        # 認証チェック (自分の情報を取得してみる)
        user_info = client.get_me(user_auth=True) # ユーザー認証が必要なエンドポイント
        global_logger.info(f"✅ Twitter API認証成功: @{user_info.data.username}")
    except tweepy.errors.Unauthorized as e:
        global_logger.critical(f"❌ Twitter API認証失敗: {e}")
        sys.exit(1)
    except Exception as e:
        global_logger.critical(f"❌ Twitter APIクライアント作成または認証チェック中にエラー: {e}", exc_info=True)
        sys.exit(1)

    # レート制限情報を最初に取得
    get_rate_limit_info(client)

    # コマンドライン引数
    if len(sys.argv) < 2:
        global_logger.error("日付引数がありません。")
        print("使用方法: python tweet.py <日付 (例: 20250129)>")
        sys.exit(1)

    date = sys.argv[1]
    global_logger.info("=== tweet 処理開始 ===")
    global_logger.info(f"対象日付: {date}")

    file_path = f"output/{date}.txt"

    try:
        with open(file_path, "r", encoding="utf-8") as file:
            # ファイル内容を読み込み、空行で分割し、各要素の前後の空白を除去
            tweets_to_post = [t.strip() for t in file.read().strip().split("\n\n") if t.strip()]
        global_logger.info(f"ファイル {file_path} から {len(tweets_to_post)} 件のツイート候補を読み込みました。")
        if not tweets_to_post:
             global_logger.warning("ファイルが空か、有効なツイート候補がありません。")
             sys.exit(0) # 正常終了
    except FileNotFoundError:
        global_logger.error(f"ファイル {file_path} が見つかりません。")
        print(f"エラー: {file_path} が見つかりません。")
        sys.exit(1)
    except Exception as e:
        global_logger.error(f"ファイル読み込みエラー: {e}", exc_info=True)
        sys.exit(1)

    # ヘッダーの作成
    header_text = get_header_text(date)
    if not header_text:
        global_logger.error("日付形式エラーのためヘッダーが作成できませんでした。")
        # ヘッダーなしで投稿を続けるか、ここで終了するか検討
        # sys.exit(1)
        # ヘッダーなしで最初のツイートを投稿する場合:
        first_tweet_text = tweets_to_post[0]
    else:
         # 最初のツイートにヘッダーを追加
        first_tweet_text = header_text + tweets_to_post[0]


    global_logger.info(f"最初のツイートを投稿します...")
    # post_tweet_with_retry は内部でロガーを使用
    thread_start_id = post_tweet_with_retry(client, text=first_tweet_text)

    if not thread_start_id:
        global_logger.error("最初のツイート投稿に失敗したため、処理を終了します。")
        sys.exit(1)

    # 2つ目以降のツイートをスレッドとして投稿
    last_tweet_id = thread_start_id
    post_count = 1 # 最初のツイートをカウント
    for i, text in enumerate(tweets_to_post[1:]):
        # 投稿間に適切な待機時間を設ける (APIルール遵守とアカウント保護のため)
        wait_seconds = 5 # 基本待機時間 (定数化推奨)
        global_logger.info(f"{wait_seconds}秒待機...")
        time.sleep(wait_seconds)

        global_logger.info(f"{i+2}番目のツイートを投稿します (返信先: {last_tweet_id})...")
        new_tweet_id = post_tweet_with_retry(client, text=text, in_reply_to_tweet_id=last_tweet_id)

        if new_tweet_id:
            last_tweet_id = new_tweet_id # 次の返信先を更新
            post_count += 1
        else:
            global_logger.error(f"{i+2}番目のツイート投稿に失敗しました。以降の投稿を中止します。")
            break # 失敗したらループを抜ける

    global_logger.info(f"=== tweet 処理終了 ({post_count}/{len(tweets_to_post)} 件投稿) ===")
