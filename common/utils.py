from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import logging
import configparser
import re
import time
from datetime import datetime, timedelta
from enum import Enum, auto
import pytz
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

class ScrapeStatus(Enum):
    """スクレイピング処理のステータスを表す Enum"""
    SUCCESS = auto()
    FAILURE = auto()
    NOT_FOUND = auto() # 必要に応じて追加 (例: 対象エピソードが見つからない場合など)

# --- モジュールレベルのロガーを取得 ---
logger = logging.getLogger(__name__)

# 定数定義クラス (Constants) は変更なし ...
class Constants:
    """定数を定義するクラス"""
    class WebDriver:
        """WebDriver関連の定数"""
        LOG_LEVEL = "WARNING"  # Seleniumのログレベル (ERROR -> WARNING に変更推奨)

    class Time:
        """時間関連の定数"""
        DEFAULT_HOUR = 25  # 時間が見つからない場合のデフォルト値（ソートの最後になる）
        DEFAULT_MINUTE = 0
        SLEEP_SECONDS = 2 # URLを開く際の待機時間
        DEFAULT_TIMEOUT = 10 # デフォルトのタイムアウト時間
        SHORT_TIMEOUT = 5 # 短めのタイムアウトを追加 (必要に応じて調整)

    class Program:
        """番組関連の定数"""
        WBS_PROGRAM_NAME = "WBS"

    class Character:
        """文字関連の定数"""
        FULL_WIDTH_CHAR_WEIGHT = 2
        HALF_WIDTH_CHAR_WEIGHT = 1
        URL_CHAR_WEIGHT = 23

    class Format:
        """フォーマット関連の定数"""
        DATE_FORMAT = "%Y%m%d"
        DATE_FORMAT_YYYYMMDD = "%Y.%m.%d"
        DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

    class CSSSelector:
        """CSSセレクタを定義するクラス"""
        # --- NHK ---
        EPISODE_INFO = 'gc-stream-panel-info'
        DATE_YEAR = 'gc-atom-text-for-date-year'
        DATE_DAY = 'gc-atom-text-for-date-day'
        DATE_TEXT_NO_YEAR = 'gc-stream-panel-info-title'
        DATE_TEXT_WITH_YEAR = 'gc-stream-panel-info-title-firstbroadcastdate-date'
        EPISODE_URL_TAG = 'a'
        TITLE = 'title'
        NHK_PLUS_URL_SPAN = '//div[@class="detailed-memo-body"]/span[contains(@class, "detailed-memo-headline")]/a[contains(text(), "NHKプラス配信はこちらからご覧ください")]'
        EYECATCH_IMAGE_DIV = 'gc-images.is-medium.eyecatch' # このセレクタは古い可能性がある
        IFRAME_ID = 'eyecatchIframe'                      # このセレクタは古い可能性がある
        STREAM_PANEL_INFO_META = "stream_panel--info--meta" # このセレクタは古い可能性がある

        # --- TV Tokyo ---
        TVTOKYO_VIDEO_ITEM = 'div[id^="News_Detail__VideoItem__"]'
        TVTOKYO_DATE_SPAN = 'span.sc-c564813-0.iCkNIF[role="presentation"]'
        TVTOKYO_POST_LINK = 'a[href*="post_"]'
        TVTOKYO_EPISODE_TITLE = "Live_Episode_Detail_EpisodeItemFullTitle"

# --- logging.basicConfig の呼び出しを削除 ---
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s') # ★削除

def setup_logger(name: str = None, level=logging.INFO) -> logging.Logger:
    """
    ルートロガーまたは指定された名前のロガーにハンドラとフォーマッタを設定する。
    既にハンドラが設定されている場合は、重複して設定しない。
    """
    # nameがNoneの場合、ルートロガーを設定
    logger_instance = logging.getLogger(name) # nameがNoneならルートロガー

    # ハンドラがまだ設定されていない場合のみ基本的な設定を行う
    # (ルートロガーに設定されていれば、通常は子ロガーにも伝播する)
    target_logger = logging.getLogger() # ルートロガーを取得してチェック
    if not target_logger.handlers:
        logger_instance.setLevel(level)
        handler = logging.StreamHandler() # コンソール出力ハンドラ
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')
        handler.setFormatter(formatter)
        logger_instance.addHandler(handler)
        logger_instance.info(f"ロガー '{logger_instance.name}' の基本的なハンドラを設定しました。")
    # else:
        # logger_instance.debug(f"ロガー '{logger_instance.name}' は既にハンドラが設定されています。")

    return logger_instance

