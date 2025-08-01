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
import json
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
import logging
from typing import Optional, Union, List, TypeAlias, Tuple
from common.base_scraper import BaseScraper
from common.episode_processor import EpisodeProcessor
from common.utils import (
    setup_logger, WebDriverManager, parse_programs_config,
    sort_blocks_by_time, Constants, format_date,
    format_program_time,
    ScrapeStatus
)
from common.CustomExpectedConditions import CustomExpectedConditions

# --- 型エイリアス定義 ---
# Scraper が返す型
ScrapeResultData = Optional[Union[str, List[str]]]
ScrapeResult = Tuple[ScrapeStatus, ScrapeResultData]

# fetch_program_info が返す型
FetchResult: TypeAlias = Optional[Tuple[str, ScrapeStatus, ScrapeResultData]]

class NHKScraper(BaseScraper):
    """NHKの番組情報をスクレイピングするクラス"""
    def __init__(self, config):
        super().__init__(config)
        self.episode_processor = EpisodeProcessor(self.logger)

    @BaseScraper.log_operation("番組情報の取得")
    def get_program_info(self, program_name: str, target_date: str) -> ScrapeResult:
        """指定された番組の情報を取得する"""
        if not self.validate_config(program_name):
            return ScrapeStatus.FAILURE, f"設定情報が見つかりません"

        program_info = self.config.get(program_name)

        def scrape_operation(driver) -> ScrapeResult:
            episode_url = self._extract_nhk_episode_info(driver, target_date, program_name)
            if episode_url:
                formatted_info = self._get_nhk_formatted_episode_info(driver, program_name, episode_url, program_info.get("channel", "不明"))
                if formatted_info:
                    return ScrapeStatus.SUCCESS, formatted_info
                else:
                    return ScrapeStatus.FAILURE, f"詳細情報の整形/取得に失敗"
            else:
                return ScrapeStatus.NOT_FOUND, f"対象エピソードが見つかりません"

        result = self.execute_with_driver(scrape_operation)

        if result is None:
            return ScrapeStatus.FAILURE, f"WebDriverエラーまたは内部エラー発生"
        elif isinstance(result, tuple) and len(result) == 2 and isinstance(result[0], ScrapeStatus):
            return result
        else:
            self.logger.error(f"execute_with_driver が予期しない値を返しました: {result}")
            return ScrapeStatus.FAILURE, f"予期しない内部エラー"

    @BaseScraper.handle_selenium_error
    def _extract_nhk_episode_info(self, driver, target_date: str, program_title: str) -> str | None:
        """NHKのエピソード情報を抽出する"""
        program_info = self.config.get(program_title)
        if not program_info:
            return None

        driver.get(program_info["url"])
        episodes = self.episode_processor.find_episode_elements(driver, program_title)
        if not episodes:
            return None

        target_date_dt = datetime.strptime(target_date, '%Y%m%d')
        for episode in episodes:
            episode_date = self.episode_processor.extract_episode_date(episode, program_title)
            if episode_date and episode_date == target_date_dt:
                return self.episode_processor.extract_episode_url(episode, program_title)
        return None

    #【新設】JSON-LDから放送時間を抽出するメソッド
    def _extract_time_from_json_ld(self, driver) -> Optional[str]:
        """エピソード詳細ページのJSON-LDから放送時間を抽出する。"""
        try:
            script_element = WebDriverWait(driver, Constants.Time.SHORT_TIMEOUT).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'script[type="application/ld+json"]'))
            )
            json_text = script_element.get_attribute('innerHTML')
            data = json.loads(json_text)

            # "startDate"と"endDate"を含む可能性のあるキーを探す
            publication_event = None
            if 'detailedRecentEvent:customProperty' in data and isinstance(data.get('detailedRecentEvent:customProperty'), dict):
                publication_event = data['detailedRecentEvent:customProperty']
            elif 'publication' in data:
                # 'publication'はリストの場合と辞書の場合がある
                if isinstance(data['publication'], list) and len(data['publication']) > 0:
                    publication_event = data['publication'][0]
                elif isinstance(data['publication'], dict):
                    publication_event = data['publication']

            if not publication_event:
                self.logger.warning("JSON-LD内に放送時間情報 (publication_event) が見つかりませんでした。")
                return None

            start_date_str = publication_event.get('startDate')
            end_date_str = publication_event.get('endDate')

            if start_date_str and end_date_str:
                start_time = datetime.fromisoformat(start_date_str).strftime('%H:%M')
                end_time = datetime.fromisoformat(end_date_str).strftime('%H:%M')
                return f"{start_time}-{end_time}"
            else:
                self.logger.warning("JSON-LD内に startDate または endDate が見つかりませんでした。")
                return None

        except (NoSuchElementException, TimeoutException):
            self.logger.debug("JSON-LDのscriptタグが見つかりませんでした。")
            return None
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            self.logger.error(f"JSON-LDからの時間抽出中にエラーが発生: {e}")
            return None

    @BaseScraper.handle_selenium_error
    def _get_nhk_formatted_episode_info(self, driver, program_title: str, episode_url: str, channel: str) -> str | None:
        """NHKのエピソード情報を整形する"""
        self.episode_processor.get_episode_detail_page(driver, episode_url)
        episode_title = self.episode_processor.extract_episode_title(driver)
        if not episode_title:
            return None

        if program_title == "BSスペシャル":
            return self._format_bs_special_output(driver, program_title, channel, episode_url, episode_title)

        nhk_plus_url = self._extract_nhk_plus_url(driver)

        #【修正】時間取得処理を _process_eyecatch_or_iframe の外に移動し、一元化
        time_str = self._extract_time_from_json_ld(driver)
        if time_str:
            program_time = f"({channel} {time_str})"
        else:
            self.logger.warning(f"放送時間が取得できませんでした。({program_title})")
            program_time = f"({channel} 時間未定)"

        # _process_eyecatch_or_iframe に program_time を渡すように変更
        formatted_output = self._process_eyecatch_or_iframe(driver, program_title, episode_url, episode_title, nhk_plus_url, program_time)
        if formatted_output:
            return formatted_output

        #【修正】フォールバックでも program_time を使用
        return self._format_fallback_output(program_title, episode_url, episode_title, program_time)

    def _format_bs_special_output(self, driver, program_title: str, channel: str, episode_url: str, episode_title: str) -> str:
        """BSスペシャル用の出力フォーマット"""
        program_time = f"({channel} 22:45-23:35)"
        return self._format_program_output(
            program_title=program_title,
            program_time=program_time,
            episode_title=episode_title,
            url_to_display=driver.current_url
        )

    def _extract_nhk_plus_url(self, driver) -> str | None:
        """NHKプラスのURLを抽出する"""
        try:
            span_element = WebDriverWait(driver, Constants.Time.DEFAULT_TIMEOUT).until(
                EC.presence_of_element_located((By.XPATH, Constants.CSSSelector.NHK_PLUS_URL_SPAN))
            )
            return span_element.get_attribute('href')
        except (NoSuchElementException, TimeoutException):
            return None

    #【修正】引数に program_time を追加
    def _process_eyecatch_or_iframe(self, driver, program_title: str, episode_url: str, episode_title: str, nhk_plus_url: str | None, program_time: str) -> str | None:
        """eyecatch画像またはiframeからURLを取得し、整形された出力文字列を返す"""
        final_url = None
        try:
            final_url = self._process_eyecatch_image(driver, program_title, episode_url)
        except Exception:
            self.logger.debug(f"eyecatch画像処理失敗。iframeを試行します。 - {program_title}")

        if not final_url:
            try:
                final_url = self._process_iframe_url(driver, program_title, episode_url)
            except Exception as iframe_e:
                self.logger.debug(f"iframe URL取得失敗: {str(iframe_e)} - {program_title}")

        if final_url:
            url_to_use = nhk_plus_url if nhk_plus_url else final_url
            #【修正】program_time は引数で受け取ったものを使用
            formatted_output = self._format_program_output(
                program_title=program_title,
                program_time=program_time,
                episode_title=episode_title,
                url_to_display=url_to_use
            )
            self.logger.info(f"{program_title} の詳細情報を取得しました")
            return formatted_output

        self.logger.debug(f"eyecatch/iframe どちらからも有効なURLを取得できませんでした - {program_title}")
        return None

    def _process_eyecatch_image(self, driver, program_title: str, episode_url: str) -> str | None:
        # ... (このメソッドは変更なし) ...
        eyecatch_div = WebDriverWait(driver, Constants.Time.DEFAULT_TIMEOUT).until(
            EC.presence_of_element_located((By.CLASS_NAME, Constants.CSSSelector.EYECATCH_IMAGE_DIV))
        )
        a_tag_element = eyecatch_div.find_element(By.TAG_NAME, Constants.CSSSelector.EPISODE_URL_TAG)
        image_link = a_tag_element.get_attribute('href')
        driver.get(image_link)
        WebDriverWait(driver, Constants.Time.DEFAULT_TIMEOUT).until(CustomExpectedConditions.page_is_ready())
        return driver.current_url

    def _process_iframe_url(self, driver, program_title: str, episode_url: str) -> str | None:
        # ... (このメソッドは変更なし) ...
        iframe = WebDriverWait(driver, Constants.Time.DEFAULT_TIMEOUT).until(
            EC.presence_of_element_located((By.ID, Constants.CSSSelector.IFRAME_ID))
        )
        iframe_src = iframe.get_attribute('src')
        match = re.search(r'/st/(.*?)\?', iframe_src)
        if match:
            extracted_id = match.group(1)
            final_url = f"https://plus.nhk.jp/watch/st/{extracted_id}"
            driver.get(final_url)
            WebDriverWait(driver, Constants.Time.DEFAULT_TIMEOUT).until(CustomExpectedConditions.page_is_ready())
            self.logger.info(f"iframeからURLを生成しました: {final_url} - {program_title}")
            return final_url
        else:
            self.logger.debug(f"iframeからIDを抽出できませんでした: {program_title}")
            return None

    #【修正】引数を変更し、ロジックを簡略化
    def _format_fallback_output(self, program_title: str, episode_url: str, episode_title: str, program_time: str) -> str:
        """eyecatch, iframe 処理失敗時のフォールバック出力"""
        return self._format_program_output(
            program_title=program_title,
            program_time=program_time,
            episode_title=episode_title,
            url_to_display=episode_url
        )

