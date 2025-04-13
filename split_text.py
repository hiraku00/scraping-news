import sys
import os
import re
import logging # logging をインポート
from common.constants import (
    TWEET_MAX_LENGTH,
    get_header_text,
    get_header_length
)
# count_tweet_length, setup_logger をインポート
from common.utils import count_tweet_length, setup_logger

# --- モジュールレベルのロガーを取得 ---
logger = logging.getLogger(__name__)

def split_program(text, max_length=TWEET_MAX_LENGTH, header_length=0):
    split_tweets = []
    lines = text.strip().split('\n')

    program_name_line = ""
    items = []

    if lines and lines[0].startswith("●"):
        program_name_line = lines[0]
        item_lines = lines[1:]
        i = 0
        while i < len(item_lines):
            if item_lines[i].startswith("・"):
                title = item_lines[i]
                i += 1
                url = item_lines[i] if i < len(item_lines) and item_lines[i].startswith("http") else ""
                if url:
                    items.append((title, url))
                    i += 1
                else:
                    logger.warning(f"アイテムのURLが見つかりません: {title}")
                    items.append((title, "(URLなし)"))
            else:
                logger.warning(f"予期しない形式の行です、スキップします: {item_lines[i][:50]}...")
                i += 1
    else:
        # ここでエラーログは出すが、処理は続行せず空リストを返す
        logger.error(f"ヘッダー行が見つからないか形式が不正です: {text[:50]}...")
        return [] # 分割不可

    # アイテム結合ロジックは変更なし
    current_tweet_text = program_name_line
    first_item_processed = False
    for title, url in items:
        item_text = f"\n{title}\n{url}"
        current_length = count_tweet_length(current_tweet_text)
        item_length = count_tweet_length(item_text)
        limit = max_length - (header_length if not first_item_processed else 0)

        if current_length + item_length <= limit:
            current_tweet_text += item_text
            first_item_processed = True
        else:
            split_tweets.append(current_tweet_text.strip())
            # 次のツイートはヘッダーなしでアイテムから開始
            current_tweet_text = f"{title}\n{url}" # ヘッダーなし
            first_item_processed = True
            if count_tweet_length(current_tweet_text) > max_length:
                logger.error(f"分割後のツイートも長すぎます。スキップ: {current_tweet_text[:50]}...")
                current_tweet_text = ""

    if current_tweet_text:
        split_tweets.append(current_tweet_text.strip())

    logger.info(f"プログラムを {len(split_tweets)} 個のツイートに分割しました: {program_name_line[:30]}...")
    return split_tweets

def split_by_program(text):
    programs = re.findall(r"(^●.*?)(?=^●|\Z)", text, re.MULTILINE | re.DOTALL)
    program_list = [p.strip() for p in programs if p.strip()] # 前後の空白を除去し、空のブロックを除外
    logger.info(f"テキストを {len(program_list)} 個のプログラムブロックに分割しました。")
    return program_list


