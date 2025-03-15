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
from common.utils import setup_logger, load_config, WebDriverManager, parse_programs_config, sort_blocks_by_time
import logging
from common.base_scraper import BaseScraper

# デフォルトのタイムアウト時間
DEFAULT_TIMEOUT = 10

# Selenium関連のヘルパークラス
class CustomExpectedConditions:
    """Seleniumのカスタム条件"""
    @staticmethod
    def page_is_ready():
        """ページが完全に読み込まれたことを確認する"""
        return lambda driver: driver.execute_script("return document.readyState") == "complete"

class NHKScraper(BaseScraper):  # BaseScraper を継承
    """NHKの番組情報をスクレイピングするクラス"""

    def __init__(self, config):
        super().__init__(config)  # 基底クラスの __init__ を呼び出す
        self.driver = None #削除

    def get_program_info(self, program_name: str, target_date: str) -> str | None:
        """指定された番組の情報を取得する"""
        program_info = self.config.get(program_name)
        if not program_info:
            self.logger.warning(f"{program_name} の設定情報が見つかりません")
            return None

        with WebDriverManager() as driver:
            self.driver = driver
            try:
                self.logger.info(f"検索開始: {program_name}")
                self.driver.get(program_info["url"])

                episode_url = self._extract_nhk_episode_info(target_date, program_name)
                if episode_url:
                    formatted_output = self._get_nhk_formatted_episode_info(program_name, episode_url, program_info["channel"])
                    return formatted_output
                else:
                    self.logger.warning(f"{program_name} が見つかりませんでした - {program_info['url']}")
                    return None
            except Exception as e:
                self.logger.error(f"エラーが発生しました: {e} - {program_name}, {program_info['url']}")
                return None

    def _extract_nhk_episode_info(self, target_date: str, program_title: str) -> str | None:
        """NHKのエピソード情報を抽出する"""
        try:
            WebDriverWait(self.driver, DEFAULT_TIMEOUT).until(CustomExpectedConditions.page_is_ready())
            episodes = WebDriverWait(self.driver, DEFAULT_TIMEOUT).until(
                EC.presence_of_all_elements_located((By.CLASS_NAME, 'gc-stream-panel-info'))
            )
            for episode in episodes:
                try:
                    date_element = episode.find_element(By.CLASS_NAME, 'gc-stream-panel-info-title-firstbroadcastdate-date')
                    year_element = date_element.find_element(By.CLASS_NAME, 'gc-atom-text-for-date-year')
                    day_element = date_element.find_element(By.CLASS_NAME, 'gc-atom-text-for-date-day')
                    year_text = year_element.text.strip()
                    day_text = day_element.text.strip()
                    date_text = f"{year_text}{day_text}"
                except NoSuchElementException:
                    try:
                        date_element = episode.find_element(By.CLASS_NAME, 'gc-stream-panel-info-title')
                        date_text = date_element.text.strip()
                    except NoSuchElementException:
                        continue
                match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', date_text)
                if match:
                    year, month, day = match.groups()
                    episode_date = datetime(int(year), int(month), int(day))
                    target_date_dt = datetime.strptime(target_date, '%Y%m%d')

                    if episode_date == target_date_dt:
                        episode_url = episode.find_element(By.TAG_NAME, 'a').get_attribute("href")
                        self.logger.debug(f"エピソード情報を抽出しました: {program_title} - {episode_url}")
                        return episode_url
        except Exception as e:
            self.logger.error(f"要素取得エラーが発生しました: {e} - {program_title}")
            return None
        return None

    def _get_nhk_formatted_episode_info(self, program_title: str, episode_url: str, channel: str) -> str | None:
        """NHKのエピソード情報を整形する"""
        try:
            self.driver.get(episode_url)
            WebDriverWait(self.driver, DEFAULT_TIMEOUT).until(CustomExpectedConditions.page_is_ready())
            target_element = WebDriverWait(self.driver, DEFAULT_TIMEOUT).until(
                EC.presence_of_element_located((By.CLASS_NAME, 'title'))
            )
            episode_title = target_element.text.strip().encode('utf-8', 'ignore').decode('utf-8', 'replace')

            if program_title == "BSスペシャル":
                program_time = f"({channel} 22:45-23:35)"
                final_url = self.driver.current_url
                formatted_output = f"●{program_title}{program_time}\n"
                formatted_output += f"・{episode_title}\n"
                formatted_output += f"{final_url}\n"
                self.logger.info(f"{program_title} の詳細情報を取得しました")
                return formatted_output

            nhk_plus_url = None
            try:
                span_element = WebDriverWait(self.driver, DEFAULT_TIMEOUT).until(
                    EC.presence_of_element_located((By.XPATH, '//div[@class="detailed-memo-body"]/span[contains(@class, "detailed-memo-headline")]/a[contains(text(), "NHKプラス配信はこちらからご覧ください")]'))
                )
                nhk_plus_url = span_element.get_attribute('href')
            except (NoSuchElementException, TimeoutException):
                pass

            try:
                eyecatch_div = WebDriverWait(self.driver, DEFAULT_TIMEOUT).until(
                    EC.presence_of_element_located((By.CLASS_NAME, 'gc-images.is-medium.eyecatch'))
                )
                a_tag = eyecatch_div.find_element(By.TAG_NAME, 'a')
                image_link = a_tag.get_attribute('href')
                self.driver.get(image_link)
                WebDriverWait(self.driver, DEFAULT_TIMEOUT).until(CustomExpectedConditions.page_is_ready())
                program_time = self._extract_program_time(program_title, episode_url, channel)
                final_url = self.driver.current_url
                formatted_output = f"●{program_title}{program_time}\n"
                formatted_output += f"・{episode_title}\n"

                if nhk_plus_url:
                    formatted_output += f"{nhk_plus_url}\n"
                else:
                    formatted_output += f"{final_url}\n"
                self.logger.info(f"{program_title} の詳細情報を取得しました")
                return formatted_output

            except Exception as e:
                try:
                    iframe = WebDriverWait(self.driver, DEFAULT_TIMEOUT).until(
                        EC.presence_of_element_located((By.ID, 'eyecatchIframe'))
                    )
                    iframe_src = iframe.get_attribute('src')
                    match = re.search(r'/st/(.*?)\?', iframe_src)
                    if match:
                        extracted_id = match.group(1)
                        final_url = f"https://plus.nhk.jp/watch/st/{extracted_id}"
                        self.driver.get(final_url)
                        WebDriverWait(self.driver, DEFAULT_TIMEOUT).until(CustomExpectedConditions.page_is_ready())
                        program_time = self._extract_program_time(program_title, episode_url, channel)
                        formatted_output = f"●{program_title}{program_time}\n"
                        formatted_output += f"・{episode_title}\n"
                        formatted_output += f"{final_url}\n"
                        self.logger.info(f"iframeからURLを生成しました: {final_url} - {program_title}")
                        return formatted_output
                    else:
                        self.logger.error(f"iframeからIDを抽出できませんでした: {program_title}, {episode_url} - {e}")
                        return None
                except Exception as iframe_e:
                    self.logger.error(f"gc-images.is-medium.eyecatch も iframe も見つかりませんでした: {program_title}, {episode_url} - {str(iframe_e)}") # 例外メッセージのみを渡す
                    program_time = self._extract_program_time(program_title, episode_url, channel)
                    formatted_output = f"●{program_title}{program_time}\n"
                    formatted_output += f"・{episode_title}\n"
                    formatted_output += f"{episode_url}\n"
                    return formatted_output

        except Exception as e:
            self.logger.error(f"エラーが発生しました: {e} - {program_title}, {episode_url}")
            return None

    def _extract_program_time(self, program_title: str, episode_url: str, channel: str, max_retries: int = 3, retry_interval: int = 1) -> str:
        """番組詳細ページから放送時間を抽出する"""
        if program_title == "国際報道 2025":
            return f"({channel} 22:00-22:45)"

        for retry in range(max_retries):
            try:
                time_element = WebDriverWait(self.driver, DEFAULT_TIMEOUT).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "stream_panel--info--meta"))
                )
                time_text = time_element.text.strip()
                start_ampm, start_time, end_ampm, end_time = self._extract_time_info(time_text)
                if start_time and end_time:
                    start_time_24h = self._convert_to_24h(start_ampm, start_time)
                    end_time_24h = self._convert_to_24h(end_ampm, end_time)
                    return f"({channel} {start_time_24h}-{end_time_24h})"
                else:
                    self.logger.warning(f"時間の取得に失敗しました。取得した文字列: {time_text} - {program_title}, {episode_url}")
                    return "（放送時間取得失敗）"
            except (TimeoutException, NoSuchElementException) as e:
                self.logger.warning(f"要素が見つかりませんでした (リトライ {retry+1}/{max_retries}): {e} - {program_title}, {episode_url}")
                if retry < max_retries - 1:
                    time.sleep(retry_interval)
                continue
            except Exception as e:
                self.logger.error(f"放送時間情報の抽出に失敗しました: {e} - {program_title}, {episode_url}")
                return "（放送時間取得失敗）"

        self.logger.error(f"最大リトライ回数を超えました: {program_title}, {episode_url}")
        return "（放送時間取得失敗）"

    def _extract_time_info(self, time_text: str) -> tuple[str | None, str | None, str | None, str | None]:
        """時刻情報を含む文字列から、午前/午後、時刻を抽出する"""
        match = re.search(r'((午前|午後)?(\d{1,2}:\d{2}))-((午前|午後)?(\d{1,2}:\d{2}))', time_text)
        if match:
            start_ampm = match.group(2)
            start_time = match.group(3)
            end_ampm = match.group(5)
            end_time = match.group(6)
            return start_ampm, start_time, end_ampm, end_time
        else:
            return None, None, None, None

    def _convert_to_24h(self, ampm: str | None, time_str: str) -> str:
        """時刻を24時間表記に変換する"""
        hour, minute = map(int, time_str.split(":"))
        if ampm == "午後" and hour != 12:
            hour += 12
        if ampm == "午前" and hour == 12:
            hour = 0
        return f"{hour:02}:{minute:02}"

