

scraping-news.py
```
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime, timedelta
import os
import sys
import time
import multiprocessing
import re
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from common.utils import setup_logger, load_config, WebDriverManager, parse_programs_config, sort_blocks_by_time, Constants
import logging
from common.base_scraper import BaseScraper
from common import utils  # 追加

# utils.py から関数をインポート
from common.utils import (
    format_date,
    format_program_time,
    extract_program_time_info # ★修正: _extract_program_time -> extract_program_time_info
)

# CustomExpectedConditions.pyをcommonに作成
from common.CustomExpectedConditions import CustomExpectedConditions

class NHKScraper(BaseScraper):
    """NHKの番組情報をスクレイピングするクラス"""

    def __init__(self, config):
        super().__init__(config)

    def get_program_info(self, program_name: str, target_date: str) -> str | None:
        """指定された番組の情報を取得する"""
        program_info = self.config.get(program_name)
        if not program_info:
            self.logger.warning(f"{program_name} の設定情報が見つかりません")
            return None

        with WebDriverManager() as driver:
            try:
                self.logger.info(f"検索開始: {program_name}")
                driver.get(program_info["url"])

                episode_url = self._extract_nhk_episode_info(driver, target_date, program_name)
                if episode_url:
                    formatted_output = self._get_nhk_formatted_episode_info(driver, program_name, episode_url, program_info["channel"])
                    return formatted_output
                else:
                    self.logger.warning(f"{program_name} が見つかりませんでした - {program_info['url']}")
                    return None
            except Exception as e:
                self.logger.error(f"エラーが発生しました: {e} - {program_name}, {program_info['url']}")
                return None

    def _extract_nhk_episode_info(self, driver, target_date: str, program_title: str) -> str | None:
        """NHKのエピソード情報を抽出する"""
        try:
            episodes = self._find_episode_elements(driver, program_title)
            if not episodes:
                return None

            target_date_dt = datetime.strptime(target_date, '%Y%m%d')

            for episode in episodes:
                episode_date = self._extract_episode_date(episode, program_title)
                if episode_date:
                    if episode_date == target_date_dt:
                        episode_url = self._extract_episode_url(episode, program_title)
                        return episode_url
            return None  # 一致するエピソードが見つからなかった場合

        except Exception as e:
            self.logger.error(f"エピソード情報抽出中にエラーが発生しました: {e} - {program_title}")
            return None

    def _find_episode_elements(self, driver, program_title: str):
        """エピソード要素リストを取得する"""
        try:
            WebDriverWait(driver, utils.Constants.Time.DEFAULT_TIMEOUT).until(CustomExpectedConditions.page_is_ready())
            episodes = WebDriverWait(driver, utils.Constants.Time.DEFAULT_TIMEOUT).until(
                EC.presence_of_all_elements_located((By.CLASS_NAME, Constants.CSSSelector.EPISODE_INFO)) # ★修正: CSSセレクタを定数から参照
            )
            return episodes
        except TimeoutException:
            self.logger.warning(f"エピソード要素が見つかりませんでした: {program_title}")
            return None # None を返すことを明示

    def _extract_episode_date(self, episode, program_title: str) -> datetime | None:
        """エピソード要素から日付を抽出する"""
        date_text = self._extract_date_text(episode, program_title)
        if date_text:
            return self._parse_date_text(date_text, program_title)
        return None

    def _extract_date_text(self, episode, program_title: str) -> str | None:
        """エピソード要素から日付テキストを抽出する"""
        try:
            try:
                date_element = episode.find_element(By.CLASS_NAME, 'gc-stream-panel-info-title-firstbroadcastdate-date') # 変更なし
                year_element = date_element.find_element(By.CLASS_NAME, Constants.CSSSelector.DATE_YEAR) # ★修正: CSSセレクタを定数から参照
                day_element = date_element.find_element(By.CLASS_NAME, Constants.CSSSelector.DATE_DAY) # ★修正: CSSセレクタを定数から参照
                year_text = year_element.text.strip()
                day_text = day_element.text.strip()
                date_text = f"{year_text}{day_text}" # 変更なし
            except NoSuchElementException:
                date_element = episode.find_element(By.CLASS_NAME, Constants.CSSSelector.DATE_TEXT_NO_YEAR) # ★修正: CSSセレクタを定数から参照
                date_text = date_element.text.strip()
            return date_text
        except NoSuchElementException:
            self.logger.debug(f"日付要素が見つかりませんでした: {program_title}")
            return None

    def _parse_date_text(self, date_text: str, program_title: str) -> datetime | None:
        """日付テキストをdatetimeオブジェクトにパースする"""
        match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', date_text)
        if match:
            year, month, day = match.groups()
            return datetime(int(year), int(month), int(day))
        else:
            self.logger.debug(f"日付テキストのパースに失敗: {date_text} - {program_title}")
            return None

    def _extract_episode_url(self, episode, program_title: str) -> str | None:
        """エピソード要素からURLを抽出する"""
        try:
            episode_url = episode.find_element(By.TAG_NAME, Constants.CSSSelector.EPISODE_URL_TAG).get_attribute("href") # ★修正: CSSセレクタを定数から参照
            self.logger.debug(f"エピソード情報を抽出しました: {program_title} - {episode_url}")
            return episode_url
        except NoSuchElementException:
            self.logger.debug(f"エピソードURLが見つかりませんでした: {program_title}") # ログレベル debug に変更
            return None

    def _get_nhk_formatted_episode_info(self, driver, program_title: str, episode_url: str, channel: str) -> str | None:
        """NHKのエピソード情報を整形する"""
        try:
            self._get_nhk_episode_detail_page(driver, episode_url)
            episode_title = self._extract_episode_title(driver)
            if not episode_title:
                return None

            if program_title == "BSスペシャル":
                return self._format_bs_special_output(driver, program_title, channel, episode_url, episode_title)

            nhk_plus_url = self._extract_nhk_plus_url(driver)

            formatted_output = self._process_eyecatch_or_iframe(driver, program_title, episode_url, channel, episode_title, nhk_plus_url)
            if formatted_output:
                return formatted_output

            # eyecatch, iframe どちらの処理も失敗した場合のフォールバック処理
            return self._format_fallback_output(driver, program_title, episode_url, channel, episode_title)

        except Exception as e:
            self.logger.error(f"エラーが発生しました: {e} - {program_title}, {episode_url}")
            return None

    def _get_nhk_episode_detail_page(self, driver, episode_url: str):
        """エピソード詳細ページに遷移し、ページの準備完了を待つ"""
        driver.get(episode_url)
        WebDriverWait(driver, utils.Constants.Time.DEFAULT_TIMEOUT).until(CustomExpectedConditions.page_is_ready())

    def _extract_episode_title(self, driver) -> str | None:
        """エピソードタイトルを抽出する"""
        try:
            target_element = WebDriverWait(driver, utils.Constants.Time.DEFAULT_TIMEOUT).until(
                EC.presence_of_element_located((By.CLASS_NAME, Constants.CSSSelector.TITLE)) # ★修正: CSSセレクタを定数から参照
            )
            episode_title = target_element.text.strip().encode('utf-8', 'ignore').decode('utf-8', 'replace')
            return episode_title # タイトルを返す
        except (TimeoutException, NoSuchElementException) as e:
            self.logger.warning(f"エピソードタイトルの取得に失敗しました: {e}")
            return None

    def _format_bs_special_output(self, driver, program_title: str, channel: str, episode_url: str, episode_title: str) -> str:
        """BSスペシャル用の出力フォーマット"""
        program_time = f"({channel} 22:45-23:35)"
        final_url = driver.current_url
        formatted_output = f"●{program_title}{program_time}\n"
        formatted_output += f"・{episode_title}\n"
        formatted_output += f"{final_url}\n"
        self.logger.info(f"{program_title} の詳細情報を取得しました")
        return formatted_output

    def _extract_nhk_plus_url(self, driver) -> str | None:
        """NHKプラスのURLを抽出する"""
        try:
            span_element = WebDriverWait(driver, utils.Constants.Time.DEFAULT_TIMEOUT).until(
                EC.presence_of_element_located((By.XPATH, Constants.CSSSelector.NHK_PLUS_URL_SPAN)) # ★修正: CSSセレクタを定数から参照
            )
            nhk_plus_url = span_element.get_attribute('href')
            return nhk_plus_url
        except (NoSuchElementException, TimeoutException):
            return None

    def _process_eyecatch_or_iframe(self, driver, program_title: str, episode_url: str, channel: str, episode_title: str, nhk_plus_url: str | None) -> str | None:
        """eyecatch画像またはiframeからURLを取得して整形する"""
        final_url = None
        try:
            final_url = self._process_eyecatch_image(driver, program_title, episode_url)
        except Exception as eyecatch_e:
            self.logger.debug(f"eyecatch画像処理失敗: {eyecatch_e} - {program_title}, {episode_url}") # debug レベルでログ出力
            try:
                final_url = self._process_iframe_url(driver, program_title, episode_url)
            except Exception as iframe_e:
                self.logger.error(f"eyecatch画像, iframe URL取得失敗: {program_title}, {episode_url} - eyecatch_e: {str(eyecatch_e)}, iframe_e: {str(iframe_e)}")
                return None # eyecatch, iframe どちらの処理も失敗

        # final_url が None でない場合のみ処理を続ける
        if final_url: # eyecatch または iframe からURLを取得できた場合
            program_time = utils.extract_program_time_info(driver, program_title, episode_url, channel) # ★修正: 関数名変更
            formatted_output = f"●{program_title}{program_time}\n"
            formatted_output += f"・{episode_title}\n"
            if nhk_plus_url:
                formatted_output += f"{nhk_plus_url}\n"
            else:
                formatted_output += f"{final_url}\n"
            self.logger.info(f"{program_title} の詳細情報を取得しました")
            return formatted_output
        return None # eyecatch, iframe どちらからもURLを取得できなかった場合

    def _process_eyecatch_image(self, driver, program_title: str, episode_url: str) -> str | None:
        """eyecatch画像からURLを取得する"""
        eyecatch_div = WebDriverWait(driver, utils.Constants.Time.DEFAULT_TIMEOUT).until(
            EC.presence_of_element_located((By.CLASS_NAME, Constants.CSSSelector.EYECATCH_IMAGE_DIV)) # ★修正: CSSセレクタを定数から参照
        )
        a_tag_element = eyecatch_div.find_element(By.TAG_NAME, Constants.CSSSelector.EPISODE_URL_TAG) # ★修正: CSSセレクタを定数から参照
        image_link = a_tag_element.get_attribute('href')
        driver.get(image_link)
        WebDriverWait(driver, utils.Constants.Time.DEFAULT_TIMEOUT).until(CustomExpectedConditions.page_is_ready())
        return driver.current_url

    def _process_iframe_url(self, driver, program_title: str, episode_url: str) -> str | None:
        """iframeからURLを取得する"""
        iframe = WebDriverWait(driver, utils.Constants.Time.DEFAULT_TIMEOUT).until(
            EC.presence_of_element_located((By.ID, Constants.CSSSelector.IFRAME_ID)) # ★修正: CSSセレクタを定数から参照, By.ID で検索
        ) # By.ID で検索
        iframe_src = iframe.get_attribute('src')
        match = re.search(r'/st/(.*?)\?', iframe_src)
        if match:
            extracted_id = match.group(1)
            final_url = f"https://plus.nhk.jp/watch/st/{extracted_id}"
            driver.get(final_url)
            WebDriverWait(driver, utils.Constants.Time.DEFAULT_TIMEOUT).until(CustomExpectedConditions.page_is_ready())
            self.logger.info(f"iframeからURLを生成しました: {final_url} - {program_title}")
            return final_url
        else:
            self.logger.error(f"iframeからIDを抽出できませんでした: {program_title}, {episode_url}")
            return None

    def _format_fallback_output(self, driver, program_title: str, episode_url: str, channel: str, episode_title: str) -> str:
        """eyecatch, iframe 処理失敗時のフォールバック出力"""
        program_time = utils.extract_program_time_info(driver, program_title, episode_url, channel) # ★修正: 関数名変更
        formatted_output = f"●{program_title}{program_time}\n"
        formatted_output += f"・{episode_title}\n"
        formatted_output += f"{episode_url}\n"
        return formatted_output

class TVTokyoScraper(BaseScraper):
    """テレビ東京の番組情報をスクレイピングするクラス"""

    def __init__(self, config):
        super().__init__(config)

    def get_program_info(self, program_name: str, target_date: str) -> str | None:
        """指定された番組の情報を取得する"""
        program_config = self.config.get(program_name)
        if not program_config:
            self.logger.warning(f"{program_name} の設定情報が見つかりません")
            return None

        with WebDriverManager() as driver:
            try:
                formatted_date = utils.format_date(target_date)
                weekday = datetime.strptime(target_date, '%Y%m%d').weekday()
                program_time = utils.format_program_time(program_config['name'], weekday, program_config['time'])
                self.logger.info(f"検索開始: {program_name}")

                if program_name == "WBS":
                    episode_urls = self._extract_tvtokyo_episode_urls(driver, program_config["urls"], formatted_date, program_name)
                else:
                    episode_urls = self._extract_tvtokyo_episode_urls(driver, [program_config["url"]], formatted_date, program_name)

                if not episode_urls:
                    self.logger.warning(f"{program_name} が見つかりませんでした")
                    return None

                episode_details = [
                    self._fetch_tvtokyo_episode_details(driver, url, program_name) for url in episode_urls
                ]

                # 結果の整形
                formatted_output = f"●{program_config['name']}{program_time}\n"
                for title, url in episode_details:
                    if title and url:
                        formatted_output += f"・{title}\n{url}\n"

                if formatted_output == f"●{program_config['name']}{program_time}\n":
                    return None

                self.logger.info(f"{program_name} の詳細情報を取得しました")
                return formatted_output

            except Exception as e:
                self.logger.error(f"番組情報取得中にエラー: {e} - {program_name}")
                return None

    def _extract_tvtokyo_episode_urls(self, driver, target_urls: list[str], formatted_date: str, program_name: str) -> list[str]:
        """
        テレビ東京のエピソードURLを抽出する。
        target_urls をリストとして受け取り、各URLに対して処理を行う。
        """
        all_urls = []
        for target_url in target_urls:
            try:
                driver.get(target_url)
                WebDriverWait(driver, utils.Constants.Time.DEFAULT_TIMEOUT).until(CustomExpectedConditions.page_is_ready())

                # 要素の存在確認（find_elements を使用）
                episode_elements = driver.find_elements(By.CSS_SELECTOR, 'div[id^="News_Detail__VideoItem__"]')
                if not episode_elements:
                    self.logger.warning(f"{program_name} のエピソード要素が見つかりませんでした - {target_url}")
                    continue  # 次のURLへ

                urls = []
                today = datetime.now().date()
                yesterday = today - timedelta(days=1)
                formatted_today = utils.format_date(today.strftime('%Y%m%d'))
                formatted_yesterday = utils.format_date(yesterday.strftime('%Y%m%d'))

                for episode in episode_elements:
                    try:
                        # 日付要素の存在確認
                        date_elements = episode.find_elements(By.CSS_SELECTOR, 'span.sc-c564813-0.iCkNIF[role="presentation"]')
                        if not date_elements:
                            self.logger.debug(f"日付要素が見つかりませんでした - {program_name} - {target_url}")
                            continue # 次のエピソードへ

                        date_element = date_elements[0]
                        date_text = date_element.text.strip()

                        if "今日" in date_text and formatted_today == formatted_date:
                            link = episode.find_element(By.CSS_SELECTOR, 'a[href*="post_"]').get_attribute("href")
                            urls.append(link)
                        elif "昨日" in date_text and formatted_yesterday == formatted_date:
                            link = episode.find_element(By.CSS_SELECTOR, 'a[href*="post_"]').get_attribute("href")
                            urls.append(link)
                        elif date_text == formatted_date:
                            link = episode.find_element(By.CSS_SELECTOR, 'a[href*="post_"]').get_attribute("href")
                            urls.append(link)

                    except (NoSuchElementException, StaleElementReferenceException) as e:
                        self.logger.error(f"エピソード解析中にエラー: {e} - {program_name} - {target_url}")
                        # 必要に応じてリトライ処理などを追加
                all_urls.extend(urls)
            except Exception as e:
                self.logger.error(f"URL取得エラー: {e} - {program_name} - {target_url}")
        self.logger.debug(f"テレビ東京のエピソードURLを抽出しました: {program_name} - {all_urls}")
        return all_urls

    def _fetch_tvtokyo_episode_details(self, driver, episode_url: str, program_name: str) -> tuple[str | None, str | None]:
        """テレビ東京のエピソード詳細情報を取得する"""
        try:
            driver.get(episode_url)
            WebDriverWait(driver, utils.Constants.Time.DEFAULT_TIMEOUT).until(CustomExpectedConditions.page_is_ready())
            title_element = WebDriverWait(driver, utils.Constants.Time.DEFAULT_TIMEOUT).until(
                EC.presence_of_element_located((By.ID, "Live_Episode_Detail_EpisodeItemFullTitle"))
            )
            title = title_element.text.strip()
            self.logger.debug(f"エピソード詳細情報を取得しました: {program_name} - {title}")
            return title, episode_url
        except Exception as e:
            self.logger.error(f"エピソード詳細取得エラー: {e} - {program_name}, {episode_url}")
            return None, None

def fetch_program_info(args: tuple[str, str, dict, str]) -> str | None:
    """並列処理用のラッパー関数"""
    task_type, program_name, programs, target_date = args
    logger = logging.getLogger(__name__)

    try:
        if task_type == 'nhk':
            scraper = NHKScraper(programs)
            result = scraper.get_program_info(program_name, target_date)
        elif task_type == 'tvtokyo':
            scraper = TVTokyoScraper(programs)
            result = scraper.get_program_info(program_name, target_date)
        else:
            logger.error(f"不明なタスクタイプです: {task_type}")
            return None

        if result:
            logger.info(f"{program_name} の情報を取得しました。")
        else:
            logger.warning(f"{program_name} の情報の取得に失敗しました。")
        return result

    except Exception as e:
        logger.error(f"{program_name} の情報取得中にエラーが発生しました: {e}")
        return None

def get_elapsed_time(start_time: float) -> float:
    """経過時間を計算する"""
    end_time = time.time()
    return end_time - start_time

def process_scraping(target_date: str, nhk_programs: dict, tvtokyo_programs: dict) -> list[tuple[str, str, dict, str]]:
    """スクレイピング処理を行う"""
    tasks = []
    for program_title in nhk_programs:
        tasks.append(('nhk', program_title, nhk_programs, target_date))

    for program_name in tvtokyo_programs:
        tasks.append(('tvtokyo', program_name, tvtokyo_programs, target_date))
    return tasks

def write_results_to_file(sorted_blocks: list[str], output_file_path: str, logger) -> None:
    """ソートされた結果をファイルに書き込む"""
    try:
        with open(output_file_path, "w", encoding="utf-8") as f:
            for i, block in enumerate(sorted_blocks):
                f.write(block + '\n' if i < len(sorted_blocks) - 1 else block)
        logger.info(f"ファイルへの書き込み完了: {output_file_path}")
    except Exception as e:
        logger.error(f"ファイルへの書き込みに失敗しました: {e}")
        raise

def main():
    """メイン関数"""
    if len(sys.argv) != 2:
        print("日付を引数で指定してください (例: python script.py 20250124)")
        sys.exit(1)

    target_date = sys.argv[1]
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    output_file_path = os.path.join(output_dir, f"{target_date}.txt")

    start_time = time.time()

    # ロガーをメインプロセスで初期化
    logger = setup_logger(__name__)

    try:
        nhk_programs = parse_programs_config('ini/nhk_config.ini')
        tvtokyo_programs = parse_programs_config('ini/tvtokyo_config.ini')

        tasks = process_scraping(target_date, nhk_programs, tvtokyo_programs)
        total_tasks = len(tasks)
        processed_tasks = 0
        results = []

        with multiprocessing.Pool() as pool:
            for result in pool.imap_unordered(fetch_program_info, tasks):
                if result:
                    results.append(result)
                processed_tasks += 1

                elapsed_time = get_elapsed_time(start_time)
                print(f"\r進捗: {processed_tasks}/{total_tasks}（経過時間：{get_elapsed_time(start_time):.0f}秒）", end="", flush=True)

        logger.info(f"【後処理開始】結果を番組ブロックごとに分割中...（経過時間：{get_elapsed_time(start_time):.0f}秒）")
        blocks = []
        current_block = []
        for line in results:
            if line.startswith('●'):
                if current_block:
                    blocks.append('\n'.join(current_block))
                    current_block = []
            current_block.append(line)
        if current_block:
            blocks.append('\n'.join(current_block))
        logger.info(f"番組ブロックの分割完了: {len(blocks)} ブロック作成（経過時間：{get_elapsed_time(start_time):.0f}秒）")

        logger.info(f"番組ブロックを時間順にソート中...（経過時間：{get_elapsed_time(start_time):.0f}秒）")
        sorted_blocks = sort_blocks_by_time(blocks)
        logger.info(f"番組ブロックのソート完了（経過時間：{get_elapsed_time(start_time):.0f}秒）")

        write_results_to_file(sorted_blocks, output_file_path, logger)

        print(f"結果を {output_file_path} に出力しました。（経過時間：{get_elapsed_time(start_time):.0f}秒）")

    except Exception as e:
        logger.error(f"メイン処理でエラーが発生しました: {e}")
        print(f"エラーが発生しました: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

```


