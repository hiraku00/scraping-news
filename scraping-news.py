import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime, timedelta
import os
import sys
import time
import multiprocessing
import logging
import configparser
import re

# 設定ファイル読み込み
nhk_config = configparser.ConfigParser()
nhk_config.read('ini/nhk_config.ini', encoding='utf-8')

tvtokyo_config = configparser.ConfigParser()
tvtokyo_config.read('ini/tvtokyo_config.ini', encoding='utf-8')

# デフォルトのタイムアウト時間
DEFAULT_TIMEOUT = 10

# ログ設定
console = logging.StreamHandler()
console.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console.setFormatter(formatter)
logging.getLogger('').addHandler(console)
logging.getLogger('').setLevel(logging.INFO)

# NHKスクレイピング関数群
class CustomExpectedConditions:
    @staticmethod
    def page_is_ready():
        return lambda driver: driver.execute_script("return document.readyState") == "complete"

def parse_nhk_programs_config():
    programs = {}
    for section in nhk_config.sections():
        if section.startswith('program_'):
            program_name = nhk_config.get(section, 'name')
            list_url = nhk_config.get(section, 'url')
            programs[program_name.strip()] = list_url.strip()
    return programs

def extract_nhk_episode_info(driver, target_date, program_title):
    try:
        WebDriverWait(driver, DEFAULT_TIMEOUT).until(CustomExpectedConditions.page_is_ready())
        episodes = WebDriverWait(driver, DEFAULT_TIMEOUT).until(
            EC.presence_of_all_elements_located((By.CLASS_NAME, 'gc-stream-panel-info'))
        )
        for episode in episodes:
            try:
                date_element = WebDriverWait(episode, DEFAULT_TIMEOUT).until(
                    EC.presence_of_element_located((By.CLASS_NAME, 'gc-stream-panel-info-title-firstbroadcastdate-date'))
                )
                year_element = WebDriverWait(date_element, DEFAULT_TIMEOUT).until(
                    EC.presence_of_element_located((By.CLASS_NAME, 'gc-atom-text-for-date-year'))
                )
                day_element = WebDriverWait(date_element, DEFAULT_TIMEOUT).until(
                    EC.presence_of_element_located((By.CLASS_NAME, 'gc-atom-text-for-date-day'))
                )
                year_text = year_element.text.strip()
                day_text = day_element.text.strip()
                date_text = f"{year_text}{day_text}"
            except:
                try:
                    date_element = WebDriverWait(episode, DEFAULT_TIMEOUT).until(
                        EC.presence_of_element_located((By.CLASS_NAME, 'gc-stream-panel-info-title'))
                    )
                    date_text = date_element.text.strip()
                except:
                    continue
            match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', date_text)
            if match:
                year, month, day = match.groups()
                episode_date = datetime(int(year), int(month), int(day))
                target_date_dt = datetime.strptime(target_date, '%Y%m%d')

                if episode_date == target_date_dt:
                    return episode.find_element(By.TAG_NAME, 'a').get_attribute("href")
    except Exception as e:
        logging.error(f"要素取得エラーが発生しました: {e} - {program_title}")
        return None
    return None

