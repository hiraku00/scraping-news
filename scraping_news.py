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
import logging
from typing import Optional, Union, List, TypeAlias, Tuple
from common.base_scraper import BaseScraper
from common.episode_processor import EpisodeProcessor
from common.utils import (
    setup_logger, WebDriverManager, parse_programs_config,
    sort_blocks_by_time, Constants, format_date,
    format_program_time, extract_program_time_info
)
from common.CustomExpectedConditions import CustomExpectedConditions

# --- 型エイリアス定義 ---
# Scraper が返す型
ScrapeResultData = Optional[Union[str, List[str]]]
ScrapeResult = Tuple[str, ScrapeResultData] # (status, data_or_message)
# fetch_program_info が返す型
FetchResult: TypeAlias = Optional[Tuple[str, str, ScrapeResultData]] # (program_name, status, data_or_message)

class NHKScraper(BaseScraper):
    """NHKの番組情報をスクレイピングするクラス"""
    def __init__(self, config):
        super().__init__(config)
        self.episode_processor = EpisodeProcessor(self.logger)

    @BaseScraper.log_operation("番組情報の取得") # 修正したデコレータを使用
    def get_program_info(self, program_name: str, target_date: str) -> ScrapeResult: # 戻り値の型を ScrapeResult に
        """指定された番組の情報を取得する"""
        if not self.validate_config(program_name):
            return "failure", f"設定情報が見つかりません" # ステータスとメッセージを返す

        program_info = self.config.get(program_name)

        def scrape_operation(driver) -> ScrapeResult:
            episode_url = self._extract_nhk_episode_info(driver, target_date, program_name)
            if episode_url:
                # _get_nhk_formatted_episode_info は成功すれば文字列、失敗すれば None を返す想定
                formatted_info = self._get_nhk_formatted_episode_info(driver, program_name, episode_url, program_info.get("channel", "不明"))
                if formatted_info:
                    return "success", formatted_info # 成功タプル
                else:
                    # 整形失敗
                    return "failure", f"詳細情報の整形/取得に失敗" # 失敗タプル
            else:
                # エピソードが見つからない
                return "failure", f"対象エピソードが見つかりません" # 失敗タプル

        # execute_with_driver は成功すれば scrape_operation の結果 (ScrapeResult)、失敗すれば None を返す
        result = self.execute_with_driver(scrape_operation)

        if result is None:
            # WebDriver 操作中のエラーなど
            return "failure", f"WebDriverエラーまたは内部エラー発生"
        elif isinstance(result, tuple) and len(result) == 2:
            # scrape_operation が正常に ScrapeResult を返した場合
            return result # そのまま返す
        else:
            # 予期しない戻り値
            self.logger.error(f"execute_with_driver が予期しない値を返しました: {result}")
            return "failure", f"予期しない内部エラー"

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
        formatted_output = self._process_eyecatch_or_iframe(driver, program_title, episode_url, channel, episode_title, nhk_plus_url)
        if formatted_output:
            return formatted_output

        return self._format_fallback_output(driver, program_title, episode_url, channel, episode_title)

    def _format_bs_special_output(self, driver, program_title: str, channel: str, episode_url: str, episode_title: str) -> str:
        """BSスペシャル用の出力フォーマット"""
        # BSスペシャルは固定の時間枠を使用
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
            url_to_use = nhk_plus_url if nhk_plus_url else final_url
            formatted_output = self._format_program_output(
                program_title=program_title,
                program_time=extract_program_time_info(driver, program_title, episode_url, channel),
                episode_title=episode_title,
                url_to_display=url_to_use
            )
            self.logger.info(f"{program_title} の詳細情報を取得しました")
            return formatted_output
        return None # eyecatch, iframe どちらからもURLを取得できなかった場合

    def _process_eyecatch_image(self, driver, program_title: str, episode_url: str) -> str | None:
        """eyecatch画像からURLを取得する"""
        eyecatch_div = WebDriverWait(driver, Constants.Time.DEFAULT_TIMEOUT).until(
            EC.presence_of_element_located((By.CLASS_NAME, Constants.CSSSelector.EYECATCH_IMAGE_DIV))
        )
        a_tag_element = eyecatch_div.find_element(By.TAG_NAME, Constants.CSSSelector.EPISODE_URL_TAG)
        image_link = a_tag_element.get_attribute('href')
        driver.get(image_link)
        WebDriverWait(driver, Constants.Time.DEFAULT_TIMEOUT).until(CustomExpectedConditions.page_is_ready())
        return driver.current_url

    def _process_iframe_url(self, driver, program_title: str, episode_url: str) -> str | None:
        """iframeからURLを取得する"""
        iframe = WebDriverWait(driver, Constants.Time.DEFAULT_TIMEOUT).until(
            EC.presence_of_element_located((By.ID, Constants.CSSSelector.IFRAME_ID))
        ) # By.ID で検索
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
            self.logger.debug(f"iframeからIDを抽出できませんでした（正常な状態の可能性あり）: {program_title}")
            return None

    def _format_fallback_output(self, driver, program_title: str, episode_url: str, channel: str, episode_title: str) -> str:
        """eyecatch, iframe 処理失敗時のフォールバック出力"""
        program_time = extract_program_time_info(driver, program_title, episode_url, channel)
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
            return "failure", f"設定情報が見つかりません"

        program_config = self.config.get(program_name)
        # --- デバッグログ追加 ---
        self.logger.debug(f"[{program_name}] 設定内容: {program_config}") # 設定内容全体をログ出力

        try:
            # WebDriverManagerを使う場合 (execute_with_driverを使わない場合)
            with WebDriverManager() as driver:
                formatted_date = format_date(target_date)
                weekday = datetime.strptime(target_date, '%Y%m%d').weekday()
                program_time = format_program_time(program_config.get('name'), weekday, program_config.get('time'))

                target_urls = []
                # --- URL取得ロジック ---
                if "urls" in program_config:
                    urls_value = program_config["urls"]
                    # --- デバッグログ追加 ---
                    self.logger.debug(f"[{program_name}] 'urls' キー検出: {urls_value} (型: {type(urls_value)})")
                    if isinstance(urls_value, str):
                        target_urls = [url.strip() for url in urls_value.split(',') if url.strip()]
                        # --- デバッグログ追加 ---
                        self.logger.debug(f"[{program_name}] 文字列を分割後のURLリスト: {target_urls}")
                    # --- ↓↓↓ ここから2行のコメントアウト (#) を削除 ↓↓↓ ---
                    elif isinstance(urls_value, list): # ← ここの '#' を削除
                        target_urls = [str(url).strip() for url in urls_value if str(url).strip()] # ← ここの '#' を削除
                        self.logger.debug(f"[{program_name}] リスト処理後のURLリスト: {target_urls}") # ← ここの '#' を削除 (任意)
                    # --- ↑↑↑ ここまで修正 ↑↑↑ ---
                    else:
                        self.logger.warning(f"[{program_name}] 'urls' キーの値が予期しない型 ({type(urls_value)})。'url' キーを試します。")
                        if "url" in program_config:
                            url_value = program_config["url"]
                            if isinstance(url_value, str) and url_value.strip():
                                target_urls = [url_value.strip()]
                                self.logger.debug(f"[{program_name}] 'url' キーをフォールバックで使用: {target_urls}")
                elif "url" in program_config:
                    url_value = program_config["url"]
                    # --- デバッグログ追加 ---
                    self.logger.debug(f"[{program_name}] 'url' キー検出: {url_value}")
                    if isinstance(url_value, str) and url_value.strip():
                        target_urls = [url_value.strip()]
                    else:
                        self.logger.warning(f"[{program_name}] 'url' キーの値が無効です: {url_value}")
                else:
                    self.logger.error(f"[{program_name}] 設定に 'url' または 'urls' キーが見つかりません。")
                    return "failure", f"設定に 'url' または 'urls' キーが見つかりません"

                # --- デバッグログ追加 ---
                self.logger.debug(f"[{program_name}] 最終的な target_urls: {target_urls}")

                if not target_urls:
                    self.logger.error(f"[{program_name}] 処理の結果、有効な target_urls が設定されませんでした。")
                    return "failure", f"有効なURLが設定されていません" # ← ここでエラーが発生していた
                # --- URL取得ロジックここまで ---

                # _extract_tvtokyo_episode_urls は成功すればリスト、失敗すれば空リストを返す想定
                episode_urls = self._extract_tvtokyo_episode_urls(driver, target_urls, formatted_date, program_name)

                if not episode_urls:
                    # 放送が見つからない場合は failure
                    return "failure", f"放送が見つかりませんでした (日付: {formatted_date})"

                # --- 詳細取得とフォーマット ---
                all_formatted_outputs = []
                episode_details = []
                for url in episode_urls:
                    # _fetch_tvtokyo_episode_details は (title, url) または (None, None) などを返す
                    detail = self._fetch_tvtokyo_episode_details(driver, url, program_name)
                    if detail and detail[0] and detail[1]: # title と url が両方ある場合のみ
                        episode_details.append(detail) # 有効なものだけ追加

                if not episode_details: # 有効な詳細が一つもない場合
                    return "failure", f"有効なエピソード詳細が見つかりませんでした"

                for episode_title, episode_detail_url in episode_details:
                    formatted_output = self._format_program_output(
                        program_title=program_config['name'],
                        program_time=program_time,
                        episode_title=episode_title,
                        url_to_display=episode_detail_url
                    )
                    if formatted_output:
                        all_formatted_outputs.append(formatted_output)

                if not all_formatted_outputs: # フォーマット結果が空の場合
                    return "failure", f"有効なフォーマット済み出力が得られませんでした"

                # 成功
                # self.logger.info(f"{program_name} の詳細情報 ({len(all_formatted_outputs)} 件) を取得しました") # 完了ログはデコレータに任せる (DEBUGレベルで出力)
                return "success", all_formatted_outputs

        except Exception as e:
            # WebDriverManager の外、または予期せぬエラー
            self.logger.error(f"番組情報取得中にエラー: {e} - {program_name}", exc_info=True)
            return "failure", f"処理中にエラー: {e}"

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

                # 少し待機（動的コンテンツ読み込みのため）
                time.sleep(1) # 必要に応じて調整

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
        status = "failure" # デフォルト
        data_or_message = "不明なエラー" # デフォルト

        if task_type == 'nhk':
            scraper = NHKScraper(programs)
            status, data_or_message = scraper.get_program_info(program_name, target_date)
        elif task_type == 'tvtokyo':
            scraper = TVTokyoScraper(programs)
            status, data_or_message = scraper.get_program_info(program_name, target_date)
        else:
            process_logger.error(f"不明なタスクタイプです: {task_type}")
            return program_name, "failure", f"不明なタスクタイプ: {task_type}" # タプルで返す

        # scraper.get_program_info の結果をタプルで返す
        return program_name, status, data_or_message

    except Exception as e:
        process_logger.error(f"{program_name} の情報取得プロセスで予期せぬエラー: {e}", exc_info=True)
        # プロセスレベルのエラーも failure タプルで返す
        return program_name, "failure", f"プロセスエラー: {e}"

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
                    progress_message = "" # 進捗行に表示するメッセージ

                    # fetch_result が None でないことを確認 (通常はタプルが返るはず)
                    if fetch_result is not None:
                        program_name, status, data_or_message = fetch_result

                        if status == "success":
                            # 成功した場合
                            result_count_str = ""
                            if isinstance(data_or_message, list):
                                result_count_str = f" ({len(data_or_message)}件)"
                            elif isinstance(data_or_message, str) and data_or_message:
                                result_count_str = " (1件)"

                            progress_message = f"{program_name} 完了{result_count_str}"

                            # 成功データを results に追加
                            if data_or_message is not None:
                                if isinstance(data_or_message, list):
                                    results.extend(res for res in data_or_message if isinstance(res, str))
                                elif isinstance(data_or_message, str):
                                    results.append(data_or_message)

                        elif status == "failure":
                            # 失敗した場合、理由メッセージを表示に含める
                            failure_reason = data_or_message if isinstance(data_or_message, str) else "詳細不明"
                            # 長すぎるメッセージは切り詰めるなどしても良い
                            max_len = 60
                            if len(failure_reason) > max_len:
                                failure_reason = failure_reason[:max_len] + "..."
                            progress_message = f"{program_name} 失敗: {failure_reason}"
                        else:
                            # 予期しないステータス
                            progress_message = f"{program_name} 未知の状態 ({status})"
                            global_logger.warning(f"不明なステータスを受け取りました: {fetch_result}")

                    else:
                        # fetch_program_info が None を返した場合 (基本的にはないはず)
                        progress_message = "不明なタスクでエラー発生"
                        global_logger.error("fetch_program_info が None を返しました")

                    # 進捗表示 (1行にまとめる)
                    print(f"進捗: {processed_tasks}/{total_tasks} ({progress_message}) （経過時間：{elapsed_time:.0f}秒）")

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
