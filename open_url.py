import os
import webbrowser
import re
import sys
import time
import logging
from common.utils import setup_logger, parse_programs_config, Constants

logger = logging.getLogger(__name__)

def extract_content_type_from_url(url: str) -> str:
    """URLからWBSコンテンツタイプを抽出する"""
    # WBS関連のURLパターンをチェック
    patterns = [
        (r'/wbs/feature/', 'feature'),
        (r'/wbs/oa/', 'oa'),
        (r'/wbs/trend_tamago/', 'trend_tamago')
    ]

    for pattern, content_type in patterns:
        if pattern in url:
            return content_type

    return 'unknown'


def get_wbs_content_types_from_urls(block_urls: list[str]) -> set[str]:
    """ブロック内のURLからWBSコンテンツタイプを抽出する"""
    content_types = set()

    for url in block_urls:
        content_type = extract_content_type_from_url(url)
        if content_type != 'unknown':
            content_types.add(content_type)

    return content_types


def open_urls_from_config(config_programs: dict, program_name: str, block_urls: list[str]) -> bool:
    """【再修正】設定ファイルのURL (一覧) とブロック内のURL (詳細) をまとめて開く"""
    if program_name not in config_programs:
        return False

    program_config = config_programs[program_name]
    list_page_urls = []
    list_page_url_to_open = None # 開く一覧ページURL
    opened_any_url = False # 何かURLを開いたかどうかのフラグ

    # --- 1. 一覧ページURLの取得 ---
    if isinstance(program_config, dict):
        if 'urls' in program_config and isinstance(program_config['urls'], list) and program_config['urls']:
            list_page_urls = program_config['urls']
        elif 'url' in program_config:
            list_page_urls = [program_config['url']]
    else:
        logger.error(f"'{program_name}' の設定データ形式が不正です。")
        return False

    # --- 2. WBS番組の場合の特別処理 ---
    wbs_pages_to_open = [] # 開くべきWBSページのリスト

    if list_page_urls:
        try:
            # 定数が存在する場合のみWBS判定を行う
            if hasattr(Constants, 'Program') and hasattr(Constants.Program, 'WBS_PROGRAM_NAME'):
                wbs_program_name = Constants.Program.WBS_PROGRAM_NAME
                if program_name == wbs_program_name:
                    # WBS番組の場合、コンテンツタイプに基づいて適切なページを選択
                    content_types = get_wbs_content_types_from_urls(block_urls)

                    logger.debug(f"WBSコンテンツタイプ検出: {content_types}")

                    if content_types:
                        # 各コンテンツタイプに対応するページをリストアップ
                        for content_type in content_types:
                            if content_type == 'feature' and len(list_page_urls) > 0:
                                wbs_pages_to_open.append(list_page_urls[0])
                            elif content_type == 'trend_tamago' and len(list_page_urls) > 1:
                                wbs_pages_to_open.append(list_page_urls[1])
                            elif content_type == 'oa' and len(list_page_urls) > 2:
                                wbs_pages_to_open.append(list_page_urls[2])

                        if wbs_pages_to_open:
                            logger.info(f"WBS番組: コンテンツタイプ別ページを開きます - {len(wbs_pages_to_open)}件")
                        else:
                            logger.warning("WBS番組: 適切なコンテンツタイプが見つかりませんでした")
                    else:
                        logger.debug("WBS番組: ブロック内にWBS関連URLが見つかりませんでした")

                # WBS番組以外の場合の処理
                if program_name != wbs_program_name or not wbs_pages_to_open:
                    list_page_url_to_open = list_page_urls[0] if list_page_urls else None
            else:
                logger.debug("Constants.Program.WBS_PROGRAM_NAME未定義のためWBS判定スキップ。")
                list_page_url_to_open = list_page_urls[0] if list_page_urls else None

        except Exception as e:
            logger.error(f"WBSコンテンツタイプ処理中にエラー: {e}", exc_info=True)
            list_page_url_to_open = list_page_urls[0] if list_page_urls else None

        # WBS番組で複数のページを開く場合
        if wbs_pages_to_open:
            for i, page_url in enumerate(wbs_pages_to_open):
                logger.info(f"WBS番組ページ {i+1}/{len(wbs_pages_to_open)} を開きます: {page_url}")
                webbrowser.open(page_url)
                opened_any_url = True
        # 通常の番組またはWBSでページが選択された場合
        elif list_page_url_to_open:
            logger.info(f"'{program_name}' の一覧ページを開きます: {list_page_url_to_open}")
            webbrowser.open(list_page_url_to_open)
            opened_any_url = True
        else:
            logger.warning(f"'{program_name}' の一覧ページURL特定に失敗しました。")
    else:
        logger.warning(f"'{program_name}' の一覧ページURLが設定から取得できませんでした。")


    # --- 3. 開くべき「詳細URL」のリストを作成 ---
    detail_urls_to_open = []
    if block_urls:
        unique_block_urls = sorted(list(set(block_urls))) # 念のため重複除去
        for detail_url in unique_block_urls:
            # 一覧ページと同じURLはスキップ
            if list_page_url_to_open and detail_url == list_page_url_to_open:
                continue
            detail_urls_to_open.append(detail_url)

    # --- 4. 詳細URLをまとめて開く ---
    if detail_urls_to_open:
        logger.info(f"'{program_name}' の詳細ページ ({len(detail_urls_to_open)}件) をまとめて開きます:")
        opened_detail_count = 0
        for i, detail_url in enumerate(detail_urls_to_open):
            logger.debug(f"  詳細URL {i+1}/{len(detail_urls_to_open)} を開くリクエスト: {detail_url}")
            webbrowser.open(detail_url)
            opened_detail_count += 1
            opened_any_url = True
        if opened_detail_count > 0:
            logger.info(f"'{program_name}': 詳細ページ {opened_detail_count} 件を開くリクエストを連続して送信しました。")
    elif opened_any_url: # 一覧は開いたが詳細がなかった場合
        logger.info(f"'{program_name}' ブロック内に開くべき追加の詳細URLは見つかりませんでした。")

    # --- 5. この関数内では待機しない ---
    # 待機処理は呼び出し元の process_program_block の最後で行います。

    return opened_any_url # 何かURLを開いた場合に True を返す