def load_config(config_path: str) -> configparser.ConfigParser:
    """設定ファイルを読み込む"""
    config = configparser.ConfigParser()
    try:
        # モジュールレベルの logger を使用
        config.read(config_path, encoding='utf-8')
        logger.info(f"設定ファイル {config_path} を読み込みました。")
    except Exception as e:
        logger.error(f"設定ファイル {config_path} の読み込みに失敗しました: {e}", exc_info=True)
        raise
    return config

class WebDriverManager:
    """WebDriverをコンテキストマネージャーで管理するクラス"""
    def __init__(self, options=None):
        self.options = options or self.default_options()
        self.driver: webdriver.Chrome | None = None
        # クラス固有のロガーを取得
        self.logger = logging.getLogger(self.__class__.__name__)

    def default_options(self):
        """デフォルトのChromeオプションを設定する"""
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        # Selenium Driver のログ出力を抑制
        options.add_experimental_option('excludeSwitches', ['enable-logging'])
        # Chrome自身のログレベルを設定 (INFO, WARNING, ERROR)
        options.add_argument(f"--log-level={Constants.WebDriver.LOG_LEVEL.lower()}")
        return options

    def __enter__(self):
        """コンテキストに入ったときにWebDriverを作成する"""
        try:
            self.driver = webdriver.Chrome(options=self.options)
            # self.logger を使用
            self.logger.info("Chrome WebDriver を作成しました。")
            return self.driver
        except Exception as e:
            # self.logger を使用
            self.logger.error(f"Chrome WebDriver の作成に失敗しました: {e}", exc_info=True)
            raise

    def __exit__(self, exc_type, exc_val, exc_tb):
        """コンテキストを抜けるときにWebDriverを終了する"""
        if self.driver:
            self.driver.quit()
            # self.logger を使用
            self.logger.info("Chrome WebDriver を終了しました。")

def parse_programs_config(config_path: str) -> dict | None:
    """
    設定ファイルを読み込んで番組情報を辞書形式で返す。
    キーは ini ファイルの 'name' の値を使用する。
    """
    config = load_config(config_path)
    programs = {}
    logger = logging.getLogger(__name__)
    broadcaster_type = None

    if "nhk" in config_path.lower():
        broadcaster_type = "nhk"
    elif "tvtokyo" in config_path.lower():
        broadcaster_type = "tvtokyo"
    else:
        logger.error(f"設定ファイルの種類を判別できません: {config_path}")
        return None

    for section in config.sections():
        # settings セクションなどをスキップ
        if not section.startswith('program_'):
            continue
        try:
            # iniファイルから情報を取得（stripで前後の空白除去）
            name_in_config = config.get(section, 'name', fallback='').strip()
            url = config.get(section, 'url', fallback='').strip()

            # name または url が空の場合はスキップ
            if not name_in_config or not url:
                logger.warning(f"セクション '{section}' で name または url が空です。スキップします。")
                continue

            dict_key = name_in_config # ★辞書のキーとして使う変数

            if broadcaster_type == 'nhk':
                channel = config.get(section, 'channel', fallback="NHK").strip()
                if dict_key not in programs:
                    program_data = {"url": url, "channel": channel, "name": dict_key} # nameも追加
                    logger.debug(f"NHK番組設定を追加: キー='{dict_key}', データ={program_data}")
                    programs[dict_key] = program_data
                else:
                    logger.warning(f"NHK番組設定が重複: キー='{dict_key}' (セクション: {section})。スキップ。")

            elif broadcaster_type == 'tvtokyo':
                time_str = config.get(section, 'time', fallback='').strip()
                if not time_str:
                    logger.warning(f"セクション '{section}' で time が空です。スキップします。")
                    continue

                if dict_key not in programs:
                    # 新規追加：urlsキーにリストとして格納
                    program_data = {
                        "urls": [url],
                        "time": time_str,
                        "name": dict_key # nameも追加
                    }
                    logger.debug(f"テレ東番組設定を追加: キー='{dict_key}', データ={program_data}")
                    programs[dict_key] = program_data
                else:
                    # 既存キー：urlsリストに追加 (存在チェックも行う)
                    if 'urls' in programs[dict_key] and isinstance(programs[dict_key]['urls'], list):
                        if url not in programs[dict_key]['urls']: # 重複追加を防ぐ
                            programs[dict_key]['urls'].append(url)
                            logger.debug(f"テレ東番組設定にURL追加: キー='{dict_key}', 追加URL='{url}'")
                        else:
                            logger.debug(f"テレ東番組設定のURLは既に存在: キー='{dict_key}', URL='{url}'")
                    else:
                        logger.warning(f"テレ東番組 '{dict_key}' の設定構造が不正か 'urls' キーがありません。URL '{url}' を追加できません。")

        except configparser.NoOptionError as e:
            logger.error(f"設定ファイルエラー(必須オプション欠落): {e}, section: {section}")
            continue
        except Exception as e:
            logger.error(f"{broadcaster_type} 番組設定解析中にエラー: {e}, section: {section}", exc_info=True)
            continue

    # 最後にデバッグ用に生成された辞書全体を出力
    logger.debug(f"--- {broadcaster_type} 設定解析完了 ---")
    for key, value in programs.items():
        logger.debug(f"キー: '{key}', 値: {value}")
    logger.info(f"{broadcaster_type} 番組設定 ({len(programs)}件) を解析しました。")
    return programs

