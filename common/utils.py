from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import logging
import configparser
import re
import time
from datetime import datetime
import pytz

# 定数定義
class Constants:
    """定数を定義するクラス"""
    class WebDriver:
        """WebDriver関連の定数"""
        LOG_LEVEL = "ERROR"  # Seleniumのログレベル

    class Time:
        """時間関連の定数"""
        DEFAULT_HOUR = 25  # 時間が見つからない場合のデフォルト値（ソートの最後になる）
        DEFAULT_MINUTE = 0
        SLEEP_SECONDS = 2 # URLを開く際の待機時間

    class Program:
        """番組関連の定数"""
        WBS_PROGRAM_NAME = "WBS"

    class Character:
        """文字関連の定数"""
        FULL_WIDTH_CHAR_WEIGHT = 2
        HALF_WIDTH_CHAR_WEIGHT = 1
        URL_CHAR_WEIGHT = 11.5

    class Format:
        """フォーマット関連の定数"""
        DATE_FORMAT = "%Y%m%d"
        DATE_FORMAT_YYYYMMDD = "%Y.%m.%d"
        DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


logger = logging.getLogger(__name__)

def setup_logger(name: str = __name__) -> logging.Logger:
    """ロガーを設定する"""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)  # INFOレベル以上のログを処理

    # 同じハンドラが重複して追加されるのを防ぐ
    if not logger.handlers:
        console_handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    # ルートロガーのレベルをERRORに設定（ルートロガーのハンドラは削除しない）
    # logging.getLogger().setLevel(logging.ERROR) # コメントアウト or 削除

    logger.info("ロガーを設定しました。")
    return logger

def load_config(config_path: str) -> configparser.ConfigParser:
    """設定ファイルを読み込む"""
    config = configparser.ConfigParser()
    try:
        config.read(config_path, encoding='utf-8')
        logging.getLogger(__name__).info(f"設定ファイル {config_path} を読み込みました。")
    except Exception as e:
        logging.getLogger(__name__).error(f"設定ファイル {config_path} の読み込みに失敗しました: {e}")
        raise
    return config

class WebDriverManager:
    """WebDriverをコンテキストマネージャーで管理するクラス"""

    def __init__(self, options=None):
        self.options = options or self.default_options()
        self.driver: webdriver.Chrome | None = None

    def default_options(self):
        """デフォルトのChromeオプションを設定する"""
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument(f"--log-level={Constants.WebDriver.LOG_LEVEL}")  # Seleniumのログレベルを設定
        return options

    def __enter__(self):
        """コンテキストに入ったときにWebDriverを作成する"""
        try:
            self.driver = webdriver.Chrome(options=self.options)
            logging.getLogger(__name__).info("Chrome WebDriverを作成しました。")
            return self.driver
        except Exception as e:
            logging.getLogger(__name__).error(f"Chrome WebDriverの作成に失敗しました: {e}")
            raise

    def __exit__(self, exc_type, exc_val, exc_tb):
        """コンテキストを抜けるときにWebDriverを終了する"""
        if self.driver:
            self.driver.quit()
            logging.getLogger(__name__).info("Chrome WebDriverを終了しました。")

def parse_programs_config(config_path: str) -> dict | None:
    """
    設定ファイルを読み込んで番組情報を辞書形式で返す。

    Args:
        config_path: 設定ファイルのパス。

    Returns:
        番組情報を格納した辞書。ファイルの種類を判別できない場合は、None
    """
    config = load_config(config_path)
    programs = {}
    logger = logging.getLogger(__name__)
    broadcaster_type = None

    # ファイル名から broadcaster_type を自動判別
    if "nhk" in config_path.lower():
        broadcaster_type = "nhk"
    elif "tvtokyo" in config_path.lower():
        broadcaster_type = "tvtokyo"
    else:
        logger.error(f"設定ファイルの種類を判別できません: {config_path}")
        return None  # または例外を投げる

    for section in config.sections():
        if section.startswith('program_'):
            try:
                program_name = config.get(section, 'name').strip()

                if broadcaster_type == 'nhk':
                    url = config.get(section, 'url').strip()
                    channel = config.get(section, 'channel', fallback="NHK").strip()
                    programs[program_name] = {"url": url, "channel": channel}
                elif broadcaster_type == 'tvtokyo':
                    url = config.get(section, 'url').strip()
                    time_str = config.get(section, 'time').strip()
                    # WBS の URL を特別扱い (リストとして保持)
                    if program_name == Constants.Program.WBS_PROGRAM_NAME:
                        if Constants.Program.WBS_PROGRAM_NAME not in programs:
                            programs[Constants.Program.WBS_PROGRAM_NAME] = {"urls": [], "time": time_str, "name": Constants.Program.WBS_PROGRAM_NAME}
                        programs[Constants.Program.WBS_PROGRAM_NAME]["urls"].append(url)
                    else:
                        programs[program_name] = {"url": url, "time": time_str, "name": program_name}
                logger.debug(f"{broadcaster_type} 番組設定を解析しました: {program_name}")

            except configparser.NoOptionError as e:
                logger.error(f"設定ファイルにエラーがあります: {e}, section: {section}")
                continue
            except Exception as e:
                logger.error(f"{broadcaster_type} 番組設定の解析中にエラーが発生しました: {e}, section: {section}")
                continue
    logger.info(f"{broadcaster_type} 番組設定ファイルを解析しました。")
    return programs

