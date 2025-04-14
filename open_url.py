import os
import webbrowser
import re
import sys
import time
import logging # logging をインポート
# setup_logger, parse_programs_config, Constants をインポート
from common.utils import setup_logger, parse_programs_config, Constants

# --- モジュールレベルのロガーを取得 ---
logger = logging.getLogger(__name__)
# logger = setup_logger(__name__) # <-- グローバルスコープでの呼び出しを削除

def extract_urls_from_file(file_path: str) -> list[str]:
    """テキストファイルからURLを抽出する"""
    urls = []
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            for line in file:
                # 行頭が "・" でない場合（ヘッダー行など）はスキップした方が安全かもしれない
                # if not line.strip().startswith("・"): continue
                # URL抽出の正規表現を改善 (空白や括弧などで区切られる場合を考慮)
                url_matches = re.findall(r'https?://[^\s"\'<>]+', line)
                if url_matches:
                    for url in url_matches:
                        # 末尾の不要な文字（例: `。」`など）があれば除去する処理を追加しても良い
                        cleaned_url = url.rstrip('。、」)')
                        urls.append(cleaned_url)
                        logger.debug(f"URLを抽出しました: {cleaned_url}")
        logger.info(f"ファイル {file_path} からURL ({len(urls)}件) を抽出しました。")
    except FileNotFoundError:
        logger.error(f"ファイル {file_path} が見つかりませんでした。")
        raise
    except Exception as e:
        logger.error(f"ファイル {file_path} からのURL抽出中にエラーが発生しました: {e}", exc_info=True)
        raise
    # 重複を除去して返す (順序は維持されない可能性あり)
    unique_urls = sorted(list(set(urls)))
    logger.info(f"重複を除いたユニークなURLは {len(unique_urls)} 件です。")
    return unique_urls


def open_urls_from_config(config_programs: dict, program_name: str, block_urls: list[str]) -> bool:
    """設定ファイルのURL (一覧) とブロック内のURL (詳細) を開く"""
    logger = logging.getLogger(__name__) # モジュールロガー

    # ★キー検索直前のログ★
    logger.debug(f"設定検索試行: 検索キー='{program_name}', 検索対象辞書キー={list(config_programs.keys())}")

    if program_name not in config_programs:
        # logger.warning(f"設定ファイルに '{program_name}' の情報が見つかりませんでした。出力ファイルのURLのみ開きます。")
        # if block_urls:
        #     for url in block_urls:
        #         logger.info(f"出力ファイルのURL ('{program_name}'): {url} を開きます")
        #         webbrowser.open(url)
        #         time.sleep(Constants.Time.SLEEP_SECONDS)
        #     return True
        # else:
        #     logger.warning(f"'{program_name}' ブロック内にもURLが見つかりませんでした。")
        #     return False
        return False

    program_config = config_programs[program_name]
    list_page_urls = [] # 一覧ページURLをリストで扱う

    # 設定から一覧ページURLを取得
    if isinstance(program_config, dict):
        if 'urls' in program_config and isinstance(program_config['urls'], list) and program_config['urls']:
            list_page_urls = program_config['urls'] # 設定のURLリストをそのまま使う
        elif 'url' in program_config: # 古い形式（urlキーのみ）へのフォールバック
            list_page_urls = [program_config['url']]
    else:
        logger.error(f"'{program_name}' の設定データ形式が不正です。")
        return False

    if not list_page_urls:
        logger.error(f"'{program_name}' の一覧ページURLが設定から取得できませんでした。")
        # 一覧ページが開けなくても詳細ページは試みる
    else:
        # --- 一覧ページを開くロジック ---
        # WBSの場合、trend_tamagoが含まれていればそちらを優先する
        url_to_open = list_page_urls[0] # デフォルトは最初のURL
        if program_name == Constants.Program.WBS_PROGRAM_NAME and len(list_page_urls) > 1:
            if any("trend_tamago" in detail_url for detail_url in block_urls):
                # trend_tamago らしきURLがあれば2番目を開く (iniでの順序依存)
                url_to_open = list_page_urls[1]
                logger.debug("トレたまURLが含まれるため、WBS一覧ページを2番目のURLに変更。")

        logger.info(f"'{program_name}' の一覧ページ: {url_to_open} を開きます")
        webbrowser.open(url_to_open)

    # --- 詳細ページ（ブロック内のURL）を開くロジック ---
    if not block_urls:
        logger.info(f"'{program_name}' ブロック内に開くべき詳細URLが見つかりませんでした。")
        return True # 一覧ページを開けた（または試みた）のでTrue

    opened_count = 0
    for detail_url in block_urls:
        # 開いた一覧ページURLと同じ詳細URLはスキップ
        if detail_url == url_to_open: # url_to_openと比較
            logger.debug(f"開いた一覧ページと同じURLのためスキップ: {detail_url}")
            continue
        logger.info(f"'{program_name}' の詳細ページ: {detail_url} を開きます")
        webbrowser.open(detail_url)
        opened_count += 1
        sleep_time = Constants.Time.SLEEP_SECONDS * 1.5 if program_name == Constants.Program.WBS_PROGRAM_NAME else Constants.Time.SLEEP_SECONDS
        time.sleep(sleep_time)

    logger.info(f"'{program_name}': 詳細ページを {opened_count} 件開きました。")
    return True