get-tweet.py
```
import tweepy
import os
import time
from dotenv import load_dotenv
from datetime import datetime, timedelta
import sys
import re
import json
import unicodedata
import logging
from common.utils import to_jst_datetime, to_utc_isoformat, extract_time_info_from_text, setup_logger

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

def search_tweets(keyword, target_date, user=None, count=10):
    """
    Twitter API v2を使ってツイートを検索し、整形前のツイートデータを返します。
    """

    if USE_API: # API を使用する場合
        try:
            client = tweepy.Client(bearer_token=BEARER_TOKEN)

            # OR検索のクエリを作成
            query = f"from:{user} ({keyword})"

            # 検索対象日を放送日の前日に設定
            jst_datetime_target = to_jst_datetime(target_date) - timedelta(days=1)
            print(f"検索対象日: {jst_datetime_target}")

            # 日本時間の日付と時刻を作成 (検索期間は前日の00:00:00 から 23:59:59)
            #                                        ↑前日に Tweet されているため
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
                print("\n待機完了。リトライ...")  # 改行を追加

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
            },
            {
                "created_at": "2024-02-24 10:03:30+00:00",
                "text": "NHK 総合 25日(火) 午後11:35\\nアナザーストーリーズ「“怪物”に出会った日～井上尚弥×ノニト・ドネア～」\\nhttps://t.co/xxxxxxxxxxx",
                "author_id": 3022192682
            }

        ]
        """
        return json.loads(dummy_json_data) # JSONをパースしたPythonオブジェクトを返す

def format_program_info(text, time_info):
    """番組情報をフォーマットする # ★追加: 番組情報フォーマット関数"""
    program_info = "番組情報の抽出に失敗" # デフォルト値

    # 番組情報のフォーマット（全角・半角両対応）
    if "ＢＳ世界のドキュメンタリー" in text:
        program_info = f"●BS世界のドキュメンタリー(NHK BS {time_info}-)"
    elif "アナザーストーリーズ" in text:
        program_info = f"●アナザーストーリーズ(NHK BS {time_info}-)"
    elif re.search(r'Asia Insight|Ａｓｉａ　Ｉｎｓｉｇｈｔ', text):  # 全角・半角両対応
        program_info = f"●Asia Insight(NHK BS {time_info}-)"
    elif "英雄たちの選択" in text:
        program_info = f"●英雄たちの選択(NHK BS {time_info}-)"
    return program_info

def cleanup_content(text, content):
    """不要な文字列を削除する # ★追加: 不要文字列削除関数"""
    # ＢＳ世界のドキュメンタリーの場合
    if "ＢＳ世界のドキュメンタリー" in text:
        content = re.sub(r'ＢＳ世界のドキュメンタリー[▽　選「]*', '', content).strip()
        content = re.sub(r'」$', '', content).strip()
    # アナザーストーリーズの場合
    elif "アナザーストーリーズ" in text:
        content = re.sub(r'アナザーストーリーズ[▽　選「]*', '', content).strip()
        content = re.sub(r'」$', '', content).strip()
    return content

def format_tweet_data(tweet_data):
    """
    ツイートデータを受け取り、指定されたフォーマットで整形されたテキストを返します。
    """
    formatted_results = ""
    logger = setup_logger(__name__) # logger を設定
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
            # 放送局と日付の基本部分を確認
            if len(parts) > 3 and parts[0] == "NHK" and parts[1] == "BS":
                time_info = extract_time_info_from_text(first_line) # utils.py の共通関数を使用
                program_info = format_program_info(text, time_info) # 関数化

        #不要な文字列を削除（全角・半角両対応）
        content = ""
        if len(lines) > 1:
            content = lines[1]
            content = cleanup_content(text, content) # 関数化

        # URLの抽出 (最終行にあると仮定)
        if len(lines) > 0:
            last_line = lines[-1]
            if last_line.startswith("https://"):
                url = last_line
            else:
                url = "URLの抽出に失敗"

        formatted_text = f"{program_info}\n・{content}\n{url}\n\n"
        formatted_results += formatted_text

    return formatted_results

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("使用方法: python get-tweet.py YYYYMMDD")
        exit()
    target_date = sys.argv[1]

    # OR検索用のキーワードをカッコで囲み、| で区切る  全角半角両対応
    keyword = "アナザーストーリーズ OR ＢＳ世界のドキュメンタリー OR Asia Insight OR Ａｓｉａ　Ｉｎｓｉｇｈｔ OR 英雄たちの選択"
    user = "nhk_docudocu"
    count = 10

    tweets = search_tweets(keyword, target_date, user, count) # APIリクエスト or ダミーデータ取得

    if tweets:
        formatted_text = format_tweet_data(tweets)
        # ファイル名を作成
        now = datetime.now()
        filename = f"output/{target_date}_tweet.txt"  # ファイル名を変更

        # outputディレクトリが存在しなければ作成
        if not os.path.exists("output"):
            os.makedirs("output")

        # テキストファイルに書き出し
        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(formatted_text)
            print(f"テキストファイルを {filename} に出力しました。")
        except Exception as e:
            print(f"ファイル書き込みエラー: {e}")

```