def process_program_block(block: str, nhk_programs: dict, tvtokyo_programs: dict) -> None:
    """【再修正】番組ブロックを処理し、該当URLをまとめて開いた後に待機する"""
    lines = block.strip().split('\n')
    if not lines:
        return

    header_line = lines[0].strip()
    if not header_line.startswith("●"):
        logger.warning(f"ヘッダー行形式不正: {header_line[:50]}...")
        return

    # --- 番組名抽出 ---
    program_name_match = re.match(r"●(.*?)\s?\(", header_line)
    if not program_name_match:
        program_name_match = re.match(r"●(.*)", header_line)
        if not program_name_match:
            logger.error(f"ヘッダーから番組名抽出失敗: {header_line}")
            return
    program_name = program_name_match.group(1).strip()
    logger.info(f"--- ブロック処理開始: {program_name} ---")

    # --- ブロック内URL抽出 ---
    block_urls = []
    for line in lines[1:]:
        url_matches = re.findall(r'https?://[^\s"\'<>]+', line)
        if url_matches:
            for url in url_matches:
                cleaned_url = url.rstrip('。、」)')
                block_urls.append(cleaned_url)
    # 重複を除去したリストをデバッグログに出力
    unique_block_urls_for_log = sorted(list(set(block_urls)))
    logger.debug(f"ブロック内URL ({len(unique_block_urls_for_log)}件, 重複除去後): {unique_block_urls_for_log}")


    # --- URLを開く処理 ---
    opened_urls_in_this_block = False # このブロックでURLを開いたか
    if program_name in nhk_programs:
        logger.info(f"'{program_name}' をNHK設定で発見。URLを開きます。")
        # open_urls_from_config は内部で一覧と詳細をまとめて開く(sleepなし)
        opened_urls_in_this_block = open_urls_from_config(nhk_programs, program_name, block_urls)
    elif program_name in tvtokyo_programs:
        logger.info(f"'{program_name}' をテレ東設定で発見。URLを開きます。")
        # open_urls_from_config は内部で一覧と詳細をまとめて開く(sleepなし)
        opened_urls_in_this_block = open_urls_from_config(tvtokyo_programs, program_name, block_urls)
    else:
        # --- 設定ファイルにない場合の処理 ---
        logger.warning(f"'{program_name}' は設定にありません。")
        if block_urls:
            # 設定がない場合もブロック内のURLをまとめて開く
            unique_block_urls_to_open = sorted(list(set(block_urls))) # 重複除去
            logger.info(f"設定にないがブロック内URL ({len(unique_block_urls_to_open)}件) をまとめて開きます:")
            opened_count = 0
            for i, url in enumerate(unique_block_urls_to_open):
                logger.debug(f"  設定外URL {i+1}/{len(unique_block_urls_to_open)} を開くリクエスト: {url}")
                webbrowser.open(url)
                opened_count += 1
            if opened_count > 0:
                logger.info(f"設定外番組 '{program_name}' のURL {opened_count} 件を開くリクエストを連続して送信しました。")
                opened_urls_in_this_block = True
        else:
            logger.info(f"'{program_name}' 設定になく、ブロック内にも開くURLはありませんでした。")

    # --- 待機処理 ---
    # ★★★ このブロックのURLを開く処理がすべて完了した後、URLを開いた場合のみ待機 ★★★
    if opened_urls_in_this_block:
        sleep_time = 1.0 # デフォルト待機時間 (秒)
        try:
            # Constants.Time.SLEEP_SECONDS が存在し、数値ならそれを優先
            if hasattr(Constants, 'Time') and hasattr(Constants.Time, 'SLEEP_SECONDS'):
                try:
                    sleep_time_const = Constants.Time.SLEEP_SECONDS
                    sleep_time = float(sleep_time_const)
                    logger.debug(f"設定ファイルから待機時間 {sleep_time:.1f} 秒を取得しました。")
                except (ValueError, TypeError):
                    logger.error(f"Constants.Time.SLEEP_SECONDS の値 '{sleep_time_const}' が数値ではありません。デフォルトの 1.0 秒を使用します。")
                    sleep_time = 1.0
            else:
                logger.debug("Constants.Time.SLEEP_SECONDS 未定義。デフォルトの 1.0 秒待機を使用します。")

            # WBSの場合の待機時間調整 (定数が存在する場合のみ)
            if hasattr(Constants, 'Program') and hasattr(Constants.Program, 'WBS_PROGRAM_NAME'):
                wbs_program_name = Constants.Program.WBS_PROGRAM_NAME
                if program_name == wbs_program_name:
                    original_sleep_time = sleep_time
                    sleep_time *= 1.5
                    logger.info(f"'{program_name}' (WBS) のため待機時間を {original_sleep_time:.1f}秒 -> {sleep_time:.1f} 秒に調整します。")
            # else: WBSでなければ調整しない

            logger.info(f"'{program_name}' の処理完了。次のブロックまで {sleep_time:.1f} 秒待機します...")
            time.sleep(sleep_time) # <-- 待機はここ、ブロック処理の最後に一度だけ！

        except Exception as e:
            # 予期せぬエラーが発生した場合でも最低限の待機は試みる
            logger.error(f"待機時間処理中に予期せぬエラーが発生しました: {e}", exc_info=True)
            sleep_time = 1.0 # フォールバック
            logger.info(f"エラー発生のため、フォールバックとして {sleep_time:.1f} 秒待機します。")
            time.sleep(sleep_time)

    else:
        logger.info(f"'{program_name}' では開くURLがなかったため、待機せずに次のブロックへ進みます。")

    logger.info(f"--- ブロック処理終了: {program_name} ---")


