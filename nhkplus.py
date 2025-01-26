import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import re
import sys
from datetime import datetime, timedelta
import os

# デフォルトのタイムアウト時間
DEFAULT_TIMEOUT = int(os.getenv("WEBDRIVER_TIMEOUT", 10))  # タイムアウト時間を環境変数から取得、デフォルトは10秒

# ページのロード完了を待つためのカスタム expected_condition
class CustomExpectedConditions:
    @staticmethod
    def page_is_ready():
        """ページが完全にロードされたことを確認する"""
        return lambda driver: driver.execute_script("return document.readyState") == "complete"


# 取得対象の番組リスト (番組名, リストページのURL) を改行区切りで定義
# -> BS世界のドキュメンタリー(火 or 水)は日付記載が無いため手動
#       https://www.nhk.jp/p/wdoc/ts/88Z7X45XZY/list/
PROGRAMS_CONFIG = """
国際報道 2025,https://www.nhk.jp/p/kokusaihoudou/ts/8M689W8RVX/list/
キャッチ!世界のトップニュース,https://www.nhk.jp/p/catchsekai/ts/KQ2GPZPJWM/list/
みみより!解説,https://www.nhk.jp/p/ts/X67KZLM3P6/list/
視点・論点,https://www.nhk.jp/p/ts/Y5P47Z7YVW/list/
所さん!事件ですよ,https://www.nhk.jp/p/jikentokoro/ts/G69KQR33PG/list/
クローズアップ現代,https://www.nhk.jp/p/gendai/ts/R7Y6NGLJ6G/list/
新プロジェクトX,https://www.nhk.jp/p/ts/P1124VMJ6R/list/
サタデーウオッチ9,https://www.nhk.jp/p/ts/7K78K8ZNJV/list/
NHKスペシャル,https://www.nhk.jp/p/special/ts/2NY2QQLPM3/list/
ドキュメント72時間,https://www.nhk.jp/p/72hours/ts/W3W8WRN8M3/list/
映像の世紀バタフライエフェクト,https://www.nhk.jp/p/butterfly/ts/9N81M92LXV/list/
BSスペシャル,https://www.nhk.jp/p/bssp/ts/6NMMPMNK5K/list/
漫画家イエナガの複雑社会を超定義,https://www.nhk.jp/p/ts/1M3MYJGG6G/list/
時論公論,https://www.nhk.jp/p/ts/4V23PRP3YR/list/
"""

def parse_programs_config(config_str):
    """PROGRAMS_CONFIG文字列をパースして、番組名とURLの辞書を生成する"""
    programs = {}
    for line in config_str.splitlines():
        line = line.strip()
        if line and not line.startswith("#"): # 空行とコメント行を無視
            try:
                program_name, list_url = line.split(",", 1)  # 最初のカンマで分割
                programs[program_name.strip()] = list_url.strip()
            except ValueError:
                print(f"不正な形式の行をスキップ: {line}")
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
        print(f"要素取得エラーが発生しました: {e}")
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

def get_formatted_episode_info(driver, program_title, episode_url):
    """エピソードページから番組情報と配信URLを整形して出力する"""
    try:
        driver.get(episode_url)
        WebDriverWait(driver, DEFAULT_TIMEOUT).until(CustomExpectedConditions.page_is_ready())
        target_element = WebDriverWait(driver, DEFAULT_TIMEOUT).until(
            EC.presence_of_element_located((By.CLASS_NAME, 'title'))
        )
        episode_title = target_element.text.strip()

        if program_title == "BSスペシャル":
            program_time = "（NHK 22:45-23:35）"
            final_url = driver.current_url
            formatted_output = f"●{program_title}{program_time}\n"
            formatted_output += f"・{episode_title}\n"
            formatted_output += f"{final_url}\n"
            return formatted_output

        eyecatch_div = WebDriverWait(driver, DEFAULT_TIMEOUT).until(
            EC.presence_of_element_located((By.CLASS_NAME, 'gc-images.is-medium.eyecatch'))
        )
        a_tag = eyecatch_div.find_element(By.TAG_NAME, 'a')

        if a_tag and 'href' in a_tag.get_attribute('outerHTML'):
            image_link = a_tag.get_attribute('href')
            driver.get(image_link)
            WebDriverWait(driver, DEFAULT_TIMEOUT).until(CustomExpectedConditions.page_is_ready())
            time_element = WebDriverWait(driver, DEFAULT_TIMEOUT).until(
                EC.presence_of_element_located((By.CLASS_NAME, "stream_panel--info--meta"))
            )
            time_text = time_element.text.strip()
            start_ampm, start_time, end_ampm, end_time = _extract_time_info(time_text)
            if start_time and end_time:
                # 時刻を24時間表記に変換
                start_time_24h = _convert_to_24h(start_ampm, start_time)
                end_time_24h = _convert_to_24h(end_ampm, end_time)
                program_time = f"（NHK {start_time_24h}-{end_time_24h}）"
            else:
                program_time = "（放送時間取得失敗）"
                print(f"時間の取得に失敗しました。取得した文字列: {time_text} - {program_title}, {episode_url}")

            final_url = driver.current_url
            formatted_output = f"●{program_title}{program_time}\n"
            formatted_output += f"・{episode_title}\n"
            formatted_output += f"{final_url}\n"
            return formatted_output
        else:
            print(f"画像リンクが見つかりませんでした: {program_title}, {episode_url}")
            return None
    except Exception as e:
        print(f"エラーが発生しました: {e} - {program_title}, {episode_url}")
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
        print("=" * 100 + f" 時間：{elapsed_time:.0f}秒、検索中 : {program_title}")
        driver.get(list_url)

        episode_url = extract_episode_info(driver, target_date, program_title)
        if episode_url:
            formatted_output = get_formatted_episode_info(driver, program_title, episode_url)
            if formatted_output:
                return formatted_output
            else:
                print(f"{program_title}の番組詳細の取得に失敗しました - {list_url}")
                return None
        else:
            print(f"{program_title}が見つかりませんでした - {list_url}")
            return None
    except Exception as e:
        print(f"エラーが発生しました: {e} - {program_title}, {list_url}")
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

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("日付を引数で指定してください (例: python script.py 20250124)")
        sys.exit(1)

    target_date = sys.argv[1]

    programs = parse_programs_config(PROGRAMS_CONFIG)

    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)

    output_file_path = os.path.join(output_dir, f"{target_date}_nhk.txt")
    start_time = time.time()  # 全処理の開始時間

    with open(output_file_path, "w", encoding="utf-8") as outfile:
        for program_title, list_url in programs.items():
            formatted_info = get_nhk_info_formatted(program_title, list_url, target_date, start_time)
            if formatted_info:
                outfile.write(formatted_info)
    end_time = time.time()  # 全処理の終了時間
    elapsed_time = end_time - start_time
    print(f"結果を {output_file_path} に出力しました。（時間：{elapsed_time:.0f}秒）")
