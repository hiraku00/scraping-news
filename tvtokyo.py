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

# 番組設定 (番組名: URLと放送時間)
PROGRAMS_CONFIG = {
    "モーサテ": {"url": "https://txbiz.tv-tokyo.co.jp/nms/special", "time": "05:45~07:05"},
    "WBS（特集）": {"url": "https://txbiz.tv-tokyo.co.jp/wbs/feature", "time": "22:00~22:58"},
    "WBS（トレたまneo）": {"url": "https://txbiz.tv-tokyo.co.jp/wbs/trend_tamago", "time": "22:00~22:58"},
}

DEFAULT_TIMEOUT = int(os.getenv("WEBDRIVER_TIMEOUT", 10))  # タイムアウト時間を環境変数から取得、デフォルトは10秒

class CustomExpectedConditions:
    @staticmethod
    def page_is_ready():
        """ページが完全にロードされたことを確認する"""
        return lambda driver: driver.execute_script("return document.readyState") == "complete"

def create_driver() -> webdriver.Chrome:
    """Selenium WebDriverを初期化して返す"""
    options = Options()
    # options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    return webdriver.Chrome(options=options)

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

def extract_episode_urls(driver: webdriver.Chrome, target_url: str, formatted_date: str) -> list:
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
                print(f"エピソード解析中にエラー: {e}")
        return urls
    except Exception as e:
        print(f"URL取得エラー: {e}")
        return []

def fetch_episode_details(driver: webdriver.Chrome, episode_url: str) -> tuple:
    """エピソードページからタイトルとURLを取得する"""
    try:
        driver.get(episode_url)
        WebDriverWait(driver, DEFAULT_TIMEOUT).until(CustomExpectedConditions.page_is_ready())
        title_element = WebDriverWait(driver, DEFAULT_TIMEOUT).until(
            EC.presence_of_element_located((By.ID, "Live_Episode_Detail_EpisodeItemFullTitle"))
        )
        return title_element.text.strip(), episode_url
    except Exception as e:
        print(f"エピソード詳細取得エラー: {e} - {episode_url}")
        return None, None

def fetch_program_details(target_date: str) -> str:
    """全番組の指定された日付の情報を取得してフォーマットする"""
    driver = create_driver()
    formatted_date = format_date(target_date)
    output = []
    start_time = time.time()  # 全処理の開始時間
    previous_time = start_time

    try:
        for program_name, config in PROGRAMS_CONFIG.items():
            if is_skip_day(program_name, target_date):
                continue

            weekday = datetime.strptime(target_date, '%Y%m%d').weekday()
            program_time = format_program_time(program_name, weekday, config["time"])

            current_time = time.time()
            elapsed_time = current_time - start_time # 全処理開始からの経過時間
            print("=" * 100 + f" 経過時間：{elapsed_time:.0f}秒、検索中 : {program_name}")

            episode_urls = extract_episode_urls(driver, config["url"], formatted_date)
            if not episode_urls:
                print(f"{program_name} のエピソードが見つかりませんでした")
                continue

            # 各エピソードの詳細を取得
            episode_details = [
                fetch_episode_details(driver, url) for url in episode_urls
            ]
            titles = "\n".join(f"・{title}" for title, _ in episode_details if title)
            urls = "\n".join(url for _, url in episode_details if url)


            # 出力をフォーマット
            output.append(f"●{program_name}{program_time}\n{titles}\n{urls}")

    finally:
        driver.quit()
    end_time = time.time() # 全処理の終了時間
    elapsed_time = end_time - start_time
    return "\n".join(output), elapsed_time

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("日付を引数で指定してください (例: python script.py 20250124)")
        sys.exit(1)

    target_date = sys.argv[1]
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    output_file_path = os.path.join(output_dir, f"{target_date}_tvtokyo.txt")

    result, elapsed_time = fetch_program_details(target_date)
    with open(output_file_path, "w", encoding="utf-8") as f:
        f.write(result)

    print(f"結果を {output_file_path} に出力しました。（経過時間：{elapsed_time:.0f}秒）")
