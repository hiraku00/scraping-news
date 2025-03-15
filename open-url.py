import os
import webbrowser
import re
import sys
import time
from common.utils import load_config, setup_logger, parse_programs_config

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

def open_urls_from_config(config_programs: dict, program_name: str, output_urls: list[str]) -> None:
    """設定ファイルのURLと出力されたURLを開く"""
    if program_name in config_programs:
        config_urls = config_programs[program_name]
        selected_config_url = None

        wbs_feature_url = None
        wbs_trend_tamago_url = None

        for program_config in config_urls:
            if "feature" in program_config['url']:
                wbs_feature_url = program_config['url']
            elif "trend_tamago" in program_config['url']:
                wbs_trend_tamago_url = program_config['url']

        if program_name == "WBS":
            has_feature_url = False
            has_trend_tamago_url = False
            for url in output_urls:
                if "feature" in url:
                    has_feature_url = True
                elif "trend_tamago" in url:
                    has_trend_tamago_url = True

            logger.info(f"設定ファイル内のURL (WBS):")

            if has_feature_url:
                selected_config_url = wbs_feature_url
                if selected_config_url:
                    logger.info(f"- {selected_config_url} (feature) を開きます")
                    webbrowser.open(selected_config_url)
            elif has_trend_tamago_url:
                selected_config_url = wbs_trend_tamago_url
                if selected_config_url:
                    logger.info(f"- {selected_config_url} (trend_tamago) を開きます")
                    webbrowser.open(selected_config_url)
            else:
                logger.info("- (出力ファイルにWBSのURLが見つかりませんでした)")

        else:
            selected_config_url = config_urls[0]['url']
            logger.info(f"設定ファイル内のURL ({program_name}): {selected_config_url} を開きます")
            # webbrowser.open() の直前でログ出力
            logger.debug(f"webbrowser.open() を呼び出し: {selected_config_url}")
            webbrowser.open(selected_config_url)

    else:
        logger.warning(f"設定ファイルに {program_name} のURLが見つかりませんでした")

    if output_urls:
        logger.info(f"出力ファイルのURL ({program_name}):")
        for url in output_urls:
            logger.info(f"{url} を開きます")
            # webbrowser.open() の直前でログ出力
            logger.debug(f"webbrowser.open() を呼び出し: {url}")
            webbrowser.open(url)
            time.sleep(2)
    else:
        logger.info(f"出力ファイルにURLが見つかりませんでした")

def process_program_block(block: str, nhk_programs: dict, tvtokyo_programs: dict) -> None:
    """番組ブロックを処理する"""
    lines = block.strip().split('\n')
    if lines:
        program_info = lines[0].strip()
        program_name = program_info.split("(")[0]

        block_urls = []
        for line in lines:
            url_match = re.search(r'https?://[^\s]+', line)
            if url_match:
                block_urls.append(url_match.group(0))

        if program_name in nhk_programs:
            open_urls_from_config(nhk_programs, program_name, block_urls)
        elif program_name in tvtokyo_programs:
            open_urls_from_config(tvtokyo_programs, program_name, block_urls)
        else:
            logger.warning(f"番組 {program_name} は設定ファイルに存在しません")
            # 設定ファイルに存在しない場合、block_urlsが空でない場合にのみURLを開く
            if block_urls:
                logger.info(f"出力ファイルのURL ({program_name}):")
                for url in block_urls:
                    logger.info(f"{url} を開きます")
                    webbrowser.open(url)
                    time.sleep(2)
            else:
                logger.info(f"出力ファイルに {program_name} のURLが見つかりませんでした")

def main():
    """メイン関数"""
    if len(sys.argv) != 2:
        print("日付を引数で指定してください (例: python script.py 20250124)")
        sys.exit(1)

    date_input = sys.argv[1]

    nhk_config_path = 'ini/nhk_config.ini'
    tvtokyo_config_path = 'ini/tvtokyo_config.ini'
    output_dir = 'output'

    output_file_path = os.path.join(output_dir, f"{date_input}.txt")

    try:
        nhk_config = load_config(nhk_config_path)
        tvtokyo_config = load_config(tvtokyo_config_path)
    except Exception as e:
        logger.error(f"設定ファイルの読み込みに失敗しました: {e}")
        sys.exit(1)

    nhk_programs = parse_programs_config(nhk_config_path)
    tvtokyo_programs = parse_programs_config(tvtokyo_config_path)
    
    try:
        output_urls = extract_urls_from_file(output_file_path)
    except Exception as e:
        logger.error(f"URLの抽出に失敗しました: {e}")
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