def get_nhk_formatted_episode_info(driver, program_title, episode_url):
    try:
        driver.get(episode_url)
        WebDriverWait(driver, DEFAULT_TIMEOUT).until(CustomExpectedConditions.page_is_ready())
        target_element = WebDriverWait(driver, DEFAULT_TIMEOUT).until(
            EC.presence_of_element_located((By.CLASS_NAME, 'title'))
        )
        episode_title = target_element.text.strip().encode('utf-8', 'ignore').decode('utf-8', 'replace')

        if program_title == "BSスペシャル":
            program_time = "（NHK 22:45-23:35）"
            final_url = driver.current_url
            formatted_output = f"●{program_title}{program_time}\n"
            formatted_output += f"・{episode_title}\n"
            formatted_output += f"{final_url}\n"
            logging.info(f"{program_title} の詳細情報を取得しました")
            return formatted_output

        try:
            eyecatch_div = WebDriverWait(driver, DEFAULT_TIMEOUT).until(
                EC.presence_of_element_located((By.CLASS_NAME, 'gc-images.is-medium.eyecatch'))
            )
            a_tag = eyecatch_div.find_element(By.TAG_NAME, 'a')
            image_link = a_tag.get_attribute('href')
            driver.get(image_link)
            WebDriverWait(driver, DEFAULT_TIMEOUT).until(CustomExpectedConditions.page_is_ready())
            program_time = _extract_program_time(driver, program_title, episode_url)
            final_url = driver.current_url
            formatted_output = f"●{program_title}{program_time}\n"
            formatted_output += f"・{episode_title}\n"
            formatted_output += f"{final_url}\n"
            logging.info(f"{program_title} の詳細情報を取得しました")
            return formatted_output

        except Exception as e:
            try:
                iframe = WebDriverWait(driver, DEFAULT_TIMEOUT).until(
                    EC.presence_of_element_located((By.ID, 'eyecatchIframe'))
                )
                iframe_src = iframe.get_attribute('src')
                match = re.search(r'/st/(.*?)\?', iframe_src)
                if match:
                    extracted_id = match.group(1)
                    final_url = f"https://plus.nhk.jp/watch/st/{extracted_id}"
                    driver.get(final_url)
                    WebDriverWait(driver, DEFAULT_TIMEOUT).until(CustomExpectedConditions.page_is_ready())
                    program_time = _extract_program_time(driver, program_title, episode_url)
                    formatted_output = f"●{program_title}{program_time}\n"
                    formatted_output += f"・{episode_title}\n"
                    formatted_output += f"{final_url}\n"
                    logging.info(f"iframeからURLを生成しました: {final_url} - {program_title}")
                    return formatted_output
                else:
                    logging.error(f"iframeからIDを抽出できませんでした: {program_title}, {episode_url} - {e}")
                    return None
            except Exception as iframe_e:
                logging.error(f"gc-images.is-medium.eyecatch も iframe も見つかりませんでした: {program_title}, {episode_url} - {e} - {iframe_e}")
                return None

    except Exception as e:
        logging.error(f"エラーが発生しました: {e} - {program_title}, {episode_url}")
        return None

def get_nhk_info_formatted(program_title, list_url, target_date, start_time):
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(options=options)
    try:
        current_time = time.time()
        elapsed_time = current_time - start_time
        logging.info(f"検索開始: {program_title} (経過時間: {elapsed_time:.0f}秒)")
        driver.get(list_url)

        episode_url = extract_nhk_episode_info(driver, target_date, program_title)
        if episode_url:
            formatted_output = get_nhk_formatted_episode_info(driver, program_title, episode_url)
            if formatted_output:
                return formatted_output
            else:
                logging.warning(f"{program_title}の番組詳細の取得に失敗しました - {list_url}")
                return None
        else:
            logging.warning(f"{program_title}が見つかりませんでした - {list_url}")
            return None
    except Exception as e:
        logging.error(f"エラーが発生しました: {e} - {program_title}, {list_url}")
        return None
    finally:
        driver.quit()

def _extract_program_time(driver, program_title, episode_url):
    if program_title == "国際報道 2025":
        return "（BS NHK 22:00-22:45）"
    try:
        time_element = WebDriverWait(driver, DEFAULT_TIMEOUT).until(
            EC.presence_of_element_located((By.CLASS_NAME, "stream_panel--info--meta"))
        )
        time_text = time_element.text.strip()
        start_ampm, start_time, end_ampm, end_time = _extract_time_info(time_text)
        if start_time and end_time:
            start_time_24h = _convert_to_24h(start_ampm, start_time)
            end_time_24h = _convert_to_24h(end_ampm, end_time)
            return f"（NHK {start_time_24h}-{end_time_24h}）"
        else:
            logging.warning(f"時間の取得に失敗しました。取得した文字列: {time_text} - {program_title}, {episode_url}")
            return "（放送時間取得失敗）"
    except Exception as e:
        logging.error(f"放送時間情報の抽出に失敗しました: {e} - {program_title}, {episode_url}")
        return "（放送時間取得失敗）"

def _extract_time_info(time_text):
    match = re.search(r'((午前|午後)?(\d{1,2}:\d{2}))-((午前|午後)?(\d{1,2}:\d{2}))', time_text)
    if match:
        start_ampm = match.group(2)
        start_time = match.group(3)
        end_ampm = match.group(5)
        end_time = match.group(6)
        return start_ampm, start_time, end_ampm, end_time
    else:
        return None, None, None, None

def _convert_to_24h(ampm, time_str):
    hour, minute = map(int, time_str.split(":"))
    if ampm == "午後" and hour != 12:
        hour += 12
    if ampm == "午前" and hour == 12:
        hour = 0
    return f"{hour:02}:{minute:02}"