get-tweet.py
```
import tweepy
import os
import time
from dotenv import load_dotenv
from datetime import datetime, timedelta
import sys
import re
import json
import unicodedata
from common.utils import to_jst_datetime, to_utc_isoformat

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

def search_tweets(keyword, target_date, user=None, count=10):
    """
    Twitter API v2を使ってツイートを検索し、整形前のツイートデータを返します。
    """

    if USE_API: # API を使用する場合
        try:
            client = tweepy.Client(bearer_token=BEARER_TOKEN)

            # OR検索のクエリを作成
            query = f"from:{user} ({keyword})"

            # 検索対象日を放送日の前日に設定
            jst_datetime_target = to_jst_datetime(target_date) - timedelta(days=1)
            print(f"検索対象日: {jst_datetime_target}")

            # 日本時間の日付と時刻を作成 (検索期間は前日の00:00:00 から 23:59:59)
            #                                        ↑前日に Tweet されているため
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
                print("\n待機完了。リトライ...")  # 改行を追加

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
            },
            {
                "created_at": "2024-02-24 10:03:30+00:00",
                "text": "NHK 総合 25日(火) 午後11:35\\nアナザーストーリーズ「“怪物”に出会った日～井上尚弥×ノニト・ドネア～」\\nhttps://t.co/xxxxxxxxxxx",
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

            # 放送局と日付の基本部分を確認
            if len(parts) > 3 and parts[0] == "NHK" and parts[1] == "BS":
                try:
                    time_str = parts[3]  # 時刻情報だけ取得
                    date_str = parts[2]  # 日付部分を取得

                    if re.search(r"\(.+深夜\)", first_line):
                        add_24_hour = True
                        print(f"デバッグ: (深夜)表記を検出(正規表現)。add_24_hour = {add_24_hour}")
                    else:
                        print(f"デバッグ: (深夜)表記を検出されず(正規表現)。add_24_hour = {add_24_hour}")

                    # 午前/午後を判定
                    if "午後" in time_str:
                        ampm = "午後"
                    elif "午前" in time_str:
                        ampm = "午前"
                    else:
                        ampm = None

                    time_parts = re.findall(r'\d+', time_str)
                    if len(time_parts) == 2:
                        hour = int(time_parts[0])
                        minute = int(time_parts[1])
                        print(f"デバッグ: 抽出された時刻 hour = {hour}, minute = {minute}, ampm = {ampm}")

                        if add_24_hour:
                            hour += 24
                            print(f"デバッグ: 24時間加算実行。hour = {hour}")

                        if ampm == "午後" and hour < 24:  # 12時間制の調整
                            hour += 12
                        elif ampm == "午前" and hour == 12:
                            hour = 0

                        if add_24_hour:
                            time_info = f"{hour:02d}:{minute:02d}"
                        else:
                            time_info = f"{hour:02}:{minute:02}"
                        print(f"デバッグ: time_info = {time_info}")
                    else:
                        time_info = "時刻情報の抽出に失敗"
                except ValueError as e:
                    time_info = "時刻情報の抽出に失敗"

                # 番組情報のフォーマット（全角・半角両対応）
                if "ＢＳ世界のドキュメンタリー" in text:
                    program_info = f"●BS世界のドキュメンタリー(NHK BS {time_info}-)"
                elif "アナザーストーリーズ" in text:
                    program_info = f"●アナザーストーリーズ(NHK BS {time_info}-)"
                elif re.search(r'Asia Insight|Ａｓｉａ　Ｉｎｓｉｇｈｔ', text):  # 全角・半角両対応
                    program_info = f"●Asia Insight(NHK BS {time_info}-)"
                elif "英雄たちの選択" in text:
                    program_info = f"●英雄たちの選択(NHK BS {time_info}-)"
                else:
                    program_info = "番組情報の抽出に失敗"

        #不要な文字列を削除（全角・半角両対応）
        content = ""
        if len(lines) > 1:
            content = lines[1]

            # ＢＳ世界のドキュメンタリーの場合
            if "ＢＳ世界のドキュメンタリー" in text:
                content = re.sub(r'ＢＳ世界のドキュメンタリー[▽　選「]*', '', content).strip()
                content = re.sub(r'」$', '', content).strip()

            # アナザーストーリーズの場合
            elif "アナザーストーリーズ" in text:
                content = re.sub(r'アナザーストーリーズ[▽　選「]*', '', content).strip()
                content = re.sub(r'」$', '', content).strip()

            # Ａｓｉａ　Ｉｎｓｉｇｈｔの場合（全角・半角両対応）
            elif re.search(r'Asia Insight|Ａｓｉａ　Ｉｎｓｉｇｈｔ', text):
                content = re.sub(r'(Asia Insight|Ａｓｉａ　Ｉｎｓｉｇｈｔ)[▽　選「]*', '', content).strip() #全角半角対応

            # 英雄たちの選択 の場合
            elif "英雄たちの選択" in text:
                content = re.sub(r'英雄たちの選択[▽　選「]*', '', content).strip()

        # URLの抽出 (最終行にあると仮定)
        if len(lines) > 0:
            last_line = lines[-1]
            if last_line.startswith("https://"):
                url = last_line
            else:
                url = "URLの抽出に失敗"

        formatted_text = f"{program_info}\n・{content}\n{url}\n\n"
        formatted_results += formatted_text

    return formatted_results

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("使用方法: python get-tweet.py YYYYMMDD")
        exit()
    target_date = sys.argv[1]

    # OR検索用のキーワードをカッコで囲み、| で区切る  全角半角両対応
    keyword = "アナザーストーリーズ OR ＢＳ世界のドキュメンタリー OR Asia Insight OR Ａｓｉａ　Ｉｎｓｉｇｈｔ OR 英雄たちの選択"
    user = "nhk_docudocu"
    count = 10

    tweets = search_tweets(keyword, target_date, user, count) # APIリクエスト or ダミーデータ取得

    if tweets:
        formatted_text = format_tweet_data(tweets)
        # ファイル名を作成
        now = datetime.now()
        filename = f"output/{target_date}_tweet.txt"  # ファイル名を変更

        # outputディレクトリが存在しなければ作成
        if not os.path.exists("output"):
            os.makedirs("output")

        # テキストファイルに書き出し
        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(formatted_text)
            print(f"テキストファイルを {filename} に出力しました。")

        except Exception as e:
            print(f"ファイル書き込みエラー: {e}")
    else:
        print("ツイートの検索に失敗しました。")
```