class TVTokyoScraper(BaseScraper):
    """テレビ東京の番組情報をスクレイピングするクラス"""

    def __init__(self, config):
        super().__init__(config)

    @BaseScraper.log_operation("番組情報の取得")
    def get_program_info(self, program_name: str, target_date: str) -> ScrapeResult:
        if not self.validate_config(program_name):
            return ScrapeStatus.FAILURE, "設定情報が見つかりません"

        program_config = self.config.get(program_name)
        self.logger.debug(f"[{program_name}] 設定内容: {program_config}")

        try:
            with WebDriverManager() as driver:
                formatted_date = format_date(target_date)
                weekday = datetime.strptime(target_date, '%Y%m%d').weekday()
                program_time = format_program_time(program_config.get('name'), weekday, program_config.get('time'))

                target_urls = self._prepare_target_urls(program_config, program_name)
                if not target_urls:
                    return ScrapeStatus.FAILURE, "有効なURLが設定されていません"

                return self._fetch_and_format_tvtokyo_episodes(
                    driver, program_config, target_urls, formatted_date, program_time, program_name
                )

        except Exception as e:
            self.logger.error(f"番組情報取得中にエラー: {e} - {program_name}", exc_info=True)
            return ScrapeStatus.FAILURE, f"処理中にエラー: {e}"

    def _prepare_target_urls(self, program_config: dict, program_name: str) -> List[str]:
        target_urls = []
        urls_value = program_config.get("urls")
        url_value = program_config.get("url")

        if urls_value:
            self.logger.debug(f"[{program_name}] 'urls' キーを処理: {urls_value} (型: {type(urls_value)})")
            if isinstance(urls_value, str):
                target_urls = [url.strip() for url in urls_value.split(',') if url.strip()]
            elif isinstance(urls_value, list):
                target_urls = [str(url).strip() for url in urls_value if str(url).strip()]
            else:
                self.logger.warning(f"[{program_name}] 'urls' の型が不正 ({type(urls_value)})。'url' キーを試行します。")

        if not target_urls and url_value:
            self.logger.debug(f"[{program_name}] 'url' キーを処理: {url_value} (型: {type(url_value)})")
            if isinstance(url_value, str) and url_value.strip():
                target_urls = [url_value.strip()]
            else:
                self.logger.warning(f"[{program_name}] 'url' キーの値が無効です: {url_value}")

        self.logger.debug(f"[{program_name}] 最終的な target_urls: {target_urls}")
        return target_urls

    def _fetch_and_format_tvtokyo_episodes(self, driver, program_config: dict, target_urls: List[str], formatted_date: str, program_time: str, program_name: str) -> ScrapeResult:
        episode_urls = self._extract_tvtokyo_episode_urls(driver, target_urls, formatted_date, program_name)
        if not episode_urls:
            return ScrapeStatus.NOT_FOUND, f"放送が見つかりませんでした (日付: {formatted_date})"

        all_formatted_outputs = []
        episode_details = []
        for url in episode_urls:
            detail = self._fetch_tvtokyo_episode_details(driver, url, program_name)
            if detail and detail[0] and detail[1]:
                episode_details.append(detail)

        if not episode_details:
            return ScrapeStatus.FAILURE, "有効なエピソード詳細が見つかりませんでした"

        for episode_title, episode_detail_url in episode_details:
            formatted_output = self._format_program_output(
                program_title=program_config['name'],
                program_time=program_time,
                episode_title=episode_title,
                url_to_display=episode_detail_url
            )
            if formatted_output:
                all_formatted_outputs.append(formatted_output)

        if not all_formatted_outputs:
            return ScrapeStatus.FAILURE, "有効なフォーマット済み出力が得られませんでした"

        return ScrapeStatus.SUCCESS, all_formatted_outputs

    def _extract_tvtokyo_episode_urls(self, driver, target_urls: list[str], formatted_date: str, program_name: str) -> list[str]:
        """
        テレビ東京のエピソードURLを抽出する。
        target_urls をリストとして受け取り、各URLに対して処理を行う。
        """
        all_urls = []
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)
        formatted_today = format_date(today.strftime('%Y%m%d'))
        formatted_yesterday = format_date(yesterday.strftime('%Y%m%d'))

        for target_url in target_urls:
            try:
                driver.get(target_url)
                # ページの主要なリスト要素が表示されるまで待機（より具体的に）
                try:
                    WebDriverWait(driver, Constants.Time.DEFAULT_TIMEOUT).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, Constants.CSSSelector.TVTOKYO_VIDEO_ITEM))
                    )
                except TimeoutException:
                    self.logger.warning(f"{program_name} のエピソードリスト要素が見つかりませんでした（タイムアウト） - {target_url}")
                    continue # 次のURLへ

                # 動的コンテンツ（特に日付やリンク情報）が読み込まれるのを待機
                # リストの最後の要素が 'visibility' (表示状態) になるまで待つ
                try:
                    # 最後の要素を取得するCSSセレクタ :last-child を使用
                    last_item_selector = f"{Constants.CSSSelector.TVTOKYO_VIDEO_ITEM}:last-child"
                    WebDriverWait(driver, Constants.Time.SHORT_TIMEOUT).until( # 少し短めのタイムアウトで試行
                        EC.visibility_of_element_located((By.CSS_SELECTOR, last_item_selector))
                    )
                    self.logger.debug(f"リストの最後の要素が表示されるのを待機完了 - {program_name} - {target_url}")
                except TimeoutException:
                    # タイムアウトしても、要素が取得できる可能性はあるため、警告に留めて処理を続行
                    self.logger.warning(f"リストの最後の要素の表示待機中にタイムアウトしましたが、処理を続行します - {program_name} - {target_url}")

                episode_elements = driver.find_elements(By.CSS_SELECTOR, Constants.CSSSelector.TVTOKYO_VIDEO_ITEM)
                if not episode_elements:
                    self.logger.warning(f"{program_name} のエピソード要素が見つかりませんでした - {target_url}")
                    continue

                urls_found_on_page = []
                for episode in episode_elements:
                    try:
                        # 日付要素の取得を試みる
                        date_elements = episode.find_elements(By.CSS_SELECTOR, Constants.CSSSelector.TVTOKYO_DATE_SPAN)
                        if not date_elements:
                            self.logger.debug(f"日付要素が見つかりませんでした - {program_name} - {target_url}")
                            continue

                        date_element = date_elements[0]
                        date_text = date_element.text.strip()

                        # 日付のマッチング確認
                        is_matching_date = (
                            ("今日" in date_text and formatted_today == formatted_date) or
                            ("昨日" in date_text and formatted_yesterday == formatted_date) or
                            date_text == formatted_date # "MM月DD日" 形式
                        )

                        if is_matching_date:
                            try:
                                link_element = episode.find_element(By.CSS_SELECTOR, Constants.CSSSelector.TVTOKYO_POST_LINK)
                                link = link_element.get_attribute("href")
                                if link:
                                    urls_found_on_page.append(link)
                                else:
                                    self.logger.debug(f"リンクURLが空でした - {program_name} - {target_url}")
                            except NoSuchElementException:
                                self.logger.debug(f"リンク要素が見つかりませんでした - {program_name} - {target_url}")

                    except StaleElementReferenceException:
                        self.logger.warning(f"要素が無効になりました。リトライまたはスキップします - {program_name} - {target_url}")
                        break # このページの処理を中断して次のURLへ行く方が安全か
                    except Exception as e_inner:
                        self.logger.error(f"エピソード解析中に予期せぬエラー: {e_inner} - {program_name} - {target_url}", exc_info=True)

                if urls_found_on_page:
                    self.logger.debug(f"抽出されたURL ({target_url}): {urls_found_on_page}")
                    all_urls.extend(urls_found_on_page)
                else:
                    self.logger.debug(f"対象日付のエピソードは見つかりませんでした - {program_name} - {target_url} (日付: {formatted_date})")

            except Exception as e_outer:
                self.logger.error(f"URL ({target_url}) の処理中にエラー: {e_outer} - {program_name}", exc_info=True)

        # 重複を除去して返す
        unique_urls = sorted(list(set(all_urls)))
        self.logger.debug(f"最終的に抽出されたユニークなエピソードURL: {program_name} - {unique_urls}")
        return unique_urls

    def _fetch_tvtokyo_episode_details(self, driver, episode_url: str, program_name: str) -> tuple[str | None, str | None]:
        """テレビ東京のエピソード詳細情報を取得する"""
        try:
            driver.get(episode_url)
            # タイトル要素が表示されるまで待機
            try:
                title_element = WebDriverWait(driver, Constants.Time.DEFAULT_TIMEOUT).until(
                    EC.presence_of_element_located((By.ID, Constants.CSSSelector.TVTOKYO_EPISODE_TITLE))
                )
                title = title_element.text.strip()
                if not title: # タイトルが空の場合も考慮
                    self.logger.warning(f"エピソードタイトルが空でした - {program_name} - {episode_url}")
                    return None, episode_url # URLは返す
                self.logger.debug(f"エピソード詳細情報を取得しました: {program_name} - {title}")
                return title, episode_url
            except TimeoutException:
                self.logger.error(f"エピソードタイトル要素が見つかりませんでした（タイムアウト） - {program_name} - {episode_url}")
                return None, None # タイトルが見つからない場合は失敗扱い

        except Exception as e:
            self.logger.error(f"エピソード詳細取得エラー: {e} - {program_name}, {episode_url}", exc_info=True)
            return None, None