def extract_time_from_block(block: str, starts_with: str = "") -> tuple[int, int]:
    """
    番組ブロックまたは行から放送開始時間を抽出する

    Args:
        block: 抽出元の文字列 (複数行の場合は改行で区切られた文字列)
        starts_with: 特定の文字列で始まる行のみを対象とする場合に指定 (例: "●")

    Returns:
        時と分のタプル (例: (9, 30))。時間が見つからない場合は (25, 0) を返す。
    """
    lines = block.split('\n')
    for line in lines:
        if starts_with and not line.startswith(starts_with):
            continue
        time_match = re.search(r'(\d{2}:\d{2})', line)
        if time_match:
            time_str = time_match.group(1)
            hour, minute = map(int, time_str.split(':'))
            return hour, minute
    return Constants.Time.DEFAULT_HOUR, Constants.Time.DEFAULT_MINUTE

def sort_blocks_by_time(blocks: list[str]) -> list[str]:
    """番組ブロックを放送時間順にソートする"""
    def get_sort_key(block: str) -> tuple[int, int]:
        """ソート用のキーを取得する"""
        return extract_time_from_block(block)
    return sorted(blocks, key=get_sort_key)

def count_characters(text: str) -> int:
    """全角文字を2文字、半角文字を1文字としてカウントする"""
    count = 0
    for char in text:
        if ord(char) > 255:  # 全角文字判定
            count += Constants.Character.FULL_WIDTH_CHAR_WEIGHT
        else:
            count += Constants.Character.HALF_WIDTH_CHAR_WEIGHT
    return count

def count_tweet_length(text):
    """URLを11.5文字としてカウントし、全体の文字数を計算"""
    url_pattern = re.compile(r'https?://\S+')
    urls = url_pattern.findall(text)

    # 全角・半角文字をカウント (共通関数を使用)
    text_length = count_characters(text)

    # URLを11.5文字として計算
    url_length = Constants.Character.URL_CHAR_WEIGHT * len(urls)

    # 全角・半角文字とURLを考慮した長さを返す
    total_length = text_length - sum(len(url) for url in urls) + url_length
    return total_length

def to_jst_datetime(date_str: str) -> datetime:
    """YYYYMMDD形式の文字列を日本時間(JST)のdatetimeオブジェクトに変換"""
    date_obj = datetime.strptime(date_str, Constants.Format.DATE_FORMAT)
    jst = pytz.timezone('Asia/Tokyo')
    jst_datetime = jst.localize(date_obj)
    return jst_datetime

def to_utc_isoformat(jst_datetime: datetime) -> str:
    """日本時間(JST)のdatetimeオブジェクトをUTCのISOフォーマット文字列に変換"""
    utc_datetime = jst_datetime.astimezone(pytz.utc)
    utc_iso = utc_datetime.strftime(Constants.Format.DATETIME_FORMAT)
    return utc_iso

def format_date(target_date: str) -> str:
    """日付をフォーマットする (YYYYMMDD -> YYYY.MM.DD)"""
    return datetime.strptime(target_date, Constants.Format.DATE_FORMAT).strftime(Constants.Format.DATE_FORMAT_YYYYMMDD)