merge-text.py
```
import os
import sys
import re
from datetime import datetime
from common.utils import setup_logger, sort_blocks_by_time

def extract_time_from_line(line: str) -> tuple[int, int] | None:
    """
    行から放送開始時間を抽出する。
    '●' で始まり、時刻情報（例：'05:45'）を含む行を対象とする。
    """
    if line.startswith('●'):
        time_match = re.search(r'(\d{2}:\d{2})', line)
        if time_match:
            time_str = time_match.group(1)
            hour, minute = map(int, time_str.split(':'))
            return hour, minute
    return None

def sort_and_merge_text(file1_path: str, file2_path: str, output_path: str, before_merge_path: str) -> None:
    """
    2つのテキストファイルを読み込み、時間でソートしてマージする。
    元のファイルをリネームしてから、マージ結果を出力する。
    file1_path が存在しない場合は file2_path のみを処理する。
    """
    logger = setup_logger(__name__)

    # file2_path (YYYYMMDD.txt) は必須
    if not os.path.exists(file2_path):
        logger.error(f"必須ファイル {file2_path} が見つかりません。")
        raise FileNotFoundError(f"必須ファイル {file2_path} が見つかりません。")

    # 元のファイル (file2_path) をリネーム (バックアップ)
    try:
        os.rename(file2_path, before_merge_path)
        logger.info(f"{file2_path} を {before_merge_path} にリネームしました。")
    except Exception as e:
        logger.error(f"{file2_path} のリネーム中にエラーが発生しました: {e}")
        raise


    # ファイルの存在確認と読み込み
    combined_lines = []

    try:
        with open(before_merge_path, 'r', encoding='utf-8') as f: #リネーム後のファイルを読む
            combined_lines = f.readlines() # 一旦リストに読み込む
        logger.info(f"{before_merge_path} を読み込みました。")

        # combined_lines の末尾が改行で終わっていない場合に改行を追加
        if combined_lines and not combined_lines[-1].endswith('\n'):
            combined_lines[-1] = combined_lines[-1] + '\n'  # 既存の最後の要素に改行を追加

    except Exception as e:
        logger.error(f"{before_merge_path} の読み込み中にエラーが発生しました: {e}")
        raise

    # file1_path (YYYYMMDD_tweet.txt) は任意
    if os.path.exists(file1_path):
        try:
            with open(file1_path, 'r', encoding='utf-8') as f:
                file1_lines = f.readlines() # file1_pathも一旦リストとして読み込む

            # file1_linesの先頭が改行で始まっていない場合、かつcombined_linesが空でない場合に改行を追加
            if file1_lines and not file1_lines[0].startswith('\n') and combined_lines:
                combined_lines.append('\n')

            combined_lines.extend(file1_lines) # extendで結合
            logger.info(f"{file1_path} を読み込みました。")
        except Exception as e:
            logger.error(f"{file1_path} の読み込み中にエラーが発生しました: {e}")
            raise  # file1_path が存在しても読み込みエラーなら停止

    # combined_lines をブロックごとに分割
    blocks = []
    current_block = []
    for line in combined_lines:
        if line.startswith('●'):
            if current_block:
                blocks.append(''.join(current_block))
            current_block = [line]
        else:
            current_block.append(line)
    if current_block:
        blocks.append(''.join(current_block))

    # ブロックをソート
    sorted_blocks = sort_blocks_by_time(blocks)

    # マージされたテキストを作成（ブロックの末尾が改行でなければ改行を追加）
    merged_text = ""
    for block in sorted_blocks:
        merged_text += block
        if not block.endswith('\n'):  # ブロックの末尾が改行でなければ
            merged_text += '\n'       # 改行を追加

    # マージされたテキストを指定されたパスに出力（最後に改行を1つ追加）
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(merged_text)
        logger.info(f"マージされたテキストを {output_path} に出力しました。")
    except Exception as e:
        logger.error(f"{output_path} への書き込み中にエラーが発生しました: {e}")
        raise

def main():
    """
    メイン関数。
    """
    if len(sys.argv) != 2:
        print("使用法: python merge-text.py YYYYMMDD")
        sys.exit(1)

    target_date = sys.argv[1]
    if not re.match(r'^\d{8}$', target_date):
        print("日付はYYYYMMDD形式で指定してください。")
        sys.exit(1)
    try:
        datetime.strptime(target_date, '%Y%m%d')
    except ValueError:
        print("無効な日付形式です。YYYYMMDD形式で指定してください。")
        sys.exit(1)

    base_dir = 'output'
    file1_path = os.path.join(base_dir, f"{target_date}_tweet.txt")  # 任意
    file2_path = os.path.join(base_dir, f"{target_date}.txt")      # 必須
    output_path = os.path.join(base_dir, f"{target_date}.txt")      # 上書き
    before_merge_path = os.path.join(base_dir, f"{target_date}_before-merge.txt") # リネーム後

    sort_and_merge_text(file1_path, file2_path, output_path, before_merge_path)

if __name__ == "__main__":
    main()

```


