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
from common.base_scraper import BaseScraper
from common.episode_processor import EpisodeProcessor
from common.utils import (
    setup_logger, WebDriverManager, parse_programs_config,
    sort_blocks_by_time, Constants, format_date,
    format_program_time, extract_program_time_info
)
from common.CustomExpectedConditions import CustomExpectedConditions

class NHKScraper(BaseScraper):
    """NHKの番組情報をスクレイピングするクラス"""
    def __init__(self, config):
        super().__init__(config)
        self.episode_processor = EpisodeProcessor(self.logger)

    @BaseScraper.log_operation("番組情報の取得")
    def get_program_info(self, program_name: str, target_date: str) -> str | None:
        """指定された番組の情報を取得する"""
        if not self.validate_config(program_name):
            return None

        program_info = self.config.get(program_name)
        def scrape_operation(driver):
            episode_url = self._extract_nhk_episode_info(driver, target_date, program_name)
            if episode_url:
                return self._get_nhk_formatted_episode_info(driver, program_name, episode_url, program_info["channel"])
            return None

        return self.execute_with_driver(scrape_operation)

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
    ### 修正 ###: 戻り値の型アノテーションを list[str] | None に変更
    def get_program_info(self, program_name: str, target_date: str) -> list[str] | None:
        """指定された番組の情報を取得する"""
        if not self.validate_config(program_name):
            return None

        program_config = self.config.get(program_name)
        # BaseScraper に execute_with_driver がある想定だが、提供コードにはないので
        # WebDriverManager を直接使う形で修正 (もし execute_with_driver があればそちらを使うべき)
        with WebDriverManager() as driver:
            try:
                formatted_date = format_date(target_date)
                weekday = datetime.strptime(target_date, '%Y%m%d').weekday()
                # 番組時間は共通のはずなのでここで決定
                program_time = format_program_time(program_config['name'], weekday, program_config['time'])
                self.logger.info(f"検索開始: {program_name}")

                target_urls = []
                # --- URL取得ロジック ---
                if "urls" in program_config:
                    urls_value = program_config["urls"]
                    if isinstance(urls_value, str):
                        target_urls = [url.strip() for url in urls_value.split(',') if url.strip()]
                    elif isinstance(urls_value, list):
                        target_urls = [str(url).strip() for url in urls_value if str(url).strip()]
                    else:
                        self.logger.warning(f"{program_name} の 'urls' キーの値が予期しない型 ({type(urls_value)}) です。'url' キーを試します。")
                        if "url" in program_config:
                            target_urls = [program_config["url"]]
                        else:
                            self.logger.error(f"{program_name} の設定に有効なURL ('urls' または 'url') が見つかりません。")
                            return None
                    if not target_urls:
                        self.logger.warning(f"{program_name} の 'urls' キーから有効なURLを取得できませんでした。'url' キーを試します。")
                        if "url" in program_config:
                            target_urls = [program_config["url"]]
                        else:
                            self.logger.error(f"{program_name} の設定に有効なURL ('urls' または 'url') が見つかりません。")
                            return None
                elif "url" in program_config:
                    target_urls = [program_config["url"]]
                else:
                    self.logger.error(f"{program_name} の設定に 'url' または 'urls' キーが見つかりません。")
                    return None

                if not target_urls:
                    self.logger.error(f"{program_name} の処理で有効な target_urls が設定されませんでした。")
                    return None
                # --- URL取得ロジックここまで ---

                episode_urls = self._extract_tvtokyo_episode_urls(driver, target_urls, formatted_date, program_name)

                if not episode_urls:
                    self.logger.warning(f"{program_name} の放送が見つかりませんでした。 (日付: {formatted_date}, URL: {target_urls})")
                    return None

                all_formatted_outputs = [] # 結果を格納するリスト
                episode_details = []
                # まず全ての詳細を取得試行
                for url in episode_urls:
                    detail = self._fetch_tvtokyo_episode_details(driver, url, program_name)
                    if detail: # (title, url) のタプル、または None
                        episode_details.append(detail)

                # 有効な詳細情報のみを抽出 (title と url が両方存在する)
                valid_details = [(title, url) for title, url in episode_details if title and url]

                if not valid_details:
                    self.logger.warning(f"{program_name} の有効なエピソード詳細が見つかりませんでした。")
                    return None # 有効なものが一つもなければ None

                # 有効な各エピソードについて出力をフォーマット
                for episode_title, episode_detail_url in valid_details:
                    formatted_output = self._format_program_output(
                        program_title=program_config['name'], # 番組名は共通
                        program_time=program_time,         # 番組時間も共通
                        episode_title=episode_title,       # 各エピソードのタイトル
                        url_to_display=episode_detail_url  # 各エピソードのURL
                    )
                    if formatted_output: # フォーマット成功時のみ追加
                        all_formatted_outputs.append(formatted_output)
                        self.logger.info(f"{program_name} のエピソード情報をフォーマットしました: {episode_title}")

                if not all_formatted_outputs:
                    # ループは回ったが、何らかの理由でフォーマット結果が空の場合
                    self.logger.warning(f"{program_name} について有効なフォーマット済み出力が得られませんでした。")
                    return None

                # ログメッセージを少し変更 (件数を表示)
                self.logger.info(f"{program_name} の詳細情報 ({len(all_formatted_outputs)} 件) を取得しました")
                return all_formatted_outputs # フォーマットされた文字列のリストを返す

            except Exception as e:
                self.logger.error(f"番組情報取得中にエラー: {e} - {program_name}", exc_info=True)
                return None

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