def process_program_block(block: str, nhk_programs: dict, tvtokyo_programs: dict) -> None:
    """番組ブロックを処理する"""
    lines = block.strip().split('\n')
    if not lines:
        logger.debug("空のブロックをスキップします。")
        return

    header_line = lines[0].strip()
    if not header_line.startswith("●"):
        logger.warning(f"ヘッダー行の形式が不正です。スキップします: {header_line[:50]}...")
        return

    # 番組名の抽出
    program_name_match = re.match(r"●(.*?)\s?\(", header_line) # ●直後からマッチ、スペースは任意
    if not program_name_match:
        program_name_match = re.match(r"●(.*)", header_line) # 括弧なしの場合
        if not program_name_match:
            logger.error(f"ヘッダーから番組名を抽出できませんでした: {header_line}")
            return
    program_name = program_name_match.group(1).strip()
    logger.info(f"--- ブロック処理開始: {program_name} ---")
    # ★抽出したキーを明確にログ出力★
    logger.debug(f"抽出された番組名 (キー検索用): >>>'{program_name}'<<<")

    # URL抽出、設定ファイル照合、URLオープン処理は変更なし
    block_urls = []
    for line in lines[1:]:
        url_matches = re.findall(r'https?://[^\s"\'<>]+', line)
        if url_matches:
            for url in url_matches:
                cleaned_url = url.rstrip('。、」)')
                block_urls.append(cleaned_url)
    logger.debug(f"ブロックから抽出したURL ({len(block_urls)}件): {block_urls}")

    # ★渡す辞書の内容もログ出力（キーのみ）★
    logger.debug(f"NHK設定辞書のキー: {list(nhk_programs.keys())}")
    logger.debug(f"テレ東設定辞書のキー: {list(tvtokyo_programs.keys())}")

    # 設定ファイルと照合してURLを開く
    processed_nhk = open_urls_from_config(nhk_programs, program_name, block_urls)
    processed_tvtokyo = False
    if not processed_nhk: # NHKで見つからなかった場合のみテレ東を試す
        processed_tvtokyo = open_urls_from_config(tvtokyo_programs, program_name, block_urls)

    if not processed_nhk and not processed_tvtokyo:
        logger.warning(f"'{program_name}' はNHK, テレ東のどちらの設定にも見つかりませんでした。")

    logger.info(f"--- ブロック処理終了: {program_name} ---")

def main():
    """メイン関数"""
    # --- Logger Setup ---
    global_logger = setup_logger(level=logging.INFO)
    # ---------------------

    if len(sys.argv) != 2:
        global_logger.error("日付引数がありません。")
        print("日付を引数で指定してください (例: python open-url.py 20250124)")
        sys.exit(1)

    date_input = sys.argv[1]
    global_logger.info("=== open-url 処理開始 ===")
    global_logger.info(f"対象日付: {date_input}")

    output_dir = 'output'
    output_file_path = os.path.join(output_dir, f"{date_input}.txt")

    nhk_config_path = 'ini/nhk_config.ini'
    tvtokyo_config_path = 'ini/tvtokyo_config.ini'

    try:
        # parse_programs_config は utils の関数 (内部でモジュールロガー使用)
        nhk_programs = parse_programs_config(nhk_config_path) or {} # None の場合は空辞書に
        tvtokyo_programs = parse_programs_config(tvtokyo_config_path) or {} # None の場合は空辞書に
        if not nhk_programs and not tvtokyo_programs:
            global_logger.warning("NHKとテレビ東京両方の設定ファイル読み込みに失敗、または設定が空です。")
            # 処理を継続するかどうかは要件による
            # sys.exit(1)

    except Exception as e:
        global_logger.error(f"設定ファイルの読み込み中にエラーが発生しました: {e}", exc_info=True)
        sys.exit(1)

    try:
        with open(output_file_path, 'r', encoding='utf-8') as file:
            content = file.read()
        global_logger.info(f"出力ファイル {output_file_path} を読み込みました。")
    except FileNotFoundError:
        global_logger.error(f"指定された出力ファイル {output_file_path} は存在しません。")
        print(f"エラー: 指定された出力ファイル {output_file_path} は存在しません。")
        sys.exit(1)
    except Exception as e:
        global_logger.error(f"出力ファイル {output_file_path} の読み込みに失敗しました: {e}", exc_info=True)
        sys.exit(1)

    # プログラムブロックの分割を改善 (空行や先頭の不要なスペースを考慮)
    # content.split("●") だと先頭の要素が空になる場合がある
    # 正規表現で●から始まるブロックを抽出する
    program_blocks = re.findall(r"(^●.*?)(?=^●|\Z)", content, re.MULTILINE | re.DOTALL)

    if not program_blocks:
        global_logger.warning("出力ファイルに処理対象の番組ブロックが見つかりませんでした。")
        print("処理対象の番組ブロックが見つかりませんでした。")
        sys.exit(0) # 正常終了として扱う

    global_logger.info(f"{len(program_blocks)}件の番組ブロックを処理します。")

    # 各ブロックを処理
    for block in program_blocks:
        # process_program_block は内部でモジュールロガーを使用
        process_program_block(block.strip(), nhk_programs, tvtokyo_programs)

    global_logger.info("=== open-url 処理終了 ===")


if __name__ == "__main__":
    main()