open-url.py
```
import os
import webbrowser
import re
import sys
import time
from common.utils import load_config, setup_logger, parse_programs_config, Constants

logger = setup_logger(__name__)

def extract_urls_from_file(file_path: str) -> list[str]:
    """テキストファイルからURLを抽出する"""
    urls = []
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            for line in file:
                url_match = re.search(r'https?://[^\s]+', line)
                if url_match:
                    urls.append(url_match.group(0))
                    logger.debug(f"URLを抽出しました: {url_match.group(0)}")
        logger.info(f"ファイル {file_path} からURLを抽出しました。")
    except FileNotFoundError:
        logger.error(f"ファイル {file_path} が見つかりませんでした。")
        raise
    except Exception as e:
        logger.error(f"ファイル {file_path} からのURL抽出中にエラーが発生しました: {e}")
        raise
    return urls

def open_urls_from_config(config_programs: dict, program_name: str, block_urls: list[str]) -> bool:
    """設定ファイルのURL (一覧) とブロック内のURL (詳細) を開く
       戻り値:  True: 正常に処理 (番組が存在), False: 番組が設定に存在しない
    """

    if program_name not in config_programs:
        logger.warning(f"設定ファイルに {program_name} のURLが見つかりませんでした")
        return False

    program_config = config_programs[program_name]
    list_page_url = None

    # WBS の場合は urls キーから最初の URL を取得、それ以外は url キーから取得
    if isinstance(program_config, dict):
        if program_name == Constants.Program.WBS_PROGRAM_NAME and 'urls' in program_config:
            list_page_url = program_config['urls'][0]  # 最初の URL (通常は feature)
            # 詳細ページに trend_tamago が含まれていたら、一覧ページも trend_tamago にする
            for detail_url in block_urls:
                if "trend_tamago" in detail_url:
                    list_page_url = program_config['urls'][1]  # 2番目の URL (trend_tamago)
                    break  # 一つ見つかったらループを抜ける
        elif 'url' in program_config:
            list_page_url = program_config['url']

    if not list_page_url:
        logger.error(f"{program_name} の一覧ページURLが設定されていません。")
        return False

    # 一覧ページを開く (WBS でも最初に一覧ページを開く)
    logger.info(f"{program_name} の一覧ページ: {list_page_url} を開きます")
    webbrowser.open(list_page_url)

    # WBSの特殊処理 (詳細ページを開く)
    if program_name == Constants.Program.WBS_PROGRAM_NAME:
        for detail_url in block_urls:
            if "feature" in detail_url or "trend_tamago" in detail_url:
                logger.info(f"{detail_url} を開きます")
                webbrowser.open(detail_url)
                time.sleep(Constants.Time.SLEEP_SECONDS)
        return True

    # 詳細ページを開く
    for detail_url in block_urls:
        logger.info(f"{program_name} の詳細ページ: {detail_url} を開きます")
        webbrowser.open(detail_url)

    return True

def process_program_block(block: str, nhk_programs: dict, tvtokyo_programs: dict) -> None:
    """番組ブロックを処理する"""
    lines = block.strip().split('\n')
    if not lines:
        return

    program_info = lines[0].strip()
    program_name = program_info.split("(")[0].strip()  # 番組名

    block_urls = []
    for line in lines:
        url_match = re.search(r'https?://[^\s]+', line)
        if url_match:
            block_urls.append(url_match.group(0))

    processed = False
    if program_name in nhk_programs:
        processed = open_urls_from_config(nhk_programs, program_name, block_urls)
    elif program_name in tvtokyo_programs:
        processed = open_urls_from_config(tvtokyo_programs, program_name, block_urls)
    else:
        logger.warning(f"番組 {program_name} は設定ファイルに存在しません")
        # 設定ファイルに存在しない場合、block_urls が空でない場合にのみURLを開く
        if block_urls:
            logger.info(f"出力ファイルのURL ({program_name}):")
            for url in block_urls:
                logger.info(f"{url} を開きます")
                webbrowser.open(url)
            processed = True

    if processed:
        time.sleep(Constants.Time.SLEEP_SECONDS)

def main():
    """メイン関数"""
    if len(sys.argv) != 2:
        print("日付を引数で指定してください (例: python script.py 20250124)")
        sys.exit(1)

    date_input = sys.argv[1]
    output_dir = 'output'
    output_file_path = os.path.join(output_dir, f"{date_input}.txt")

    nhk_config_path = 'ini/nhk_config.ini'
    tvtokyo_config_path = 'ini/tvtokyo_config.ini'

    try:
        nhk_programs = parse_programs_config(nhk_config_path)
        tvtokyo_programs = parse_programs_config(tvtokyo_config_path)
    except Exception as e:
        logger.error(f"設定ファイルの読み込みに失敗しました: {e}")
        sys.exit(1)

    try:
        with open(output_file_path, 'r', encoding='utf-8') as file:
            content = file.read()
    except FileNotFoundError:
        print(f"エラー: 指定された出力ファイル {output_file_path} は存在しません。")
        sys.exit(1)
    except Exception as e:
        logger.error(f"出力ファイル {output_file_path} の読み込みに失敗しました: {e}")
        sys.exit(1)

    program_blocks = content.split("●")[1:]

    for block in program_blocks:
        process_program_block(block, nhk_programs, tvtokyo_programs)

if __name__ == "__main__":
    main()

```