# --- 関数定義 ---
# モジュールレベルのロガーを取得
logger = logging.getLogger(__name__)

# 戻り値の型アノテーションを修正: FetchResult を使用
def fetch_program_info(args: tuple[str, str, dict, str]) -> FetchResult: # 戻り値の型を FetchResult に
    """並列処理用のラッパー関数。番組名、ステータス、結果/メッセージのタプル、またはNoneを返す"""
    task_type, program_name, programs, target_date = args
    process_logger = logging.getLogger(f"{__name__}.{program_name}")

    try:
        scraper = None
        status: ScrapeStatus = ScrapeStatus.FAILURE # デフォルト
        data_or_message: ScrapeResultData = "不明なエラー" # デフォルト

        if task_type == 'nhk':
            scraper = NHKScraper(programs)
            status, data_or_message = scraper.get_program_info(program_name, target_date)
        elif task_type == 'tvtokyo':
            scraper = TVTokyoScraper(programs)
            status, data_or_message = scraper.get_program_info(program_name, target_date)
        else:
            process_logger.error(f"不明なタスクタイプです: {task_type}")
            return program_name, ScrapeStatus.FAILURE, f"不明なタスクタイプ: {task_type}"

        # scraper.get_program_info の結果をタプルで返す
        return program_name, status, data_or_message

    except Exception as e:
        process_logger.error(f"{program_name} の情報取得プロセスで予期せぬエラー: {e}", exc_info=True)
        # プロセスレベルのエラーも failure タプルで返す
        return program_name, ScrapeStatus.FAILURE, f"プロセスエラー: {e}"