class TVTokyoScraper(BaseScraper):  # BaseScraper を継承
    """テレビ東京の番組情報をスクレイピングするクラス"""

    def __init__(self, config):
        super().__init__(config)  # 基底クラスの __init__ を呼び出す
        self.driver = None #削除

    def get_program_info(self, program_name: str, target_date: str) -> str | None:
        """指定された番組の情報を取得する"""
        program_config = self.config.get(program_name)
        if not program_config:
            self.logger.warning(f"{program_name} の設定情報が見つかりません")
            return None

        with WebDriverManager() as driver:
            self.driver = driver
            try:
                formatted_date = format_date(target_date)
                weekday = datetime.strptime(target_date, '%Y%m%d').weekday()
                program_time = format_program_time(program_config['name'], weekday, program_config['time'])
                self.logger.info(f"検索開始: {program_name}")

                if program_name == "WBS":
                    episode_urls = self._extract_tvtokyo_episode_urls(program_config["urls"], formatted_date, program_name)
                else:
                    episode_urls = self._extract_tvtokyo_episode_urls([program_config["url"]], formatted_date, program_name)

                if not episode_urls:
                    self.logger.warning(f"{program_name} が見つかりませんでした")
                    return None

                episode_details = [
                    self._fetch_tvtokyo_episode_details(url, program_name) for url in episode_urls
                ]

                # 結果の整形
                formatted_output = f"●{program_config['name']}{program_time}\n"
                for title, url in episode_details:
                    if title and url:
                        formatted_output += f"・{title}\n{url}\n"

                if formatted_output == f"●{program_config['name']}{program_time}\n":  # 詳細情報がない場合
                    return None

                self.logger.info(f"{program_name} の詳細情報を取得しました")
                return formatted_output

            except Exception as e:
                self.logger.error(f"番組情報取得中にエラー: {e} - {program_name}")
                return None

    def _extract_tvtokyo_episode_urls(self, target_urls: list[str], formatted_date: str, program_name: str) -> list[str]:
        """
        テレビ東京のエピソードURLを抽出する。
        target_urls をリストとして受け取り、各URLに対して処理を行う。
        """
        all_urls = []
        for target_url in target_urls:
            try:
                self.driver.get(target_url)
                WebDriverWait(self.driver, DEFAULT_TIMEOUT).until(CustomExpectedConditions.page_is_ready())

                # 要素の存在確認（find_elements を使用）
                episode_elements = self.driver.find_elements(By.CSS_SELECTOR, 'div[id^="News_Detail__VideoItem__"]')
                if not episode_elements:
                    self.logger.warning(f"{program_name} のエピソード要素が見つかりませんでした - {target_url}")
                    continue  # 次のURLへ

                urls = []
                today = datetime.now().date()
                yesterday = today - timedelta(days=1)
                formatted_today = format_date(today.strftime('%Y%m%d'))
                formatted_yesterday = format_date(yesterday.strftime('%Y%m%d'))

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

    def _fetch_tvtokyo_episode_details(self, episode_url: str, program_name: str) -> tuple[str | None, str | None]:
        """テレビ東京のエピソード詳細情報を取得する"""
        try:
            self.driver.get(episode_url)
            WebDriverWait(self.driver, DEFAULT_TIMEOUT).until(CustomExpectedConditions.page_is_ready())
            title_element = WebDriverWait(self.driver, DEFAULT_TIMEOUT).until(
                EC.presence_of_element_located((By.ID, "Live_Episode_Detail_EpisodeItemFullTitle"))
            )
            title = title_element.text.strip()
            self.logger.debug(f"エピソード詳細情報を取得しました: {program_name} - {title}")
            return title, episode_url
        except Exception as e:
            self.logger.error(f"エピソード詳細取得エラー: {e} - {program_name}, {episode_url}")
            return None, None