split-text.py
```
import sys
import os
import re
from common.constants import (
    TWEET_MAX_LENGTH,
    get_header_text,
    get_header_length
)
from common.utils import count_tweet_length

# コマンドライン引数から日付を取得
if len(sys.argv) < 2:
    print("使用方法: python split-text.py <日付 (例: 20250129)>")
    sys.exit(1)

date = sys.argv[1]
file_path = f"output/{date}.txt"
backup_file_path = f"output/{date}_before-split.txt"

# 指定された日付のファイルを読み込む
try:
    with open(file_path, "r", encoding="utf-8") as file:
        text = file.read().strip()  # ファイル全体を文字列として読み込む
except FileNotFoundError:
    print(f"エラー: {file_path} が見つかりません。")
    sys.exit(1)

def split_program(text, max_length=TWEET_MAX_LENGTH, header_length=0):
    """
    番組テキストを指定された文字数制限内で分割する関数（ヘッダーなし）。

    Args:
        text (str): 分割対象の番組テキスト（番組名、タイトル、URLを含む）。
        max_length (int): 文字数制限。

    Returns:
        list: 分割されたテキストのリスト。
    """
    split_tweets = []
    lines = text.split('\n')

    program_name = ""  # 現在処理中の番組名
    current_tweet = ""  # 現在作成中のツイート
    is_first_program = True  # 最初のプログラムかどうかを判定するフラグ

    i = 0
    while i < len(lines):
        if lines[i].startswith("●"):
            program_name = lines[i]  # 現在の番組名を設定

            # 新しい番組なのでcurrent_tweetをリセット
            if current_tweet:
                split_tweets.append(current_tweet)
            current_tweet = ""
            i += 1

        elif i < len(lines) and lines[i].startswith("・"):
            title = lines[i]
            i += 1
            url = lines[i] if i < len(lines) else ""
            combined = f"{title}\n{url}"

            # 番組名を追加
            if not current_tweet:
                current_tweet = program_name + '\n'

            # 最初のプログラムの最初のツイートのみ、ヘッダー長を考慮
            if is_first_program and not split_tweets:
                if count_tweet_length(current_tweet + combined) <= max_length - header_length:
                    current_tweet += combined + "\n"
                    i += 1
                else:
                    split_tweets.append(current_tweet)
                    current_tweet = combined + "\n"
                    i += 1
            else:
                if count_tweet_length(current_tweet + combined) <= max_length:
                    current_tweet += combined + "\n"
                    i += 1
                else:
                    split_tweets.append(current_tweet)
                    current_tweet = combined + "\n"
                    i += 1

        elif not lines[i].strip():
            # 空行は無視するが、current_tweetが空でない場合は追加
            if current_tweet:
                split_tweets.append(current_tweet)
            current_tweet = ""  # リセット
            i += 1
        else:
            i += 1

    # 最後の処理
    if current_tweet:
        split_tweets.append(current_tweet)

    is_first_program = False
    return split_tweets

# プログラム（ブロック）ごとにテキストを分割する関数
def split_by_program(text):
    programs = re.split(r'(^●.*?\n)', text, flags=re.MULTILINE)
    # 空文字列を削除
    programs = [p for p in programs if p]
    # プログラム名と内容を組み合わせる
    program_list = []
    for i in range(0, len(programs), 2):
        if i + 1 < len(programs):
            program_list.append(programs[i].strip() + '\n' + programs[i+1].strip() + '\n')  # 前後の空白を削除して改行を挟む
        else:
            program_list.append(programs[i].strip())
    return program_list

# テキストをプログラムごとに分割
programs = split_by_program(text)

# 分割が必要なプログラムがあるかどうかを判定
needs_split = False

# 分割前の文字数と内容を出力
print("\n")
print("============================== 分割前のテキスト ==============================")
for i, program in enumerate(programs):
    length = count_tweet_length(program)
    print(program)
    print(f"文字数: {length}")
    print("-" * 20)

    # 最初のブロックの場合はヘッダーを考慮して判定
    header_length = get_header_length(date)  # ヘッダーの長さを計算
    if i == 0:
        if length + header_length > TWEET_MAX_LENGTH:
            needs_split = True
            break
    elif length > TWEET_MAX_LENGTH:  # 2番目以降のブロックは TWEET_MAX_LENGTH で判定
        needs_split = True
        break

if needs_split:
    # (ファイルバックアップ、分割、ファイル書き込み処理は変更なし)
    # ファイルバックアップ
    try:
        os.rename(file_path, backup_file_path)
        print(f"ファイルを {backup_file_path} にバックアップしました。")
    except FileNotFoundError:
        print(f"バックアップ元ファイル {file_path} が見つかりませんでした。処理を中断します。")
        sys.exit(1)
    except Exception as e:
        print(f"バックアップ処理中にエラーが発生しました: {e}")
        sys.exit(1)

    # 分割されたプログラムを格納するリスト
    new_programs = []
    header_length = get_header_length(date)
    for program in programs:
        if i == 0:  # 最初のブロック
            if count_tweet_length(program)  > TWEET_MAX_LENGTH - header_length:
                split_tweets = split_program(program, header_length=header_length)
                new_programs.extend(split_tweets)
            else:
                new_programs.append(program) # 分割不要
        else:  # 2番目以降のブロック
            if count_tweet_length(program) > TWEET_MAX_LENGTH:
                split_tweets = split_program(program)  # header_length は不要
                new_programs.extend(split_tweets)
            else:
                new_programs.append(program)  # 分割不要

    # 分割されたテキストをファイルに書き込む
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            for i, item in enumerate(new_programs):
                f.write(item)
                if i < len(new_programs) - 1:  # 最後の要素以外に改行を挿入
                    f.write("\n")  # 分割単位の間に空行を挿入

        print(f"分割されたツイートは {file_path} に保存しました。")

    except Exception as e:
        print(f"分割されたツイートの保存中にエラーが発生しました: {e}")

        # バックアップファイルを元に戻す
        try:
            os.rename(backup_file_path, file_path)
            print(f"バックアップファイル {backup_file_path} を {file_path} に復元しました。")
        except Exception as e:
            print(f"バックアップファイルの復元中にエラーが発生しました: {e}")
        sys.exit(1)

    # 分割後の文字数と内容を出力
    print("\n")
    print("============================== 分割後のテキスト ==============================")
    for item in new_programs:
        length = count_tweet_length(item)
        print(item)
        print(f"文字数: {length}")
        print("-" * 60)

else:
    # 分割が必要ない場合
    print("分割は不要でした。ファイルは変更されません。")

print("処理完了")

```