def get_elapsed_time(start_time: float) -> float:
    """経過時間を計算する"""
    end_time = time.time()
    return end_time - start_time

def process_scraping(target_date: str, nhk_programs: dict, tvtokyo_programs: dict) -> list[tuple[str, str, dict, str]]:
    """スクレイピング処理を行う"""
    nhk_tasks = [('nhk', program_title, nhk_programs, target_date) for program_title in nhk_programs]
    tvtokyo_tasks = [('tvtokyo', program_name, tvtokyo_programs, target_date) for program_name in tvtokyo_programs]
    return nhk_tasks + tvtokyo_tasks

def write_results_to_file(sorted_blocks: list[str], output_file_path: str) -> None:
    """ソートされた結果をファイルに書き込む (logger を引数で受け取らない)"""
    # モジュールレベルの logger を使用
    try:
        previous_header = None
        with open(output_file_path, "w", encoding="utf-8") as f:
            # ... (ファイル書き込みロジックは変更なし) ...
            for i, block in enumerate(sorted_blocks):
                lines = [line for line in block.split('\n') if line.strip()]
                if not lines:
                    logger.debug(f"空のブロックをスキップしました: index={i}")
                    continue
                current_header = lines[0]
                is_header = current_header.startswith('●')
                if is_header:
                    if current_header == previous_header:
                        logger.debug(f"ヘッダー重複検出、結合します: {current_header}")
                        for line in lines[1:]:
                            f.write(line + '\n')
                    else:
                        if i > 0: f.write('\n')
                        logger.debug(f"新しいヘッダーを書き込みます: {current_header}")
                        for line in lines: f.write(line + '\n')
                        previous_header = current_header
                else:
                    logger.warning(f"予期しない形式のブロック（ヘッダーなし）: index={i}, content='{block[:50]}...'")
                    if i > 0: f.write('\n')
                    for line in lines: f.write(line + '\n')
                    previous_header = None

        logger.info(f"ファイルへの書き込み完了: {output_file_path}")

    except Exception as e:
        logger.error(f"ファイルへの書き込み中にエラーが発生しました: {e}", exc_info=True)
        raise

