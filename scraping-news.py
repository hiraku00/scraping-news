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
                date_element = episode.find_element(By.CLASS_NAME, Constants.CSSSelector.DATE_TEXT_WITH_YEAR)
                year_element = date_element.find_element(By.CLASS_NAME, Constants.CSSSelector.DATE_YEAR)
                day_element = date_element.find_element(By.CLASS_NAME, Constants.CSSSelector.DATE_DAY)
                year_text = year_element.text.strip()
                day_text = day_element.text.strip()
                date_text = f"{year_text}{day_text}"
            except NoSuchElementException:
                date_element = episode.find_element(By.CLASS_NAME, Constants.CSSSelector.DATE_TEXT_NO_YEAR)
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
                self.logger.debug(f"iframe URL取得失敗 (正常な状態の可能性あり): {program_title} - {str(iframe_e)}")
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
            self.logger.debug(f"iframeからIDを抽出できませんでした（正常な状態の可能性あり）: {program_title}")
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

def process_and_sort_results(results: list[str | None], start_time: float, logger) -> list[str]:
    """結果を番組ブロックごとに分割し、時間順にソートする"""
    logger.info(f"\n【後処理開始】結果を番組ブロックごとに分割中...（経過時間：{get_elapsed_time(start_time):.0f}秒）") # \n を追加
    blocks = []
    current_block = []
    # results リスト内の None をフィルタリング
    filtered_results = [res for res in results if res is not None]

    for line in filtered_results: # None を除外したリストを処理
        if line.startswith('●'): # None チェックは不要になった
            if current_block:
                blocks.append('\n'.join(current_block))
            current_block = [line] # 新しいブロックを開始
        else:
            current_block.append(line) # 現在のブロックに追加

    if current_block: # ループ終了後に最後のブロックを追加
        blocks.append('\n'.join(current_block))

    logger.info(f"番組ブロックの分割完了: {len(blocks)} ブロック作成（経過時間：{get_elapsed_time(start_time):.0f}秒）")

    logger.info(f"番組ブロックを時間順にソート中...（経過時間：{get_elapsed_time(start_time):.0f}秒）")
    sorted_blocks = sort_blocks_by_time(blocks)
    logger.info(f"番組ブロックのソート完了（経過時間：{get_elapsed_time(start_time):.0f}秒）")
    return sorted_blocks

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

        # 結果の集計とソート
        sorted_blocks = process_and_sort_results(results, start_time, logger)

        # ファイルへの書き込み
        write_results_to_file(sorted_blocks, output_file_path, logger)

        print(f"\n結果を {output_file_path} に出力しました。（経過時間：{get_elapsed_time(start_time):.0f}秒）") # \n を追加して改行

    except Exception as e:
        logger.error(f"メイン処理でエラーが発生しました: {e}")
        print(f"エラーが発生しました: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