tweet.py
```
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

```


base_scraper.py
```
from abc import ABC, abstractmethod
import logging
from common.utils import WebDriverManager

class BaseScraper(ABC):
    """スクレイパーの抽象基底クラス"""

    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.driver = None

    @abstractmethod
    def get_program_info(self, program_name: str, target_date: str) -> str | None:
        """指定された番組の情報を取得する"""
        pass

```


constants.py
```
from datetime import datetime
from common.utils import count_characters  # 文字カウント関数をインポート

# Twitterの文字数制限 (本来は280文字だが、少なめに-10にして設定)
TWEET_MAX_LENGTH = 270

# ヘッダーテキストのフォーマット文字列
HEADER_TEXT_FORMAT = "{date}({weekday})のニュース・ドキュメンタリー番組など\n\n"

def get_header_text(date_str: str) -> str:
    """日付文字列からヘッダーテキストを生成する"""
    try:
        target_date_dt = datetime.strptime(date_str, '%Y%m%d')
        formatted_date = target_date_dt.strftime('%y/%m/%d')
        weekdays = ["月", "火", "水", "木", "金", "土", "日"]
        japanese_weekday = weekdays[target_date_dt.weekday()]
        header_text = HEADER_TEXT_FORMAT.format(date=formatted_date, weekday=japanese_weekday)
        return header_text
    except ValueError:
        return ""  # エラー時は空文字列

def get_header_length(date_str: str) -> int:
    """日付文字列からヘッダーテキストの長さを計算する"""
    header_text = get_header_text(date_str)
    return count_characters(header_text)  # 文字カウント関数を使用

```


utils.py
```
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import logging
import configparser
import re
import time
from datetime import datetime
import pytz
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

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
        DEFAULT_TIMEOUT = 10 # デフォルトのタイムアウト時間

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

    class CSSSelector: # ★追加: CSSセレクタを定義
        """CSSセレクタを定義するクラス"""
        EPISODE_INFO = 'gc-stream-panel-info'
        DATE_YEAR = 'gc-atom-text-for-date-year'
        DATE_DAY = 'gc-atom-text-for-date-day'
        DATE_TEXT_NO_YEAR = 'gc-stream-panel-info-title'
        EPISODE_URL_TAG = 'a'
        TITLE = 'title'
        NHK_PLUS_URL_SPAN = '//div[@class="detailed-memo-body"]/span[contains(@class, "detailed-memo-headline")]/a[contains(text(), "NHKプラス配信はこちらからご覧ください")]'
        EYECATCH_IMAGE_DIV = 'gc-images.is-medium.eyecatch'
        IFRAME_ID = 'eyecatchIframe'
        STREAM_PANEL_INFO_META = "stream_panel--info--meta" # utils.py でも使用

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s') # ★修正: basicConfigで共通設定

def setup_logger(name: str = __name__) -> logging.Logger:
    """ロガーを設定する"""
    logger = logging.getLogger(name)
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

def extract_program_time_info(driver: webdriver.Chrome, program_title: str, episode_url: str, channel: str, max_retries: int = 3, retry_interval: int = 1) -> str:
    """番組詳細ページから放送時間を抽出し、フォーマットする # ★修正: 関数名変更, 処理を共通化"""
    logger = setup_logger(__name__)  # ロガーをセットアップ

    if program_title == "国際報道 2025":
        return f"({channel} 22:00-22:45)"

    for retry in range(max_retries):
        try:
            time_element_text = WebDriverWait(driver, Constants.Time.DEFAULT_TIMEOUT).until(
                EC.presence_of_element_located((By.CLASS_NAME, Constants.CSSSelector.STREAM_PANEL_INFO_META)) # ★修正: CSSセレクタを定数から参照
            ).text.strip()
            start_ampm, start_time, end_ampm, end_time = _extract_time_parts(time_element_text) # ★修正: 内部関数名変更
            if start_time and end_time:
                start_time_24h = _to_24h_format(start_ampm, start_time) # ★修正: 内部関数名変更
                end_time_24h = _to_24h_format(end_ampm, end_time) # ★修正: 内部関数名変更
                return f"({channel} {start_time_24h}-{end_time_24h})"
            else:
                logger.warning(f"時間の取得に失敗しました。取得した文字列: {time_element_text} - {program_title}, {episode_url}")
                return "（放送時間取得失敗）"
        except (TimeoutException, NoSuchElementException) as e:
            logger.warning(f"要素が見つかりませんでした (リトライ {retry+1}/{max_retries}): {e} - {program_title}, {episode_url}")
            if retry < max_retries - 1: time.sleep(retry_interval)
        except Exception as e:
            logger.error(f"放送時間情報の抽出に失敗しました: {e} - {program_title}, {episode_url}")

    logger.error(f"最大リトライ回数を超えました: {program_title}, {episode_url}") # 共通のエラーメッセージ
    return "（放送時間取得失敗）"

def _extract_time_parts(time_text: str) -> tuple[str | None, str | None, str | None, str | None]: # ★修正: 関数名変更
    """時刻情報を含む文字列から、午前/午後、時刻を抽出する # ★修正: 関数名変更"""
    match = re.search(r'((午前|午後)?(\d{1,2}:\d{2}))-((午前|午後)?(\d{1,2}:\d{2}))', time_text)
    if not match: return None, None, None, None
    return match.group(2), match.group(3), match.group(5), match.group(6)

def _to_24h_format(ampm: str | None, time_str: str) -> str: # ★修正: 関数名変更
    """時刻を24時間表記に変換する # ★修正: 関数名変更"""
    hour, minute = map(int, time_str.split(":"))
    if ampm == "午後" and hour != 12:
        hour += 12
    if ampm == "午前" and hour == 12:
        hour = 0
    return f"{hour:02}:{minute:02}"

def format_program_time(program_name: str, weekday: int, default_time: str) -> str:
    """番組時間をフォーマットする"""
    if program_name.startswith("WBS"):
        return "(テレ東 22:00~22:58)" if weekday < 4 else "(テレ東 23:00~23:58)"
    return f"(テレ東 {default_time})"

def extract_time_info_from_text(text: str) -> str:
    """ツイートテキストから時刻情報を抽出・整形する # ★追加: get-tweet.py 用の時刻情報抽出関数"""
    time_info = "時刻情報の抽出に失敗" # デフォルト値
    add_24_hour = False # フラグを追加
    logger = setup_logger(__name__) # logger を設定

    if re.search(r"\(.+深夜\)", text): # (深夜)表記を検出
        add_24_hour = True
        logger.debug(f"デバッグ: (深夜)表記を検出(正規表現)。add_24_hour = {add_24_hour}")
    else:
        logger.debug(f"デバッグ: (深夜)表記を検出されず(正規表現)。add_24_hour = {add_24_hour}")

    time_match = re.search(r'(\d{1,2})日\((.)\) (午前|午後)(\d{1,2}):(\d{2})', text) # 正規表現で時刻を抽出
    if time_match:
        hour = int(time_match.group(4))
        minute = int(time_match.group(5))
        ampm = time_match.group(3)
        logger.debug(f"デバッグ: 抽出された時刻 hour = {hour}, minute = {minute}, ampm = {ampm}")

        if add_24_hour:
            hour += 24
            logger.debug(f"デバッグ: 24時間加算実行。hour = {hour}")

        if ampm == "午後" and hour < 12:  # 12時間制の調整
            hour += 12
        elif ampm == "午前" and hour == 12:
            hour = 0

        if add_24_hour: # 24時間表記
            time_info = f"{hour:02d}:{minute:02d}"
        else:
            time_info = f"{hour:02}:{minute:02}"
        logger.debug(f"デバッグ: time_info = {time_info}")
    else:
        logger.warning(f"時刻情報の抽出に失敗しました: text = {text}") # 警告ログ
    return time_info

```

CustomExpectedConditions.py
```
from selenium.webdriver.remote.webdriver import WebDriver

class CustomExpectedConditions:
    """Seleniumのカスタム条件"""
    @staticmethod
    def page_is_ready():
        """ページが完全に読み込まれたことを確認する"""
        return lambda driver: driver.execute_script("return document.readyState") == "complete"

```