def fetch_program_info(args: tuple[str, str, dict, str]) -> str | list[str] | None:
    """並列処理用のラッパー関数"""
    task_type, program_name, programs, target_date = args
    # ここで setup_logger は呼ばない。モジュールレベルの logger を使う。

    try:
        result = None # 初期化
        scraper = None
        if task_type == 'nhk':
            scraper = NHKScraper(programs)
            result = scraper.get_program_info(program_name, target_date)
        elif task_type == 'tvtokyo':
            scraper = TVTokyoScraper(programs)
            result = scraper.get_program_info(program_name, target_date)
        else:
            logger.error(f"不明なタスクタイプです: {task_type}")
            return None

        # --- ログ出力は BaseScraper のデコレータに任せる方針でも良い ---
        # scraper.get_program_info が None を返した場合のログはデコレータ側で出力される想定
        # if result is None:
        #     logger.warning(f"{program_name} の情報の取得に失敗しました。")

        return result

    except Exception as e:
        # scraper 内でもエラーログは出るはずだが、プロセスレベルでのエラーも記録
        logger.error(f"{program_name} の情報取得プロセスで予期せぬエラー: {e}", exc_info=True)
        return None

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
    """結果を番組ブロックごとに分割し、時間順にソートする (logger を引数で受け取らない)"""
    # モジュールレベルの logger を使用
    logger.info(f"【後処理開始】結果の分割とソート...（経過時間：{get_elapsed_time(start_time):.0f}秒）")

    # None を除外し、リストの場合は展開
    flat_results = []
    for res in results:
        if isinstance(res, list):
            flat_results.extend(r for r in res if isinstance(r, str)) # 文字列のみ追加
        elif isinstance(res, str):
            flat_results.append(res)
    logger.debug(f"有効な結果件数: {len(flat_results)}")

    blocks = []
    current_block = []
    for line in flat_results:
        # ● の前に半角スペースが入るように修正 (_format_program_output 側で対応済み)
        if line.startswith('● '): # ヘッダー行の判定を修正
            if current_block:
                blocks.append('\n'.join(current_block))
            current_block = [line] # 新しいブロックを開始
        # ヘッダー行以外で、かつブロックが開始されている場合
        elif current_block:
             current_block.append(line)
        # ヘッダーなしで始まった場合 (通常は発生しないはず)
        else:
             logger.warning(f"ヘッダーなしで始まる行を検出、スキップします: {line[:50]}...")

    if current_block:
        blocks.append('\n'.join(current_block))

    logger.info(f"番組ブロックの分割完了: {len(blocks)} ブロック")
    logger.info(f"番組ブロックを時間順にソート中...")

    # ブロックをソート (sort_blocks_by_time は utils にある)
    sorted_blocks = sort_blocks_by_time(blocks)
    logger.info(f"番組ブロックのソート完了（経過時間：{get_elapsed_time(start_time):.0f}秒）")

    return sorted_blocks

def main():
    """メイン関数"""
    # --- Logger Setup ---
    # main 関数の最初で一度だけ呼び出す
    # これにより、このスクリプト全体（インポートされたモジュール含む）の基本的なログ設定が行われる
    global_logger = setup_logger(level=logging.INFO) # INFOレベル以上に設定
    # ---------------------

    if len(sys.argv) != 2:
        global_logger.error("日付引数がありません。")
        print("日付を引数で指定してください (例: python script.py 20250124)")
        sys.exit(1)

    target_date = sys.argv[1]
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    output_file_path = os.path.join(output_dir, f"{target_date}.txt")

    start_time = time.time()
    global_logger.info("=== scraping-news 処理開始 ===")
    global_logger.info(f"対象日付: {target_date}")

    try:
        # parse_programs_config は utils の関数 (内部でモジュールロガー使用)
        nhk_programs = parse_programs_config('ini/nhk_config.ini')
        tvtokyo_programs = parse_programs_config('ini/tvtokyo_config.ini')

        if not nhk_programs and not tvtokyo_programs:
             global_logger.error("設定ファイルの読み込みに失敗したか、設定が空です。処理を終了します。")
             sys.exit(1)

        # process_scraping は変更なし
        tasks = process_scraping(target_date, nhk_programs or {}, tvtokyo_programs or {})
        total_tasks = len(tasks)
        processed_tasks = 0
        results = []

        if total_tasks == 0:
             global_logger.warning("実行するタスクがありません。")
        else:
            global_logger.info(f"並列処理を開始します ({total_tasks} タスク)")
            # multiprocessing.Pool を使う場合、サブプロセスでもログ設定が引き継がれるか確認が必要
            # サブプロセス側 (fetch_program_info) でも logging.getLogger(__name__) で取得すれば
            # 基本的にはルートロガーの設定が使われるはず
            with multiprocessing.Pool() as pool:
                for result_item in pool.imap_unordered(fetch_program_info, tasks):
                    if result_item is not None:
                        results.append(result_item)

                    processed_tasks += 1
                    elapsed_time = get_elapsed_time(start_time)
                    print(f"\r進捗: {processed_tasks}/{total_tasks}（経過時間：{elapsed_time:.0f}秒）", end="", flush=True)
            print() # 進捗表示の後に改行
            global_logger.info("並列処理が完了しました。")

        # 結果の集計とソート
        if not results:
            global_logger.warning("有効な番組情報が一件も見つかりませんでした。")
            print("有効な番組情報が見つからなかったため、ファイルは作成されませんでした。")
        else:
            # process_and_sort_results, write_results_to_file は内部でモジュールロガーを使用
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
