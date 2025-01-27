import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import re
import sys
from datetime import datetime
import os
import multiprocessing
import logging
import configparser

# 設定ファイル読み込み
config = configparser.ConfigParser()
config.read('ini/nhk_config.ini', encoding='utf-8')

# デフォルトのタイムアウト時間
DEFAULT_TIMEOUT = int(config.get('settings', 'webdriver_timeout', fallback=10))

# ログ設定
# ログファイルへの出力設定を削除
# LOG_FILE = "log/nhk_scraper.log"
# logging.basicConfig(filename=LOG_FILE, level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', filemode='w', encoding='utf-8')

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


# ページのロード完了を待つためのカスタム expected_condition
class CustomExpectedConditions:
    @staticmethod
    def page_is_ready():
        """ページが完全にロードされたことを確認する"""
        return lambda driver: driver.execute_script("return document.readyState") == "complete"

def parse_programs_config():
    """設定ファイルから番組リストを読み込む"""
    programs = {}
    for section in config.sections():
        if section.startswith('program_'):
            program_name = config.get(section, 'name')
            list_url = config.get(section, 'url')
            programs[program_name.strip()] = list_url.strip()
    return programs


def extract_episode_info(driver, target_date, program_title):
    """リストページから指定された日付のエピソードURLを抽出する"""
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


def _extract_time_info(time_text):
    """文字列から時間部分を抽出する"""
    match = re.search(r'((午前|午後)?(\d{1,2}:\d{2}))-((午前|午後)?(\d{1,2}:\d{2}))', time_text)
    if match:
        start_ampm = match.group(2)
        start_time = match.group(3)
        end_ampm = match.group(5)
        end_time = match.group(6)
        return start_ampm, start_time, end_ampm, end_time
    else:
        return None, None, None, None


def _extract_program_time(driver, program_title, episode_url):
    """番組の放送時間を抽出する共通関数"""
    try:
        time_element = WebDriverWait(driver, DEFAULT_TIMEOUT).until(
            EC.presence_of_element_located((By.CLASS_NAME, "stream_panel--info--meta"))
        )
        time_text = time_element.text.strip()
        start_ampm, start_time, end_ampm, end_time = _extract_time_info(time_text)
        if start_time and end_time:
            # 時刻を24時間表記に変換
            start_time_24h = _convert_to_24h(start_ampm, start_time)
            end_time_24h = _convert_to_24h(end_ampm, end_time)
            return f"（NHK {start_time_24h}-{end_time_24h}）"
        else:
            logging.warning(f"時間の取得に失敗しました。取得した文字列: {time_text} - {program_title}, {episode_url}")
            return "（放送時間取得失敗）"
    except Exception as e:
        logging.error(f"放送時間情報の抽出に失敗しました: {e} - {program_title}, {episode_url}")
        return "（放送時間取得失敗）"



def get_formatted_episode_info(driver, program_title, episode_url):
    """エピソードページから番組情報と配信URLを整形して出力する"""
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
            # gc-images.is-medium.eyecatch が見つからない場合、iframeから情報を取得する
            try:
                iframe = WebDriverWait(driver, DEFAULT_TIMEOUT).until(
                    EC.presence_of_element_located((By.ID, 'eyecatchIframe'))
                )
                iframe_src = iframe.get_attribute('src')
                match = re.search(r'/st/(.*?)\?', iframe_src)
                if match:
                    extracted_id = match.group(1)
                    final_url = f"https://plus.nhk.jp/watch/st/{extracted_id}"
                    driver.get(final_url)  # iframeから取得したURLに遷移する
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
    """番組リストページから、指定された日付の番組情報を取得する"""
    # Seleniumの設定
    options = Options()
    options.add_argument("--headless")  # ヘッドレスモードを有効化
    options.add_argument("--disable-gpu")  # GPUを無効化
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(options=options)
    try:
        current_time = time.time()
        elapsed_time = current_time - start_time
        logging.info(f"検索開始: {program_title} (経過時間: {elapsed_time:.0f}秒)")
        driver.get(list_url)

        episode_url = extract_episode_info(driver, target_date, program_title)
        if episode_url:
            formatted_output = get_formatted_episode_info(driver, program_title, episode_url)
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


def _convert_to_24h(ampm, time_str):
    """午前/午後表記の時刻を24時間表記に変換するヘルパー関数"""
    hour, minute = map(int, time_str.split(":"))
    if ampm == "午後" and hour != 12:
        hour += 12
    if ampm == "午前" and hour == 12:
        hour = 0
    return f"{hour:02}:{minute:02}"


def fetch_program_info(args):
    """並列処理用のラッパー関数"""
    program_title, list_url, target_date, start_time = args
    return get_nhk_info_formatted(program_title, list_url, target_date, start_time)


def main():
    if len(sys.argv) != 2:
        print("日付を引数で指定してください (例: python script.py 20250124)")
        sys.exit(1)

    target_date = sys.argv[1]

    programs = parse_programs_config()

    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)

    output_file_path = os.path.join(output_dir, f"{target_date}_nhk.txt")
    start_time = time.time()  # 全処理の開始時間
    all_results = []

    # 並列処理の設定
    with multiprocessing.Pool() as pool:
        # 各番組の情報を取得するための引数を準備
        program_args = [(program_title, list_url, target_date, start_time) for program_title, list_url in programs.items()]
        # 進捗表示のためのカウンター
        total_tasks = len(program_args)
        processed_tasks = 0

        # 並列処理を実行し、結果を取得
        for result in pool.imap_unordered(fetch_program_info, program_args):
            if result:
                all_results.append(result)
            processed_tasks += 1
            print(f"\r進捗: {processed_tasks}/{total_tasks}\n", end="", flush=True)

    # 結果をファイルに書き出す
    with open(output_file_path, "w", encoding="utf-8") as outfile:
        for result in all_results:
            if result:
                outfile.write(result)

    end_time = time.time()  # 全処理の終了時間
    elapsed_time = end_time - start_time
    # logging.info(f"結果を {output_file_path} に出力しました。（時間：{elapsed_time:.0f}秒）") # この行を削除
    print(f"結果を {output_file_path} に出力しました。（時間：{elapsed_time:.0f}秒）")

if __name__ == "__main__":
    main()
