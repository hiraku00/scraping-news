import tweepy
import time
import sys
import os
from dotenv import load_dotenv
from datetime import datetime
import logging # logging をインポート
from common.constants import TWEET_MAX_LENGTH, get_header_text
from common.utils import count_tweet_length, setup_logger

# --- ロギング設定 ---
def setup_logging():
    """ロギングの設定を行う"""
    # ルートロガーを取得
    logger = logging.getLogger()
    
    # 既存のハンドラをクリア
    logger.handlers = []
    
    # ログレベルの設定
    logger.setLevel(logging.INFO)
    
    # コンソールハンドラの設定
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # フォーマッタの設定
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    
    # ハンドラを追加
    logger.addHandler(console_handler)
    
    return logger

# ロガーの初期化
logger = setup_logging()

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

def update_rate_limit_from_response(response):
    """レスポンスからレート制限情報を取得・更新する試み"""
    global rate_limit_remaining, rate_limit_reset
    updated = False
    try:
        # v1.1 互換ヘッダーを試す (response.resp.headers が最も可能性が高い)
        if hasattr(response, 'resp') and hasattr(response.resp, 'headers'):
            headers = response.resp.headers
            remaining = headers.get('x-rate-limit-remaining')
            reset = headers.get('x-rate-limit-reset')
            limit = headers.get('x-rate-limit-limit') # limit もあれば取得

            if remaining is not None and reset is not None:
                rate_limit_remaining = int(remaining)
                rate_limit_reset = int(reset)
                rate_limit_limit_val = int(limit) if limit is not None else 'N/A'
                logger.info(f"レート制限情報更新 (Header): 残り={rate_limit_remaining}, 上限={rate_limit_limit_val}, リセット={datetime.fromtimestamp(rate_limit_reset)}")
                updated = True
            else:
                logger.debug("レスポンスヘッダーにレート制限情報 (x-rate-limit-*) が見つかりませんでした。")
        # v2 レスポンスの rate_limit 属性も念のため試す
        elif hasattr(response, 'rate_limit') and response.rate_limit is not None:
            rate_limit_remaining = response.rate_limit.remaining
            rate_limit_reset = response.rate_limit.reset
            rate_limit_limit = response.rate_limit.limit
            logger.info(f"レート制限情報更新 (v2 response): 残り={rate_limit_remaining}, 上限={rate_limit_limit}, リセット={datetime.fromtimestamp(rate_limit_reset)}")
            updated = True
        else:
            logger.debug("レスポンスオブジェクトからレート制限情報を取得できませんでした。")
    except (ValueError, TypeError) as e:
        logger.warning(f"レスポンスからのレート制限情報解析中にエラー: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"レート制限情報更新中に予期せぬエラー: {e}", exc_info=True)

    # 更新できなかった場合、グローバル変数をNoneにしておく（任意）
    # if not updated:
    #     rate_limit_remaining = None
    #     rate_limit_reset = None

    return updated

def post_tweet_with_retry(client, text, in_reply_to_tweet_id=None, max_retries=3, base_delay=10):
    """ツイート投稿関数 (リトライ、レート制限考慮)"""
    global rate_limit_remaining, rate_limit_reset
    # logger = logging.getLogger(__name__) # 関数内でロガーを取得

    for attempt in range(max_retries):
        try:
            # レートリミット事前チェック (前回情報があれば利用)
            # (この部分は既存のままでも良いが、情報が更新されない可能性を考慮)
            if rate_limit_remaining is not None and rate_limit_remaining <= 1:
                logger.warning("前回のレートリミット情報に基づき、リセットまで待機する可能性があります。")
                # (待機処理は既存のまま)
                if rate_limit_reset is not None and rate_limit_reset > 0:
                    reset_dt_naive = datetime.utcfromtimestamp(rate_limit_reset)
                    now_dt_naive = datetime.utcnow()
                    wait_time = reset_dt_naive - now_dt_naive
                    wait_seconds = max(0, wait_time.total_seconds()) + 5 # 5秒のマージン
                    if wait_seconds > 0:
                        logger.info(f"リセットまで {wait_seconds:.1f} 秒待機します...")
                        time.sleep(wait_seconds)
                        rate_limit_remaining = None # 待機後は情報をクリア
                        rate_limit_reset = None
                    else:
                        logger.info("リセット時間を過ぎているため、待機せずに続行します。")
                        rate_limit_remaining = None
                        rate_limit_reset = None
                else:
                    logger.warning(f"リセット時間が不明なため、{base_delay}秒待機します。")
                    time.sleep(base_delay)
                    rate_limit_remaining = None
                    rate_limit_reset = None

            # 文字数チェック (省略)
            tweet_length = count_tweet_length(text)
            logger.info(f"ツイート投稿試行 (試行 {attempt+1}/{max_retries}): 文字数={tweet_length}, 返信先={in_reply_to_tweet_id}")
            if tweet_length > TWEET_MAX_LENGTH:
                logger.error(f"エラー：ツイートが文字数制限 ({TWEET_MAX_LENGTH}) を超えています ({tweet_length}文字)。")
                return None

            # 投稿実行
            response = client.create_tweet(
                text=text,
                in_reply_to_tweet_id=in_reply_to_tweet_id,
                user_auth=True
            )
            tweet_id = response.data["id"]
            logger.info(f"ツイート成功: ID={tweet_id}")

            # ★★★ 投稿成功後にレスポンスからレート制限情報を更新 ★★★
            update_rate_limit_from_response(response)

            return tweet_id

        except tweepy.errors.TooManyRequests as e:
            logger.warning(f"レートリミット超過 (429エラー): {e}")
            reset_time = None
            if hasattr(e, 'response') and e.response is not None and hasattr(e.response, 'headers'):
                reset_header = e.response.headers.get('x-rate-limit-reset')
                if reset_header:
                    try:
                        reset_time = int(reset_header)
                        rate_limit_reset = reset_time # グローバル変数も更新
                        # タイムゾーンを考慮してローカル時間を表示する場合 (参考)
                        # local_reset_time = datetime.fromtimestamp(reset_time)
                        # logger.info(f"レートリミットリセット時刻 (ヘッダーより, UTC): {datetime.utcfromtimestamp(reset_time)}")
                        # logger.info(f"レートリミットリセット時刻 (ヘッダーより, Local): {local_reset_time}")
                        # 現在はUTCで表示
                        logger.info(f"レートリミットリセット時刻 (ヘッダーより): {datetime.fromtimestamp(reset_time)}")
                    except (ValueError, TypeError):
                        logger.warning("x-rate-limit-reset ヘッダーの解析に失敗。")

            # 待機時間を計算
            if reset_time:
                reset_dt_naive = datetime.utcfromtimestamp(reset_time)
                now_dt_naive = datetime.utcnow()
                wait_time = reset_dt_naive - now_dt_naive
                # ヘッダーの時間を使う場合はマージンを少し多めにとる (例: 5秒)
                delay = max(1, wait_time.total_seconds()) + 5
                logger.warning(f"リセット時刻に基づき、{delay:.1f} 秒待機します...")
            else:
                # ヘッダーが取れない場合は指数バックオフ
                delay = base_delay * (2 ** attempt)
                logger.warning(f"リセット時刻不明。{delay}秒待機します...")

            # --- カウントダウン表示付き待機 ---
            wait_start_time = time.monotonic() # より正確な時間計測のため
            total_wait_seconds_int = int(delay) # 整数秒を取得

            try:
                for i in range(total_wait_seconds_int, 0, -1):
                    # \r でカーソルを行頭に戻し、同じ行に残り時間を上書き表示
                    # end='' で改行を防ぐ
                    # 後ろのスペースは、秒数が減ったときに前の桁の数字が残らないようにするため
                    print(f"\r⏳ 残り {i} 秒...          ", end='')
                    time.sleep(1) # 1秒待機

                # ループが終わったら表示をクリア
                print("\r✅ 待機完了。                 ")

                # 念のため、計算上の待機時間と実際の待機時間の差を調整
                # (ループ処理や print のオーバーヘッドを考慮)
                elapsed_time = time.monotonic() - wait_start_time
                remaining_fractional_sleep = delay - elapsed_time
                if remaining_fractional_sleep > 0:
                    time.sleep(remaining_fractional_sleep)

            except KeyboardInterrupt:
                print("\n🚫 待機中に中断されました (Ctrl+C)。")
                # 中断した場合、例外を再送出してスクリプトを停止させるか、
                # 特定の処理を行うかを選択できます。
                # ここでは再送出してプログラムを終了させます。
                raise

            # リトライ前にレート情報をリセット（次の試行で再取得を試みる or エラー待ち）
            rate_limit_remaining = None
            rate_limit_reset = None

        except tweepy.errors.Forbidden as e: # ★★★ Forbidden (403) エラーを個別に捕捉 ★★★
            logger.error(f"Twitter APIエラー (Forbidden - 403): {e}")
            # API code 187 が Duplicate status
            is_duplicate = False
            if hasattr(e, 'api_codes') and 187 in e.api_codes:
                is_duplicate = True
                logger.error("エラー原因: 重複ツイート (API Code 187)")
            elif "duplicate content" in str(e).lower():
                is_duplicate = True
                logger.error("エラー原因: 重複ツイート (エラーメッセージより判断)")

            if is_duplicate:
                logger.error("重複ツイートのため、リトライせずに終了します。")
                return None # ★★★ リトライしない ★★★
            else:
                logger.error("重複以外のForbiddenエラーのため、リトライせずに終了します。")
                # 必要であればエラー詳細を出力
                if hasattr(e, 'response') and e.response is not None:
                    try:
                        error_data = e.response.json()
                        logger.error(f"エラー詳細 (JSON): {error_data}")
                    except Exception as json_error:
                        logger.error(f"レスポンスのJSON解析失敗: {json_error}")
                        logger.error(f"レスポンスボディ(raw): {e.response.text}")
                return None # ★★★ リトライしない ★★★

        except tweepy.errors.BadRequest as e:
            logger.error(f"Twitter APIエラー (BadRequest - 400): {e}", exc_info=True)
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_data = e.response.json()
                    logger.error(f"エラー詳細 (JSON): {error_data}")
                except Exception as json_error:
                    logger.error(f"レスポンスのJSON解析失敗: {json_error}")
                    logger.error(f"レスポンスボディ(raw): {e.response.text}")
            return None # リトライせずに失敗

        except tweepy.TweepyException as e:
            logger.error(f"Tweepyエラー: {e}", exc_info=True)
            delay = base_delay * (2 ** attempt)
            logger.warning(f"Tweepyエラー発生、{delay}秒待機してリトライします...")
            time.sleep(delay)

        except Exception as e: # 予期せぬエラー
            logger.error(f"予期せぬエラー: {e}", exc_info=True)
            return None

    logger.error("ツイート投稿のリトライ上限回数に達しました。")
    return None

def main(date=None, output_dir="output"):
    """メイン処理を実行する関数
    
    Args:
        date (str, optional): 処理対象の日付 (YYYYMMDD形式)。
                             指定がない場合はコマンドライン引数から取得します。
        output_dir (str, optional): 出力ディレクトリのパス。デフォルトは"output"。
    """
    # --- Logger Setup ---
    global_logger = setup_logger(level=logging.INFO)
    # ---------------------

    # 環境変数チェック
    if not all([API_KEY, API_SECRET, ACCESS_TOKEN, ACCESS_SECRET, BEARER_TOKEN]):
        global_logger.critical("❌ 必要な環境変数が正しく設定されていません。処理を終了します。")
        return 1
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
        return 1
    except Exception as e:
        global_logger.critical(f"❌ Twitter APIクライアント作成または認証チェック中にエラー: {e}", exc_info=True)
        return 1

    # 日付の取得
    if date is None:
        # コマンドライン引数から日付を取得
        if len(sys.argv) < 2:
            global_logger.error("日付引数がありません。")
            print("使用方法: python tweet.py <日付 (例: 20250115)>")
            return 1
        date = sys.argv[1]
    global_logger.info("=== tweet 処理開始 ===")
    global_logger.info(f"対象日付: {date}")

    # 出力ディレクトリが存在しない場合は作成
    os.makedirs(output_dir, exist_ok=True)
    file_path = os.path.join(output_dir, f"{date}.txt")

    try:
        with open(file_path, "r", encoding="utf-8") as file:
            # ファイル内容を読み込み、空行で分割し、各要素の前後の空白を除去
            tweets_to_post = [t.strip() for t in file.read().strip().split("\n\n") if t.strip()]
        global_logger.info(f"ファイル {file_path} から {len(tweets_to_post)} 件のツイート候補を読み込みました。")
        if not tweets_to_post:
            global_logger.warning("ファイルが空か、有効なツイート候補がありません。")
            return 0  # 正常終了
    except FileNotFoundError:
        global_logger.error(f"ファイル {file_path} が見つかりません。")
        print(f"エラー: {file_path} が見つかりません。")
        return 1
    except Exception as e:
        global_logger.error(f"ファイル読み込みエラー: {e}", exc_info=True)
        return 1

    # ヘッダーの作成
    header_text = get_header_text(date)
    if not header_text:
        global_logger.error("日付形式エラーのためヘッダーが作成できませんでした。")
        # ヘッダーなしで最初のツイートを投稿する場合:
        first_tweet_text = tweets_to_post[0]
    else:
        # 最初のツイートにヘッダーを追加
        first_tweet_text = header_text + tweets_to_post[0]

    # 最初のツイートを投稿
    global_logger.info("=" * 50)
    global_logger.info("📢 ツイートを開始します")
    global_logger.info("-" * 50)
    global_logger.info(f"📝 1/{len(tweets_to_post)} 件目のツイート内容:")
    global_logger.info(first_tweet_text)
    global_logger.info("-" * 50)
    
    thread_start_id = post_tweet_with_retry(client, text=first_tweet_text)

    if not thread_start_id:
        global_logger.error("❌ 最初のツイート投稿に失敗したため、処理を終了します。")
        return 1
    else:
        global_logger.info(f"✅ 1/{len(tweets_to_post)} 件目のツイートを投稿しました (ID: {thread_start_id})")

    # 2つ目以降のツイートをスレッドとして投稿
    last_tweet_id = thread_start_id
    post_count = 1  # 最初のツイートをカウント
    for i, text in enumerate(tweets_to_post[1:], 2):
        # 投稿間に適切な待機時間を設ける (APIルール遵守とアカウント保護のため)
        wait_seconds = 5  # 基本待機時間 (定数化推奨)
        global_logger.info(f"⏳ 次のツイートまで {wait_seconds} 秒待機します...")
        time.sleep(wait_seconds)

        global_logger.info("-" * 50)
        global_logger.info(f"📝 {i}/{len(tweets_to_post)} 件目のツイート内容 (返信先: {last_tweet_id}):")
        global_logger.info(text)
        global_logger.info("-" * 50)
        
        new_tweet_id = post_tweet_with_retry(client, text=text, in_reply_to_tweet_id=last_tweet_id)

        if new_tweet_id:
            last_tweet_id = new_tweet_id  # 次の返信先を更新
            post_count += 1
            global_logger.info(f"✅ {i}/{len(tweets_to_post)} 件目のツイートを投稿しました (ID: {new_tweet_id})")
        else:
            global_logger.error(f"❌ {i}/{len(tweets_to_post)} 件目のツイート投稿に失敗しました。以降の投稿を中止します。")
            break  # 失敗したらループを抜ける

    global_logger.info(f"=== tweet 処理終了 ({post_count}/{len(tweets_to_post)} 件投稿) ===")
    return 0

if __name__ == "__main__":
    sys.exit(main())