def process_and_sort_results(results: list[str | list[str] | None], start_time: float) -> list[str]:
    """結果を番組ブロックごとに分割し、時間順にソートする"""
    logger.info(f"【後処理開始】結果の分割とソート...（経過時間：{get_elapsed_time(start_time):.0f}秒）")
    flat_results = []
    for res in results:
        if isinstance(res, list):
            flat_results.extend(r for r in res if isinstance(r, str))
        elif isinstance(res, str):
            flat_results.append(res)
    logger.debug(f"有効な結果件数: {len(flat_results)}")

    blocks = []
    current_block = []
    for line in flat_results:
        if line.startswith('●'):
            if current_block:
                blocks.append('\n'.join(current_block))
            current_block = [line]
        elif current_block:
            current_block.append(line)
        else:
            logger.warning(f"ヘッダーなしで始まる行を検出、スキップします: {line[:50]}...")

    if current_block:
        blocks.append('\n'.join(current_block))

    logger.info(f"番組ブロックの分割完了: {len(blocks)} ブロック")
    logger.info(f"番組ブロックを時間順にソート中...")
    sorted_blocks = sort_blocks_by_time(blocks) # sort_blocks_by_time は修正済みの extract_time_from_block を使う
    logger.info(f"番組ブロックのソート完了（経過時間：{get_elapsed_time(start_time):.0f}秒）")
    return sorted_blocks