# --- extract_time_from_block, sort_blocks_by_time, count_characters, count_tweet_length ---
# --- to_jst_datetime, to_utc_isoformat, format_date ---
# これらの関数は変更なし (内部の logger はモジュールレベルのものを使用)
def extract_time_from_block(block: str, starts_with: str = "") -> tuple[int, int]:
    lines = block.split('\n')
    for line in lines:
        if starts_with and not line.startswith(starts_with):
            continue
        time_match = re.search(r'\(.*?(\d{1,2}:\d{2})', line)
        if not time_match:
            time_match = re.search(r'(\d{1,2}:\d{2})', line)

        if time_match:
            time_str = time_match.group(1)
            try:
                hour, minute = map(int, time_str.split(':'))
                return hour, minute
            except ValueError:
                logger.warning(f"時間文字列のパースに失敗: {time_str} in '{line[:30]}...'")
                continue
    return Constants.Time.DEFAULT_HOUR, Constants.Time.DEFAULT_MINUTE

def sort_blocks_by_time(blocks: list[str]) -> list[str]:
    def get_sort_key(block: str) -> tuple[int, int]:
        return extract_time_from_block(block, starts_with='●')
    try:
        return sorted(blocks, key=get_sort_key)
    except Exception as e:
        logger.error(f"ブロックのソート中にエラーが発生しました: {e}", exc_info=True)
        return blocks

def count_characters(text: str) -> int:
    count = 0
    for char in text:
        if ord(char) > 255:
            count += Constants.Character.FULL_WIDTH_CHAR_WEIGHT
        else:
            count += Constants.Character.HALF_WIDTH_CHAR_WEIGHT
    return count

def count_tweet_length(text):
    url_pattern = re.compile(r'https?://\S+')
    urls = url_pattern.findall(text)
    text_without_urls = url_pattern.sub('', text)
    text_length = count_characters(text_without_urls)
    url_length = Constants.Character.URL_CHAR_WEIGHT * len(urls)
    total_length = text_length + url_length
    return total_length

def to_jst_datetime(date_str: str) -> datetime:
    try:
        date_obj = datetime.strptime(date_str, Constants.Format.DATE_FORMAT)
        jst = pytz.timezone('Asia/Tokyo')
        jst_datetime = jst.localize(date_obj)
        return jst_datetime
    except ValueError as e:
        logger.error(f"日付文字列のパースに失敗しました: {date_str} - {e}", exc_info=True)
        raise

def to_utc_isoformat(jst_datetime: datetime) -> str:
    if jst_datetime.tzinfo is None:
        logger.warning("タイムゾーン情報がないdatetimeオブジェクトが渡されました。JSTとして扱います。")
        jst = pytz.timezone('Asia/Tokyo')
        jst_datetime = jst.localize(jst_datetime)
    utc_datetime = jst_datetime.astimezone(pytz.utc)
    utc_iso = utc_datetime.strftime(Constants.Format.DATETIME_FORMAT)
    return utc_iso

def format_date(target_date: str) -> str:
    try:
        return datetime.strptime(target_date, Constants.Format.DATE_FORMAT).strftime(Constants.Format.DATE_FORMAT_YYYYMMDD)
    except ValueError as e:
        logger.error(f"日付フォーマットに失敗しました: {target_date} - {e}", exc_info=True)
        return target_date