def format_date(target_date: str) -> str:
    """日付をフォーマットする"""
    return f"{target_date[:4]}.{target_date[4:6]}.{target_date[6:8]}"

def format_program_time(program_name: str, weekday: int, default_time: str) -> str:
    """番組時間をフォーマットする"""
    if program_name.startswith("WBS"):
        return "(テレ東 22:00~22:58)" if weekday < 4 else "(テレ東 23:00~23:58)"
    return f"(テレ東 {default_time})"

def _extract_program_time(driver: webdriver.Chrome, program_title: str, episode_url: str, channel: str, max_retries: int = 3, retry_interval: int = 1) -> str:
    """番組詳細ページから放送時間を抽出する"""
    if program_title == "国際報道 2025":
        return f"({channel} 22:00-22:45)"

    for retry in range(max_retries):
        try:
            time_element = WebDriverWait(driver, DEFAULT_TIMEOUT).until(
                EC.presence_of_element_located((By.CLASS_NAME, "stream_panel--info--meta"))
            )
            time_text = time_element.text.strip()
            start_ampm, start_time, end_ampm, end_time = _extract_time_info(time_text)
            if start_time and end_time:
                start_time_24h = _convert_to_24h(start_ampm, start_time)
                end_time_24h = _convert_to_24h(end_ampm, end_time)
                return f"({channel} {start_time_24h}-{end_time_24h})"
            else:
                logging.getLogger(__name__).warning(f"時間の取得に失敗しました。取得した文字列: {time_text} - {program_title}, {episode_url}")
                return "（放送時間取得失敗）"
        except (TimeoutException, NoSuchElementException) as e:
            logging.getLogger(__name__).warning(f"要素が見つかりませんでした (リトライ {retry+1}/{max_retries}): {e} - {program_title}, {episode_url}")
            if retry < max_retries - 1:
                time.sleep(retry_interval)
            continue
        except Exception as e:
            logging.getLogger(__name__).error(f"放送時間情報の抽出に失敗しました: {e} - {program_title}, {episode_url}")
            return "（放送時間取得失敗）"

    logging.getLogger(__name__).error(f"最大リトライ回数を超えました: {program_title}, {episode_url}")
    return "（放送時間取得失敗）"