# --- ヘルパー関数定義 ---
def _process_fetch_result(fetch_result: FetchResult, results_list: list[str], logger: logging.Logger) -> str:
    """
    fetch_program_info の結果を処理し、進捗メッセージを生成する。
    成功した場合は results_list にデータを追加する。
    """
    if fetch_result is None:
        logger.error("fetch_program_info が None を返しました")
        return "不明なタスクでエラー発生"

    program_name, status, data_or_message = fetch_result
    progress_message = ""

    if status == ScrapeStatus.SUCCESS:
        result_count = 0
        if isinstance(data_or_message, list):
            valid_results = [res for res in data_or_message if isinstance(res, str)]
            results_list.extend(valid_results)
            result_count = len(valid_results)
        elif isinstance(data_or_message, str) and data_or_message:
            results_list.append(data_or_message)
            result_count = 1
        progress_message = f"{program_name} 完了 ({result_count}件)" if result_count > 0 else f"{program_name} 完了 (データなし)"
    elif status == ScrapeStatus.FAILURE:
        failure_reason = data_or_message if isinstance(data_or_message, str) else "詳細不明"
        max_len = 60
        if len(failure_reason) > max_len:
            failure_reason = failure_reason[:max_len] + "..."
        progress_message = f"{program_name} 失敗: {failure_reason}"
    elif status == ScrapeStatus.NOT_FOUND:
        reason = data_or_message if isinstance(data_or_message, str) else "詳細不明"
        progress_message = f"{program_name} 対象なし: {reason}" # メッセージを調整
    else:
        progress_message = f"{program_name} 未知の状態 ({status.name})"
        logger.warning(f"不明なステータスを受け取りました: {fetch_result}")

    return progress_message