nhk_config.ini
```
[program_1]
name = 国際報道 2025
url = https://www.nhk.jp/p/kokusaihoudou/ts/8M689W8RVX/list/
channel = NHK BS

[program_2]
name = キャッチ!世界のトップニュース
url = https://www.nhk.jp/p/catchsekai/ts/KQ2GPZPJWM/list/
channel = NHK総合

[program_3]
name = みみより!解説
url = https://www.nhk.jp/p/ts/X67KZLM3P6/list/
channel = NHK総合

[program_4]
name = 視点・論点
url = https://www.nhk.jp/p/ts/Y5P47Z7YVW/list/
channel = NHK Eテレ

[program_5]
name = 所さん!事件ですよ
url = https://www.nhk.jp/p/jikentokoro/ts/G69KQR33PG/list/
channel = NHK総合

[program_6]
name = クローズアップ現代
url = https://www.nhk.jp/p/gendai/ts/R7Y6NGLJ6G/list/
channel = NHK総合

[program_7]
name = 新プロジェクトX
url = https://www.nhk.jp/p/ts/P1124VMJ6R/list/
channel = NHK総合

[program_8]
name = サタデーウオッチ9
url = https://www.nhk.jp/p/ts/7K78K8ZNJV/list/
channel = NHK総合

[program_9]
name = NHKスペシャル
url = https://www.nhk.jp/p/special/ts/2NY2QQLPM3/list/
channel = NHK総合

[program_10]
name = ドキュメント72時間
url = https://www.nhk.jp/p/72hours/ts/W3W8WRN8M3/list/
channel = NHK総合

[program_11]
name = 映像の世紀バタフライエフェクト
url = https://www.nhk.jp/p/butterfly/ts/9N81M92LXV/list/
channel = NHK総合

[program_12]
name = BSスペシャル
url = https://www.nhk.jp/p/bssp/ts/6NMMPMNK5K/list/
channel = NHK BS

[program_13]
name = 漫画家イエナガの複雑社会を超定義
url = https://www.nhk.jp/p/ts/1M3MYJGG6G/list/
channel = NHK総合

[program_14]
name = 時論公論
url = https://www.nhk.jp/p/ts/4V23PRP3YR/list/
channel = NHK総合

[program_15]
name = ETV特集
url = https://www.nhk.jp/p/etv21c/ts/M2ZWLQ6RQP/list/
channel = NHK Eテレ

[program_16]
name = 首都圏情報 ネタドリ!
url = https://www.nhk.jp/p/netadori/ts/QL8GZ2L5VX/list/
channel = NHK総合

[program_17]
name = カラーでよみがえる映像の世紀
url = https://www.nhk.jp/p/ts/14R94115LZ/list/
channel = NHK総合

[program_18]
name = 時をかけるテレビ
url = https://www.nhk.jp/p/tokikaketv/ts/WQGK99QWJZ/list/
channel = NHK総合

[program_19]
name = ドキュランドへようこそ
url = https://www.nhk.jp/p/docland/ts/KZGVPVRXZN/list/
channel = NHK Eテレ

[program_20]
name = プロフェッショナル 仕事の流儀
url = https://www.nhk.jp/p/professional/ts/8X88ZVMGV5/list/
channel = NHK総合

; [program_XX]
; name = アナザーストーリーズ
; url = https://www.nhk.jp/p/anotherstories/ts/VWRZ1WWNYP/list/
; channel = NHK BS

; [program_XX]
; name = BS世界のドキュメンタリー
; url = https://www.nhk.jp/p/wdoc/ts/88Z7X45XZY/list/
; channel = NHK BS

```

tvtokyo_config.ini
```
[settings]
webdriver_timeout = 10

[program_1]
name = モーサテ
url = https://txbiz.tv-tokyo.co.jp/nms/special
time = 05:45~07:05

[program_2]
name = WBS
url = https://txbiz.tv-tokyo.co.jp/wbs/feature
time = 22:00~22:58

[program_3]
name = WBS
url = https://txbiz.tv-tokyo.co.jp/wbs/trend_tamago
time = 22:00~22:58

[program_4]
name = ガイアの夜明け
url = https://txbiz.tv-tokyo.co.jp/gaia/oa
time = 22:00~22:54

[program_5]
name = カンブリア宮殿
url = https://txbiz.tv-tokyo.co.jp/cambria/oa
time = 23:06~23:55

```


```
❯ tree                                                                                                                                                                                                                           15:13:50
.
├── common
│   ├── __pycache__
│   │   ├── base_scraper.cpython-311.pyc
│   │   ├── constants.cpython-311.pyc
│   │   ├── CustomExpectedConditions.cpython-311.pyc
│   │   └── utils.cpython-311.pyc
│   ├── base_scraper.py
│   ├── constants.py
│   ├── CustomExpectedConditions.py
│   └── utils.py
├── get-tweet.py
├── ini
│   ├── nhk_config.ini
│   └── tvtokyo_config.ini
├── memo(for-Refactoring).md
├── merge-text.py
├── open-url.py
├── output
│   ├── 20250318_before-merge.txt
│   ├── 20250318_tweet.txt
│   ├── 20250318.txt
│   ├── 2501
│   │   ├── 20250123.txt
│   │   ├── 20250124.txt
│   │   ├── 20250125.txt
│   │   ├── 20250126.txt
│   │   ├── 20250127.txt
│   │   ├── 20250128.txt
│   │   ├── 20250129.txt
│   │   ├── 20250130.txt
│   │   └── 20250131.txt
│   ├── 2502
│   │   ├── 20250201.txt
│   │   ├── 20250202.txt
│   │   ├── 20250203_bk.txt
│   │   ├── 20250203.txt
│   │   ├── 20250204.txt
│   │   ├── 20250205.txt
│   │   ├── 20250206.txt
│   │   ├── 20250207.txt
│   │   ├── 20250208.txt
│   │   ├── 20250209.txt
│   │   ├── 20250210_bk.txt
│   │   ├── 20250210.txt
│   │   ├── 20250211.txt
│   │   ├── 20250212.txt
│   │   ├── 20250213.txt
│   │   ├── 20250214.txt
│   │   ├── 20250215.txt
│   │   ├── 20250216.txt
│   │   ├── 20250217_bk.txt
│   │   ├── 20250217.txt
│   │   ├── 20250218.txt
│   │   ├── 20250219_sekai-docu.txt
│   │   ├── 20250219.txt
│   │   ├── 20250220.txt
│   │   ├── 20250221.txt
│   │   ├── 20250222.txt
│   │   ├── 20250223_sekai-docu.txt
│   │   ├── 20250223.txt
│   │   ├── 20250224_tweet_search.txt
│   │   ├── 20250224.txt
│   │   ├── 20250225_tweet_search.txt
│   │   ├── 20250225.txt
│   │   ├── 20250226_tweet_search.txt
│   │   ├── 20250226.txt
│   │   ├── 20250227.txt
│   │   ├── 20250228_tweet_search.txt
│   │   └── 20250228.txt
│   └── 2503
│       ├── 20250301.txt
│       ├── 20250302.txt
│       ├── 20250303_bk.txt
│       ├── 20250303_tweet_search.txt
│       ├── 20250303.txt
│       ├── 20250304_tweet.txt
│       ├── 20250304.txt
│       ├── 20250305_tweet.txt
│       ├── 20250305.txt
│       ├── 20250306.txt
│       ├── 20250307_tweet.txt
│       ├── 20250307.txt
│       ├── 20250308.txt
│       ├── 20250309.txt
│       ├── 20250310_before-split.txt
│       ├── 20250310_tweet.txt
│       ├── 20250310.txt
│       ├── 20250311.txt
│       ├── 20250312_before-merge.txt
│       ├── 20250312_tweet.txt
│       ├── 20250312.txt
│       ├── 20250313_before-split.txt
│       ├── 20250313.txt
│       ├── 20250314_before-merge.txt
│       ├── 20250314_tweet.txt
│       ├── 20250314.txt
│       ├── 20250315.txt
│       ├── 20250316.txt
│       ├── 20250317_before-merge.txt
│       ├── 20250317_before-split.txt
│       ├── 20250317_tweet.txt
│       └── 20250317.txt
├── README.md
├── scraping-news.py
├── split-text.py
└── tweet.py
```