# --- extract_program_time_info ---
# 内部の setup_logger 呼び出しを削除
def extract_program_time_info(driver: webdriver.Chrome, program_title: str, episode_url: str, channel: str, max_retries: int = 1, retry_interval: int = 1) -> str:
    """番組詳細ページから放送時間を抽出し、フォーマットする (NHK用)"""
    # logger = setup_logger(__name__)  # <-- 削除

    # 特定番組の固定時間 (設定ファイルへの移行推奨箇所)
    if program_title == "国際報道 2025":
        logger.debug(f"固定時間を返します: {program_title}")
        return f"({channel} 22:00-22:45)" # 定数化推奨

    for attempt in range(max_retries):
        try:
            time_element = WebDriverWait(driver, Constants.Time.DEFAULT_TIMEOUT).until(
                EC.presence_of_element_located((By.CLASS_NAME, Constants.CSSSelector.STREAM_PANEL_INFO_META)) # セレクタ確認必要
            )
            time_element_text = time_element.text.strip()
            logger.debug(f"取得した時間文字列: '{time_element_text}' - {program_title}")

            start_ampm, start_time, end_ampm, end_time = _extract_time_parts(time_element_text)
            if start_time and end_time:
                start_time_24h = _to_24h_format(start_ampm, start_time)
                end_time_24h = _to_24h_format(end_ampm, end_time)
                formatted_time = f"({channel} {start_time_24h}-{end_time_24h})"
                logger.info(f"放送時間を抽出しました: {formatted_time} - {program_title}")
                return formatted_time
            else:
                logger.warning(f"時間部分の抽出に失敗しました。取得文字列: '{time_element_text}' - {program_title}, {episode_url}")
                break # パース失敗時はリトライしない
        except (TimeoutException, NoSuchElementException) as e:
            # NoSuchElementException も TimeoutException と同様に扱う
            logger.warning(f"時間要素が見つかりませんでした (試行 {attempt+1}/{max_retries}): {program_title} - {e.__class__.__name__}")
            if attempt < max_retries - 1:
                time.sleep(retry_interval)
            else:
                logger.error(f"時間要素の取得に失敗しました (最大リトライ回数超過): {program_title}, {episode_url}")
        except Exception as e:
            logger.error(f"放送時間情報の抽出中に予期せぬエラー (試行 {attempt+1}): {e} - {program_title}, {episode_url}", exc_info=True)
            break # 予期せぬエラーはリトライしない

    # ループを抜けた場合（失敗した場合）
    logger.error(f"放送時間の取得に最終的に失敗しました: {program_title}, {episode_url}")
    return "(放送時間取得失敗)"

# --- _extract_time_parts, _to_24h_format, format_program_time, extract_time_info_from_text ---
# これらのヘルパー関数は変更なし (内部の logger はモジュールレベルのものを使用)
def _extract_time_parts(time_text: str) -> tuple[str | None, str | None, str | None, str | None]:
    match = re.search(r'(午前|午後)?\s?(\d{1,2}:\d{2})\s?-\s?(午前|午後)?\s?(\d{1,2}:\d{2})', time_text)
    if match:
        return match.group(1), match.group(2), match.group(3), match.group(4)
    else:
        logger.debug(f"時刻パターンの抽出に失敗: '{time_text}'")
        return None, None, None, None

def _to_24h_format(ampm: str | None, time_str: str) -> str:
    try:
        hour, minute = map(int, time_str.split(":"))
        if ampm == "午後" and hour != 12:
            hour += 12
        elif ampm == "午前" and hour == 12:
            hour = 0
        return f"{hour:02}:{minute:02}"
    except ValueError:
        logger.error(f"時刻変換エラー: ampm='{ampm}', time_str='{time_str}'")
        return time_str

def format_program_time(program_name: str, weekday: int, default_time: str) -> str:
    """番組時間をフォーマットする (TV Tokyo用)"""
    if program_name.startswith(Constants.Program.WBS_PROGRAM_NAME):
        time_str = "22:00-22:58" if weekday < 4 else "23:00-23:58" # 金曜以外と金曜 (定数化推奨)
        channel = "テレ東" # 定数化推奨
        logger.debug(f"WBS ({'月-木' if weekday < 4 else '金'}) の時間を設定: {time_str}")
        return f"({channel} {time_str})"
    else:
        channel = "テレ東" # 定数化推奨
        logger.debug(f"{program_name} のデフォルト時間を設定: {default_time}")
        return f"({channel} {default_time})"

def extract_time_info_from_text(text: str) -> str:
    """ツイートテキストから時刻情報を抽出・整形する"""
    time_info = "時刻抽出失敗"
    add_24_hour = False

    if re.search(r"[（\(]深夜[）\)]", text):
        add_24_hour = True
        logger.debug("深夜表記を検出")

    time_match = re.search(r'(\d{1,2})日\s?\(.\)\s?(午前|午後)(\d{1,2}):(\d{2})', text)
    if time_match:
        # day = int(time_match.group(1)) # day は使わない
        ampm = time_match.group(2)
        hour = int(time_match.group(3))
        minute = int(time_match.group(4))
        logger.debug(f"抽出された時刻要素: ampm={ampm}, hour={hour}, minute={minute}")

        if ampm == "午後" and hour != 12:
            hour += 12
        elif ampm == "午前" and hour == 12:
            hour = 0

        if add_24_hour:
            if hour < 12: # 0時～11時台なら24時間加算
                hour += 24
                logger.debug(f"24時間加算実行 -> hour={hour}")

        time_info = f"{hour:02}:{minute:02}"
        logger.debug(f"整形後の時刻情報: {time_info}")
    else:
        logger.warning(f"時刻情報のパターンマッチに失敗しました: '{text[:50]}...'")

    return time_info
