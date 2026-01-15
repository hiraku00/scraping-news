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
    is_first_tweet_in_block = True

    for title, url in items:
        # URLが "(URLなし)" の場合はタイトルのみ追加
        item_text = f"\n{title}" + (f"\n{url}" if url != "(URLなし)" else "")
        current_length = count_tweet_length(current_tweet_text)
        item_length = count_tweet_length(item_text)

        limit = max_length - (header_length if is_first_tweet_in_block else 0)

        if current_length + item_length <= limit:
            current_tweet_text += item_text
        else:
            # 分割が発生
            # current_tweet_text が空でないことを確認してから追加
            if current_tweet_text.strip():
                split_tweets.append(current_tweet_text.strip())
            else:
                # ヘッダー行のみで既に制限を超えていた、などの特殊ケースで発生する可能性
                logger.warning("分割時に空のツイートを検知しました。")

            # 次のツイートの準備 (ヘッダーなしでアイテムから開始)
            # URLがない場合も考慮
            current_tweet_text = f"{title}" + (f"\n{url}" if url != "(URLなし)" else "")
            # ★フラグ更新: これ以降はブロック内の最初のツイートではない
            is_first_tweet_in_block = False

            # 分割直後のアイテムだけでも長すぎる場合のチェック
            # 次のツイートの制限はヘッダーを含まない max_length
            # ★修正箇所: チェックする制限を max_length にする
            if count_tweet_length(current_tweet_text) > max_length:
                logger.error(f"分割後のツイート（アイテム単体）も長すぎます。スキップ: {current_tweet_text[:50]}...")
                # エラー処理: アイテムをスキップするため、current_tweet_text を空にする
                current_tweet_text = ""
                # is_first_tweet_in_block は False のまま

    # ループ終了後、最後の current_tweet_text が残っている場合に追加
    if current_tweet_text.strip():
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
        print("使用方法: python split-text.py <日付 (例: 20250115)>")
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
        # ★ 注意: get_header_length が返すヘッダー自体の文字数か、
        # それ以外の部分の文字数かによって count_tweet_length の計算と合わせる必要がある
        # ここでは program_text 全体の長さをチェックしている
        length = count_tweet_length(program_text)
        limit = TWEET_MAX_LENGTH - (header_length if i == 0 else 0)
        header_info = f"(ヘッダー長 {header_length} 相当分を考慮)" if i == 0 else ""
        logger.info(f"- ブロック {i+1}: {length} 文字 (制限: {limit}) {header_info}")
        if length > limit:
            logger.warning(f"  -> ブロック {i+1} は文字数制限 ({limit}) を超えているため分割が必要です。")
            needs_split = True
            # break はコメントアウトのまま (全てのブロックをチェックするため)

    if needs_split:
        global_logger.info("文字数超過のため、ファイルの分割処理を実行します。")

        try:
            os.rename(file_path, backup_file_path)
            global_logger.info(f"ファイルを {backup_file_path} にバックアップしました。")
        except FileNotFoundError:
            # rename 元のファイルがない場合、処理は続行できない
            global_logger.error(f"バックアップ元ファイル {file_path} が見つかりませんでした。処理を中断します。")
            sys.exit(1)
        except Exception as e:
            global_logger.error(f"バックアップ処理中にエラーが発生しました: {e}", exc_info=True)
            sys.exit(1)

        # 分割処理
        new_tweet_list = []
        try: # 分割処理全体も try-except で囲むと、エラー時に復元しやすい
            for i, program_text in enumerate(programs):
                # 分割が必要かどうかのチェックは、分割前チェックと同じロジックで行う
                current_limit = TWEET_MAX_LENGTH - (header_length if i == 0 else 0)
                if count_tweet_length(program_text) > current_limit:
                    # split_program 呼び出し (max_length と header_length を渡す)
                    split_tweets = split_program(program_text,
                                                 max_length=TWEET_MAX_LENGTH,
                                                 header_length=(header_length if i == 0 else 0))
                    new_tweet_list.extend(split_tweets)
                else:
                    # 分割不要なブロックはそのまま追加
                    new_tweet_list.append(program_text)

            # 分割されたテキストをファイルに書き込む (間に空行を入れる)
            content_to_write = "\n\n".join(new_tweet_list) + "\n" # 最後に改行追加
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content_to_write)
            global_logger.info(f"分割されたツイート ({len(new_tweet_list)}件) は {file_path} に保存しました。")

        except Exception as e:
            global_logger.error(f"分割処理またはファイル書き込み中にエラーが発生しました: {e}", exc_info=True)
            # エラー発生時、バックアップファイルを元に戻す試み
            try:
                # 元のファイルが存在しない場合のみ復元する (書き込みが部分的に成功した場合など)
                if not os.path.exists(file_path):
                    os.rename(backup_file_path, file_path)
                    global_logger.info(f"エラー発生のため、バックアップファイル {backup_file_path} を {file_path} に復元しました。")
                else:
                    global_logger.warning(f"エラー発生しましたが、{file_path} が存在するためバックアップファイルからの復元は行いません。")
            except Exception as restore_e:
                global_logger.error(f"バックアップファイルの復元中にエラーが発生しました: {restore_e}", exc_info=True)
            sys.exit(1) # エラー発生時は終了

        # 分割後の文字数と内容を出力
        global_logger.info("\n分割後のテキストチェック:")
        all_ok = True
        for i, item in enumerate(new_tweet_list):
            length = count_tweet_length(item)
            # 分割後のチェックでは、最初のツイートのみヘッダー込みの制限、他は通常の制限
            limit = TWEET_MAX_LENGTH - (header_length if i == 0 else 0)
            status = "OK" if length <= limit else "NG (制限超過)"
            if length > limit:
                all_ok = False
            logger.info(f"- ツイート {i+1}: {length} 文字 (制限: {limit}) - {status}")
            # logger.debug(item) # 必要なら内容もデバッグ出力

        if not all_ok:
            global_logger.warning("分割後も文字数制限を超過しているツイートがあります。")


    else:
        global_logger.info("分割は不要でした。ファイルは変更されません。")

    global_logger.info("=== split-text 処理終了 ===")