if __name__ == "__main__":
    # --- Logger Setup ---
    global_logger = setup_logger(level=logging.INFO)
    # ---------------------

    if len(sys.argv) < 2:
        global_logger.error("日付引数がありません。")
        print("使用方法: python split-text.py <日付 (例: 20250129)>")
        sys.exit(1)

    date = sys.argv[1]
    global_logger.info("=== split-text 処理開始 ===")
    global_logger.info(f"対象日付: {date}")

    file_path = f"output/{date}.txt"
    backup_file_path = f"output/{date}_before-split.txt"

    try:
        with open(file_path, "r", encoding="utf-8") as file:
            text = file.read().strip()
        global_logger.info(f"ファイル {file_path} を読み込みました。")
    except FileNotFoundError:
        global_logger.error(f"ファイル {file_path} が見つかりません。")
        print(f"エラー: {file_path} が見つかりません。")
        sys.exit(1)
    except Exception as e:
        global_logger.error(f"ファイル読み込みエラー: {e}", exc_info=True)
        sys.exit(1)

    programs = split_by_program(text)
    if not programs:
        global_logger.warning("処理対象のプログラムブロックが見つかりませんでした。")
        print("処理対象のプログラムブロックが見つかりませんでした。")
        sys.exit(0)

    needs_split = False
    header_length = get_header_length(date) # ヘッダー長を先に計算

    global_logger.info("\n分割前の文字数チェック:")
    for i, program_text in enumerate(programs):
        length = count_tweet_length(program_text)
        header_info = f"(ヘッダー長 {header_length} 込み)" if i == 0 else ""
        limit = TWEET_MAX_LENGTH - (header_length if i == 0 else 0)
        logger.info(f"- ブロック {i+1}: {length} 文字 {header_info} (制限: {limit})")
        if length > limit:
            logger.warning(f"  -> ブロック {i+1} は文字数制限を超えているため分割が必要です。")
            needs_split = True
            # break # 一つでも超えていたら分割処理へ

    if needs_split:
        global_logger.info("文字数超過のため、ファイルの分割処理を実行します。")
        # ファイルバックアップ
        try:
            # バックアップファイルが既に存在する場合は上書きしないようにするか、連番をつける
            if os.path.exists(backup_file_path):
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                backup_file_path = f"output/{date}_before-split_{timestamp}.txt"
                global_logger.warning(f"バックアップファイルが既に存在するため、別名で保存します: {backup_file_path}")
            os.rename(file_path, backup_file_path)
            global_logger.info(f"ファイルを {backup_file_path} にバックアップしました。")
        except FileNotFoundError:
            global_logger.error(f"バックアップ元ファイル {file_path} が見つかりませんでした。処理を中断します。")
            sys.exit(1)
        except Exception as e:
            global_logger.error(f"バックアップ処理中にエラーが発生しました: {e}", exc_info=True)
            sys.exit(1)

        # 分割処理
        new_tweet_list = []
        for i, program_text in enumerate(programs):
            limit = TWEET_MAX_LENGTH - (header_length if i == 0 else 0)
            if count_tweet_length(program_text) > limit:
                # split_program はリストを返す
                split_tweets = split_program(program_text, max_length=TWEET_MAX_LENGTH, header_length=(header_length if i == 0 else 0))
                new_tweet_list.extend(split_tweets)
            else:
                new_tweet_list.append(program_text) # 分割不要

        # 分割されたテキストをファイルに書き込む (間に空行を入れる)
        try:
            content_to_write = "\n\n".join(new_tweet_list) + "\n" # 最後に改行追加
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content_to_write)
            global_logger.info(f"分割されたツイート ({len(new_tweet_list)}件) は {file_path} に保存しました。")

        except Exception as e:
            global_logger.error(f"分割されたツイートの保存中にエラーが発生しました: {e}", exc_info=True)
            # バックアップファイルを元に戻す
            try:
                os.rename(backup_file_path, file_path)
                global_logger.info(f"エラー発生のため、バックアップファイル {backup_file_path} を {file_path} に復元しました。")
            except Exception as restore_e:
                global_logger.error(f"バックアップファイルの復元中にエラーが発生しました: {restore_e}", exc_info=True)
            sys.exit(1)

        # 分割後の文字数と内容を出力
        global_logger.info("\n分割後のテキストチェック:")
        for i, item in enumerate(new_tweet_list):
            length = count_tweet_length(item)
            limit = TWEET_MAX_LENGTH - (header_length if i == 0 else 0)
            status = "OK" if length <= limit else "NG (制限超過)"
            logger.info(f"- ツイート {i+1}: {length} 文字 (制限: {limit}) - {status}")
            # logger.debug(item) # 必要なら内容もデバッグ出力
            # print("-" * 60)

    else:
        global_logger.info("分割は不要でした。ファイルは変更されません。")

    global_logger.info("=== split-text 処理終了 ===")