def _extract_time_info(time_text: str) -> tuple[str | None, str | None, str | None, str | None]:
    """時刻情報を含む文字列から、午前/午後、時刻を抽出する"""
    match = re.search(r'((午前|午後)?(\d{1,2}:\d{2}))-((午前|午後)?(\d{1,2}:\d{2}))', time_text)
    if match:
        start_ampm = match.group(2)
        start_time = match.group(3)
        end_ampm = match.group(5)
        end_time = match.group(6)
        return start_ampm, start_time, end_ampm, end_time
    else:
        return None, None, None, None

def _convert_to_24h(ampm: str | None, time_str: str) -> str:
    """時刻を24時間表記に変換する"""
    hour, minute = map(int, time_str.split(":"))
    if ampm == "午後" and hour != 12:
        hour += 12
    if ampm == "午前" and hour == 12:
        hour = 0
    return f"{hour:02}:{minute:02}"

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

def get_japanese_weekday(date: datetime) -> str:
    """日付から日本語の曜日を取得する"""
    weekdays = ["月", "火", "水", "木", "金", "土", "日"]
    return weekdays[date.weekday()]

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

        write_results_to_file(sorted_blocks, output_file_path, logger) #loggerを渡す

        print(f"結果を {output_file_path} に出力しました。（経過時間：{get_elapsed_time(start_time):.0f}秒）")

    except Exception as e:
        logger.error(f"メイン処理でエラーが発生しました: {e}")
        print(f"エラーが発生しました: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