def main():
    """メイン関数"""
    # --- Logger Setup ---
    global_logger = setup_logger(level=logging.INFO)
    # global_logger = setup_logger(level=logging.DEBUG)
    # ---------------------

    target_date = sys.argv[1]
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    output_file_path = os.path.join(output_dir, f"{target_date}.txt")

    start_time = time.time()
    global_logger.info("=== scraping-news 処理開始 ===")
    global_logger.info(f"対象日付: {target_date}")

    try:
        nhk_programs = parse_programs_config('ini/nhk_config.ini')
        tvtokyo_programs = parse_programs_config('ini/tvtokyo_config.ini')

        if not nhk_programs and not tvtokyo_programs:
            global_logger.error("設定ファイルの読み込みに失敗したか、設定が空です。処理を終了します。")
            sys.exit(1)

        tasks = process_scraping(target_date, nhk_programs or {}, tvtokyo_programs or {})
        total_tasks = len(tasks)
        processed_tasks = 0
        results = [] # スクレイピング結果のみを格納

        if total_tasks == 0:
            global_logger.warning("実行するタスクがありません。")
        else:
            global_logger.info(f"並列処理を開始します ({total_tasks} タスク)")
            with multiprocessing.Pool() as pool:
                # imap_unordered で FetchResult を受け取る
                for fetch_result in pool.imap_unordered(fetch_program_info, tasks):
                    processed_tasks += 1
                    elapsed_time = get_elapsed_time(start_time)

                    # ヘルパー関数で結果処理とメッセージ生成
                    progress_message = _process_fetch_result(fetch_result, results, global_logger)

                    # 進捗表示 (1行にまとめる)
                    # \r を使って行を上書きすることで、ログが流れすぎるのを防ぐ
                    print(f"\n進捗: {processed_tasks}/{total_tasks} ({progress_message}) （経過時間：{elapsed_time:.0f}秒）", end="")

            print() # \r で上書きした行の後で改行を入れる
            global_logger.info("並列処理が完了しました。")

        # --- 結果の集計とファイル書き込み ---
        if not results:
            global_logger.warning("有効な番組情報が一件も見つかりませんでした。")
            print("有効な番組情報が見つからなかったため、ファイルは作成されませんでした。")
        else:
            # process_and_sort_results は成功データ (results) のみを処理する
            sorted_blocks = process_and_sort_results(results, start_time)
            write_results_to_file(sorted_blocks, output_file_path)
            print(f"\n結果を {output_file_path} に出力しました。（経過時間：{get_elapsed_time(start_time):.0f}秒）")


    except Exception as e:
        global_logger.error(f"メイン処理で予期せぬエラーが発生しました: {e}", exc_info=True)
        print(f"エラーが発生しました: {e}")
        sys.exit(1)
    finally:
        global_logger.info(f"=== scraping-news 処理終了（総経過時間：{get_elapsed_time(start_time):.0f}秒） ===")

if __name__ == "__main__":
    # Windows で multiprocessing を使う場合に必要な場合がある
    # multiprocessing.freeze_support()
    main()
