import os
import webbrowser
import re
import sys
import time
from common.utils import load_config, setup_logger, parse_programs_config, Constants

logger = setup_logger(__name__)

def extract_urls_from_file(file_path: str) -> list[str]:
    """テキストファイルからURLを抽出する"""
    urls = []
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            for line in file:
                url_match = re.search(r'https?://[^\s]+', line)
                if url_match:
                    urls.append(url_match.group(0))
                    logger.debug(f"URLを抽出しました: {url_match.group(0)}")
        logger.info(f"ファイル {file_path} からURLを抽出しました。")
    except FileNotFoundError:
        logger.error(f"ファイル {file_path} が見つかりませんでした。")
        raise
    except Exception as e:
        logger.error(f"ファイル {file_path} からのURL抽出中にエラーが発生しました: {e}")
        raise
    return urls

def open_urls_from_config(config_programs: dict, program_name: str, block_urls: list[str]) -> bool:
    """設定ファイルのURL (一覧) とブロック内のURL (詳細) を開く
       戻り値:  True: 正常に処理 (番組が存在), False: 番組が設定に存在しない
    """

    if program_name not in config_programs:
        logger.warning(f"設定ファイルに {program_name} のURLが見つかりませんでした")
        return False

    program_config = config_programs[program_name]
    list_page_url = None

    # WBS の場合は urls キーから最初の URL を取得、それ以外は url キーから取得
    if isinstance(program_config, dict):
        if program_name == Constants.Program.WBS_PROGRAM_NAME and 'urls' in program_config:
            list_page_url = program_config['urls'][0]  # 最初の URL (通常は feature)
            # 詳細ページに trend_tamago が含まれていたら、一覧ページも trend_tamago にする
            for detail_url in block_urls:
                if "trend_tamago" in detail_url:
                    list_page_url = program_config['urls'][1]  # 2番目の URL (trend_tamago)
                    break  # 一つ見つかったらループを抜ける
        elif 'url' in program_config:
            list_page_url = program_config['url']

    if not list_page_url:
        logger.error(f"{program_name} の一覧ページURLが設定されていません。")
        return False

    # 一覧ページを開く (WBS でも最初に一覧ページを開く)
    logger.info(f"{program_name} の一覧ページ: {list_page_url} を開きます")
    webbrowser.open(list_page_url)

    # WBSの特殊処理 (詳細ページを開く)
    if program_name == Constants.Program.WBS_PROGRAM_NAME:
        for detail_url in block_urls:
            if "feature" in detail_url or "trend_tamago" in detail_url:
                logger.info(f"{detail_url} を開きます")
                webbrowser.open(detail_url)
                time.sleep(Constants.Time.SLEEP_SECONDS)
        return True

    # 詳細ページを開く
    for detail_url in block_urls:
        logger.info(f"{program_name} の詳細ページ: {detail_url} を開きます")
        webbrowser.open(detail_url)

    return True

def process_program_block(block: str, nhk_programs: dict, tvtokyo_programs: dict) -> None:
    """番組ブロックを処理する"""
    lines = block.strip().split('\n')
    if not lines:
        return

    program_info = lines[0].strip()
    program_name = program_info.split("(")[0].strip()  # 番組名

    block_urls = []
    for line in lines:
        url_match = re.search(r'https?://[^\s]+', line)
        if url_match:
            block_urls.append(url_match.group(0))

    processed = False
    if program_name in nhk_programs:
        processed = open_urls_from_config(nhk_programs, program_name, block_urls)
    elif program_name in tvtokyo_programs:
        processed = open_urls_from_config(tvtokyo_programs, program_name, block_urls)
    else:
        logger.warning(f"番組 {program_name} は設定ファイルに存在しません")
        # 設定ファイルに存在しない場合、block_urls が空でない場合にのみURLを開く
        if block_urls:
            logger.info(f"出力ファイルのURL ({program_name}):")
            for url in block_urls:
                logger.info(f"{url} を開きます")
                webbrowser.open(url)
            processed = True

    if processed:
        time.sleep(Constants.Time.SLEEP_SECONDS)

def main():
    """メイン関数"""
    if len(sys.argv) != 2:
        print("日付を引数で指定してください (例: python script.py 20250124)")
        sys.exit(1)

    date_input = sys.argv[1]
    output_dir = 'output'
    output_file_path = os.path.join(output_dir, f"{date_input}.txt")

    nhk_config_path = 'ini/nhk_config.ini'
    tvtokyo_config_path = 'ini/tvtokyo_config.ini'

    try:
        nhk_programs = parse_programs_config(nhk_config_path)
        tvtokyo_programs = parse_programs_config(tvtokyo_config_path)
    except Exception as e:
        logger.error(f"設定ファイルの読み込みに失敗しました: {e}")
        sys.exit(1)

    try:
        with open(output_file_path, 'r', encoding='utf-8') as file:
            content = file.read()
    except FileNotFoundError:
        print(f"エラー: 指定された出力ファイル {output_file_path} は存在しません。")
        sys.exit(1)
    except Exception as e:
        logger.error(f"出力ファイル {output_file_path} の読み込みに失敗しました: {e}")
        sys.exit(1)

    program_blocks = content.split("●")[1:]

    for block in program_blocks:
        process_program_block(block, nhk_programs, tvtokyo_programs)

if __name__ == "__main__":
    main()