# main 関数は変更なし (ただし、Constantsの確認処理を強化)
def main():
    """メイン関数"""
    # ログ設定を最初に行う
    # ログレベルを DEBUG にすると、どのURLがどの順番で開かれようとしているか詳細に確認できます。
    # logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    # global_logger = logging.getLogger(__name__)
    # ↑basicConfigを使うか、setup_loggerを使うか統一してください。以下はsetup_loggerを使う前提。
    global_logger = setup_logger(level=logging.INFO) # 通常はINFO, デバッグ時はDEBUGに変更

    # --- 必須モジュール/設定の確認 ---
    constants_ok = True
    try:
        # Constants 自体の存在確認
        _ = Constants
        # 必須属性の存在確認 (存在しない場合にAttributeError)
        if not (hasattr(Constants, 'Time') and hasattr(Constants.Time, 'SLEEP_SECONDS')):
            global_logger.error("Constants.Time.SLEEP_SECONDS が定義されていません。")
            constants_ok = False
        # WBS判定用の定数はなくても動作はするが警告を出す
        if not (hasattr(Constants, 'Program') and hasattr(Constants.Program, 'WBS_PROGRAM_NAME')):
            global_logger.warning("Constants.Program.WBS_PROGRAM_NAME が定義されていません。WBSの待機時間調整は行われません。")
        # SLEEP_SECONDS が数値か確認
        elif not isinstance(Constants.Time.SLEEP_SECONDS, (int, float)):
            val = Constants.Time.SLEEP_SECONDS
            global_logger.error(f"Constants.Time.SLEEP_SECONDS の値 ({val}, 型:{type(val)}) が数値ではありません。")
            constants_ok = False

        if constants_ok:
            global_logger.debug("Constants モジュールと必須属性を確認しました。")
        else:
            print("エラー: common/utils.py の Constants 設定に問題があります。ログを確認してください。プログラムを終了します。")
            sys.exit(1)

    except NameError:
        global_logger.critical("common.utils から Constants をインポートできませんでした。common/utils.pyファイルが存在するか、パスが正しいか確認してください。")
        print("致命的エラー: 必須モジュール(Constants)が見つかりません。プログラムを終了します。")
        sys.exit(1)
    except Exception as e:
        global_logger.critical(f"Constants モジュールの読み込み中に予期せぬエラー: {e}", exc_info=True)
        print("致命的エラー: 設定読み込み中に予期せぬエラーが発生しました。プログラムを終了します。")
        sys.exit(1)

    # --- コマンドライン引数処理 ---
    if len(sys.argv) != 2:
        global_logger.error("日付引数がありません。")
        print("使用法: python <スクリプト名>.py YYYYMMDD")
        sys.exit(1)

    date_input = sys.argv[1]
    if not re.fullmatch(r"\d{8}", date_input):
        global_logger.error(f"日付引数の形式が不正です: {date_input} (YYYYMMDD形式)")
        print("エラー: 日付引数の形式が不正です (YYYYMMDD形式で指定してください)。")
        sys.exit(1)

    global_logger.info("=== open-url 処理開始 ===")
    global_logger.info(f"対象日付: {date_input}")

    # --- ファイルパス設定 ---
    output_dir = 'output'
    output_file_path = os.path.join(output_dir, f"{date_input}.txt")
    nhk_config_path = 'ini/nhk_config.ini'
    tvtokyo_config_path = 'ini/tvtokyo_config.ini'

    # --- 設定ファイルの読み込み ---
    try:
        nhk_programs = parse_programs_config(nhk_config_path) or {}
        tvtokyo_programs = parse_programs_config(tvtokyo_config_path) or {}
        if not nhk_programs and not tvtokyo_programs:
            global_logger.warning("NHKとTV東京、両方の設定が空かロードに失敗しました。")
        else:
            global_logger.info(f"設定読み込み完了: NHK={len(nhk_programs)}件, TV東京={len(tvtokyo_programs)}件")
            # デバッグ用に読み込んだキーを表示 (長くなる可能性があるので注意)
            # global_logger.debug(f"NHK Keys: {list(nhk_programs.keys())}")
            # global_logger.debug(f"TVTokyo Keys: {list(tvtokyo_programs.keys())}")
    except Exception as e:
        global_logger.error(f"設定ファイル ({nhk_config_path}, {tvtokyo_config_path}) の読み込み中にエラー: {e}", exc_info=True)
        print("エラー: 設定ファイルの読み込みに失敗しました。")
        sys.exit(1)

    # --- 出力ファイルの読み込み ---
    try:
        with open(output_file_path, 'r', encoding='utf-8') as file:
            content = file.read()
        global_logger.info(f"出力ファイル {output_file_path} を読み込みました。")
    except FileNotFoundError:
        global_logger.error(f"指定された出力ファイルが見つかりません: {output_file_path}")
        print(f"エラー: 出力ファイル {output_file_path} が見つかりません。")
        sys.exit(1)
    except Exception as e:
        global_logger.error(f"出力ファイル {output_file_path} の読み込みに失敗: {e}", exc_info=True)
        print(f"エラー: 出力ファイル {output_file_path} の読み込みに失敗しました。")
        sys.exit(1)

    # --- 番組ブロックの抽出 ---
    # 正規表現を少し修正: 行頭の●から始まり、次の行頭の●またはファイルの終わりまでを非貪欲にマッチ
    program_blocks = re.findall(r"(^●.*?)(?=^●|\Z)", content, re.MULTILINE | re.DOTALL)

    if not program_blocks:
        global_logger.warning("出力ファイルに処理対象の番組ブロック ('●'で始まる行) が見つかりませんでした。")
        print("処理対象の番組ブロックが見つかりませんでした。")
        sys.exit(0)

    global_logger.info(f"{len(program_blocks)}件の番組ブロックを検出しました。処理を開始します。")

    # --- 各ブロックを処理 ---
    total_blocks = len(program_blocks)
    for i, block_content in enumerate(program_blocks):
        block_num = i + 1
        logger.info(f"===== ブロック {block_num}/{total_blocks} 処理開始 =====")
        # process_program_block 内で番組名ログが出るので、ここではブロック番号のみ
        process_program_block(block_content.strip(), nhk_programs, tvtokyo_programs)
        logger.info(f"===== ブロック {block_num}/{total_blocks} 処理終了 =====")


    global_logger.info("=== すべての番組ブロックの処理が完了しました ===")


if __name__ == "__main__":
    main()
