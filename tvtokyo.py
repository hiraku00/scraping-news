import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime
import os
import sys
import time
import multiprocessing
import logging
import configparser

# 設定ファイル読み込み
config = configparser.ConfigParser()
config.read('ini/tvtokyo_config.ini', encoding='utf-8')

# デフォルトのタイムアウト時間
DEFAULT_TIMEOUT = int(config.get('settings', 'webdriver_timeout', fallback=10))

# ログ設定
# ログファイルへの出力設定を削除
# LOG_FILE = "log/tvtokyo_scraper.log"
# logging.basicConfig(filename=LOG_FILE, level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# コンソール出力用のハンドラを追加
console = logging.StreamHandler()
console.setLevel(logging.INFO)
# コンソール出力用ログフォーマット
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console.setFormatter(formatter)
# root loggerを取得して、ハンドラを追加
logging.getLogger('').addHandler(console)
# root loggerのレベルを設定（必要に応じて）
logging.getLogger('').setLevel(logging.INFO)



class CustomExpectedConditions:
    @staticmethod
    def page_is_ready():
        """ページが完全にロードされたことを確認する"""
        return lambda driver: driver.execute_script("return document.readyState") == "complete"

def create_driver() -> webdriver.Chrome:
    """Selenium WebDriverを初期化して返す"""
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    return webdriver.Chrome(options=options)


def parse_programs_config():
    """設定ファイルから番組リストを読み込む"""
    programs = {}
    for section in config.sections():
        if section.startswith('program_'):
            program_name = config.get(section, 'name')
            program_url = config.get(section, 'url')
            program_time = config.get(section, 'time')
            programs[program_name.strip()] = {"url": program_url.strip(), "time": program_time.strip()}
    return programs


def format_date(target_date: str) -> str:
    """指定された日付を yyyy.MM.dd 形式に変換する"""
    return f"{target_date[:4]}.{target_date[4:6]}.{target_date[6:8]}"

def is_skip_day(program_name: str, target_date: str) -> bool:
    """番組が特定の日付にスキップされるべきかを判定する"""
    weekday = datetime.strptime(target_date, '%Y%m%d').weekday()
    if program_name == "WBS（トレたまneo）" and weekday != 3:  # 木曜日以外はスキップ
        return True
    if weekday >= 5:  # 土日は全番組スキップ
        return True
    return False

def format_program_time(program_name: str, weekday: int, default_time: str) -> str:
    """番組の放送時間を曜日に応じてフォーマットする"""
    if program_name.startswith("WBS"):
        return "（テレ東 22:00~22:58）" if weekday < 4 else "（テレ東 23:00~23:58）"
    return f"（テレ東 {default_time}）"

def extract_episode_urls(driver: webdriver.Chrome, target_url: str, formatted_date: str, program_name: str) -> list:
    """指定されたURLと日付から該当するエピソードのURLリストを取得する"""
    try:
        driver.get(target_url)
        WebDriverWait(driver, DEFAULT_TIMEOUT).until(CustomExpectedConditions.page_is_ready())
        episodes = WebDriverWait(driver, DEFAULT_TIMEOUT).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'div[id^="News_Detail__VideoItem__"]'))
        )
        urls = []
        for episode in episodes:
            try:
                date_element = WebDriverWait(episode, 5).until(
                    lambda e: e.find_element(By.CSS_SELECTOR, 'span.sc-c564813-0.iCkNIF[role="presentation"]')
                )
                if date_element.text.strip() == formatted_date:
                    link = episode.find_element(By.CSS_SELECTOR, 'a[href*="post_"]').get_attribute("href")
                    urls.append(link)
            except Exception as e:
                logging.error(f"エピソード解析中にエラー: {e} - {program_name}")
        return urls
    except Exception as e:
        logging.error(f"URL取得エラー: {e} - {program_name}")
        return []

def fetch_episode_details(driver: webdriver.Chrome, episode_url: str, program_name: str) -> tuple:
    """エピソードページからタイトルとURLを取得する"""
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

def fetch_program_details(program_name, config, target_date, start_time):
    """特定の番組の情報を取得してフォーマットする"""
    driver = create_driver()
    formatted_date = format_date(target_date)
    output = []

    try:
        if is_skip_day(program_name, target_date):
                return None

        weekday = datetime.strptime(target_date, '%Y%m%d').weekday()
        program_time = format_program_time(program_name, weekday, config["time"])

        current_time = time.time()
        elapsed_time = current_time - start_time # 全処理開始からの経過時間
        logging.info(f"検索中 : {program_name} (経過時間: {elapsed_time:.0f}秒)")

        episode_urls = extract_episode_urls(driver, config["url"], formatted_date, program_name)
        if not episode_urls:
             logging.warning(f"{program_name} のエピソードが見つかりませんでした")
             return None

        # 各エピソードの詳細を取得
        episode_details = [
            fetch_episode_details(driver, url, program_name) for url in episode_urls
        ]
        titles = "\n".join(f"・{title}" for title, _ in episode_details if title)
        urls = "\n".join(url for _, url in episode_details if url)

        # 出力をフォーマット
        return f"●{program_name}{program_time}\n{titles}\n{urls}"

    except Exception as e:
       logging.error(f"番組情報取得中にエラー: {e} - {program_name}")
       return None

    finally:
        driver.quit()


def fetch_program_info(args):
    """並列処理用のラッパー関数"""
    program_name, config, target_date, start_time = args
    return fetch_program_details(program_name, config, target_date, start_time)

def main():
    if len(sys.argv) != 2:
        print("日付を引数で指定してください (例: python script.py 20250124)")
        sys.exit(1)

    target_date = sys.argv[1]
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    output_file_path = os.path.join(output_dir, f"{target_date}_tvtokyo.txt")

    start_time = time.time() # 全処理開始時間
    programs = parse_programs_config()

    # 並列処理の設定
    with multiprocessing.Pool() as pool:
        # 各番組の情報を取得するための引数を準備
        program_args = [(program_name, config, target_date, start_time) for program_name, config in programs.items()]
        # 進捗表示のためのカウンター
        total_tasks = len(program_args)
        processed_tasks = 0

        # 並列処理を実行し、結果を取得
        results = []
        for result in pool.imap_unordered(fetch_program_info, program_args):
            results.append(result)
            processed_tasks += 1
            print(f"\r進捗: {processed_tasks}/{total_tasks}\n", end="", flush=True)

    with open(output_file_path, "w", encoding="utf-8") as f:
        for result in results:
            if result:
                f.write(result + "\n")

    end_time = time.time() # 全処理の終了時間
    elapsed_time = end_time - start_time
    # logging.info(f"結果を {output_file_path} に出力しました。（経過時間：{elapsed_time:.0f}秒）") # この行を削除
    print(f"結果を {output_file_path} に出力しました。（経過時間：{elapsed_time:.0f}秒）")


if __name__ == "__main__":
    main()