# テレビ東京スクレイピング関数群
def parse_tvtokyo_programs_config():
    programs = {}
    for section in tvtokyo_config.sections():
        if section.startswith('program_'):
            program_name = tvtokyo_config.get(section, 'name')
            program_url = tvtokyo_config.get(section, 'url')
            program_time = tvtokyo_config.get(section, 'time')
            programs[program_name.strip()] = {"url": program_url.strip(), "time": program_time.strip()}
    return programs

def format_date(target_date: str) -> str:
    return f"{target_date[:4]}.{target_date[4:6]}.{target_date[6:8]}"

def is_skip_day(program_name: str, target_date: str) -> bool:
    weekday = datetime.strptime(target_date, '%Y%m%d').weekday()
    if program_name == "WBS（トレたまneo）" and weekday != 3:
        return True
    if weekday >= 5:
        return True
    return False

def format_program_time(program_name: str, weekday: int, default_time: str) -> str:
    if program_name.startswith("WBS"):
        return "（テレ東 22:00~22:58）" if weekday < 4 else "（テレ東 23:00~23:58）"
    return f"（テレ東 {default_time}）"

def extract_tvtokyo_episode_urls(driver: webdriver.Chrome, target_url: str, formatted_date: str, program_name: str) -> list:
    try:
        driver.get(target_url)
        WebDriverWait(driver, DEFAULT_TIMEOUT).until(CustomExpectedConditions.page_is_ready())
        episodes = WebDriverWait(driver, DEFAULT_TIMEOUT).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'div[id^="News_Detail__VideoItem__"]'))
        )
        urls = []
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)
        formatted_today = format_date(today.strftime('%Y%m%d'))
        formatted_yesterday = format_date(yesterday.strftime('%Y%m%d'))

        for episode in episodes:
            try:
                date_element = WebDriverWait(episode, 5).until(
                    lambda e: e.find_element(By.CSS_SELECTOR, 'span.sc-c564813-0.iCkNIF[role="presentation"]')
                )
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

            except Exception as e:
                logging.error(f"エピソード解析中にエラー: {e} - {program_name}")
        return urls
    except Exception as e:
        logging.error(f"URL取得エラー: {e} - {program_name}")
        return []

def fetch_tvtokyo_episode_details(driver: webdriver.Chrome, episode_url: str, program_name: str) -> tuple:
    try:
        driver.get(episode_url)
        WebDriverWait(driver, DEFAULT_TIMEOUT).until(CustomExpectedConditions.page_is_ready())
        title_element = WebDriverWait(driver, DEFAULT_TIMEOUT).until(
            EC.presence_of_element_located((By.ID, "Live_Episode_Detail_EpisodeItemFullTitle"))
        )
        return title_element.text.strip(), episode_url
    except Exception as e:
        logging.error(f"エピソード詳細取得エラー: {e} - {program_name}, {episode_url}")
        return None, None


# def fetch_tvtokyo_program_details(program_name, config, target_date, start_time):
#     driver = create_driver()
#     formatted_date = format_date(target_date)
#     output = []
#     program_start_time = time.time()

#     try:
#         if is_skip_day(program_name, target_date):
#             logging.info(f"{program_name} はスキップされました")
#             return None

#         weekday = datetime.strptime(target_date, '%Y%m%d').weekday()
#         program_time = format_program_time(program_name, weekday, config["time"])

#         current_time = time.time()
#         elapsed_time = current_time - start_time
#         logging.info(f"検索開始: {program_name} (経過時間: {elapsed_time:.0f}秒)")

#         list_url = config["url"]  # リストURLを取得
#         episode_urls = extract_tvtokyo_episode_urls(driver, list_url, formatted_date, program_name)
#         if not episode_urls:
#             # ログメッセージに番組名とURLを追加
#             logging.warning(f"{program_name} のエピソードが見つかりませんでした - {list_url}")
#             return None

#         episode_details = [
#             fetch_tvtokyo_episode_details(driver, url, program_name) for url in episode_urls
#         ]
#         titles = "\n".join(f"・{title}" for title, _ in episode_details if title)
#         urls = "\n".join(url for _, url in episode_details if url)

#         formatted_output = f"●{program_name}{program_time}\n{titles}\n{urls}\n"
#         logging.info(f"{program_name} の詳細情報を取得しました")
#         return formatted_output

#     except Exception as e:
#         logging.error(f"番組情報取得中にエラー: {e} - {program_name}")
#         return None

#     finally:
#         driver.quit()
#         program_end_time = time.time()
#         program_elapsed_time = program_end_time - program_start_time
#         logging.info(f"{program_name} の処理時間: {program_elapsed_time:.0f}秒")


def fetch_tvtokyo_program_details(program_name, config, target_date, start_time):
    driver = create_driver()
    formatted_date = format_date(target_date)
    list_url = config["url"]  # URL取得を前に移動

    try:
        if is_skip_day(program_name, target_date):
            logging.info(f"{program_name} はスキップされました")
            return None

        # 経過時間計算（NHKと同様の形式で検索開始時に表示）
        current_time = time.time()
        elapsed_time = current_time - start_time
        logging.info(f"検索開始: {program_name} (経過時間: {elapsed_time:.0f}秒)")

        weekday = datetime.strptime(target_date, '%Y%m%d').weekday()
        program_time = format_program_time(program_name, weekday, config["time"])

        episode_urls = extract_tvtokyo_episode_urls(driver, list_url, formatted_date, program_name)
        if not episode_urls:
            # NHKと同様の警告メッセージに変更
            logging.warning(f"{program_name}が見つかりませんでした - {list_url}")
            return None

        episode_details = [
            fetch_tvtokyo_episode_details(driver, url, program_name) for url in episode_urls
        ]
        titles = "\n".join(f"・{title}" for title, _ in episode_details if title)
        urls = "\n".join(url for _, url in episode_details if url)

        formatted_output = f"●{program_name}{program_time}\n{titles}\n{urls}\n"
        logging.info(f"{program_name} の詳細情報を取得しました")
        return formatted_output

    except Exception as e:
        logging.error(f"番組情報取得中にエラー: {e} - {program_name}")
        return None

    finally:
        driver.quit()
        # 処理時間のログ出力を削除（NHKと統一するため）


def fetch_program_info(args):
    """並列処理用のラッパー関数"""
    task_type, *rest = args
    if task_type == 'nhk':
        return fetch_nhk_program_info(rest)
    elif task_type == 'tvtokyo':
        return fetch_tvtokyo_program_info(rest)
    else:
        return None


def fetch_nhk_program_info(args):
    program_title, list_url, target_date, start_time = args
    return get_nhk_info_formatted(program_title, list_url, target_date, start_time)


def fetch_tvtokyo_program_info(args):
    program_name, config, target_date, start_time = args
    return fetch_tvtokyo_program_details(program_name, config, target_date, start_time)


def create_driver() -> webdriver.Chrome:
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    return webdriver.Chrome(options=options)

def extract_time_from_block(block):
    """番組ブロックから放送時間を抽出するヘルパー関数"""
    first_line = block.split('\n')[0]  # ブロックの最初の行を取得
    time_match = re.search(r'（(NHK|テレ東|BS NHK) (\d{2}:\d{2})', first_line)
    if time_match:
        broadcaster, time_str = time_match.groups()
        hour, minute = map(int, time_str.split(':'))
        return hour, minute
    return 25, 0  # 時間が抽出できない場合は最後にソート

def sort_blocks_by_time(blocks):
    """番組ブロックを放送時間順にソートする"""
    return sorted(blocks, key=extract_time_from_block)

def main():
    if len(sys.argv) != 2:
        print("日付を引数で指定してください (例: python script.py 20250124)")
        sys.exit(1)

    target_date = sys.argv[1]
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    output_file_path = os.path.join(output_dir, f"{target_date}.txt")

    start_time = time.time()
    nhk_programs = parse_nhk_programs_config()
    tvtokyo_programs = parse_tvtokyo_programs_config()

    # NHKとテレビ東京のタスクを1つのリストにまとめる
    tasks = []
    for program_title, list_url in nhk_programs.items():
        tasks.append(('nhk', program_title, list_url, target_date, start_time))
    for program_name, config in tvtokyo_programs.items():
        tasks.append(('tvtokyo', program_name, config, target_date, start_time))

    total_tasks = len(tasks)
    processed_tasks = 0

    results = []
    with multiprocessing.Pool() as pool:
        for result in pool.imap_unordered(fetch_program_info, tasks):
            if result:
                results.append(result)
            processed_tasks += 1
            print(f"\r進捗: {processed_tasks}/{total_tasks}\n", end="", flush=True)

    # 結果を番組ブロックごとに分割
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

    # 番組ブロックを時間順にソート
    sorted_blocks = sort_blocks_by_time(blocks)

    # ソートされた結果をファイルに書き込む
    with open(output_file_path, "w", encoding="utf-8") as f:
        for block in sorted_blocks:
            f.write(block + '\n')

    end_time = time.time()
    elapsed_time = end_time - start_time
    print(f"結果を {output_file_path} に出力しました。（経過時間：{elapsed_time:.0f}秒）")

if __name__ == "__main__":
    main()
