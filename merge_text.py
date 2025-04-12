import os
import sys
import re
from datetime import datetime
import logging # logging をインポート
# setup_logger, sort_blocks_by_time をインポート
from common.utils import setup_logger, sort_blocks_by_time

# --- モジュールレベルのロガーを取得 ---
logger = logging.getLogger(__name__)

def extract_time_from_line(line: str) -> tuple[int, int] | None:
    if line.startswith('● '): # ● の後のスペースを考慮
        time_match = re.search(r'(\d{2}:\d{2})', line)
        if time_match:
            time_str = time_match.group(1)
            try: # エラーハンドリング追加
                 hour, minute = map(int, time_str.split(':'))
                 return hour, minute
            except ValueError:
                 logger.warning(f"時間文字列のパース失敗 (extract_time_from_line): {time_str} in '{line[:50]}...'")
    return None


def sort_and_merge_text(file1_path: str, file2_path: str, output_path: str, before_merge_path: str) -> None:
    """
    2つのテキストファイルを読み込み、時間でソートしてマージする。
    """
    # logger = setup_logger(__name__) # <-- 削除、モジュールレベルの logger を使用

    # file2_path (YYYYMMDD.txt) は必須
    if not os.path.exists(file2_path):
        logger.error(f"必須ファイル {file2_path} が見つかりません。処理を中断します。")
        # raise FileNotFoundError(f"必須ファイル {file2_path} が見つかりません。")
        return # エラーを出力して終了

    # 元のファイル (file2_path) をリネーム (バックアップ)
    try:
        os.rename(file2_path, before_merge_path)
        logger.info(f"{file2_path} を {before_merge_path} にリネームしました。")
    except Exception as e:
        logger.error(f"{file2_path} のリネーム中にエラーが発生しました: {e}", exc_info=True)
        # リネーム失敗時は処理を中断
        raise # or return

    # ファイルの存在確認と読み込み
    combined_lines = []
    try:
        with open(before_merge_path, 'r', encoding='utf-8') as f:
            combined_lines = f.readlines()
        logger.info(f"{before_merge_path} を読み込みました ({len(combined_lines)}行)。")
        # 末尾改行チェックと追加
        if combined_lines and not combined_lines[-1].endswith('\n'):
            logger.debug(f"{before_merge_path} の末尾に改行を追加します。")
            combined_lines[-1] += '\n'

    except Exception as e:
        logger.error(f"{before_merge_path} の読み込み中にエラーが発生しました: {e}", exc_info=True)
        # 読み込み失敗時はバックアップを戻して終了するのが安全
        try:
            os.rename(before_merge_path, file2_path)
            logger.info(f"エラー発生のため、{before_merge_path} を {file2_path} に戻しました。")
        except Exception as rename_e:
            logger.error(f"バックアップファイルの復元中にエラー: {rename_e}", exc_info=True)
        raise # or return

    # file1_path (YYYYMMDD_tweet.txt) は任意
    if os.path.exists(file1_path):
        try:
            with open(file1_path, 'r', encoding='utf-8') as f:
                file1_lines = f.readlines()
            logger.info(f"{file1_path} を読み込みました ({len(file1_lines)}行)。")

            # 結合前に file2 の末尾と file1 の先頭に不要な空行があれば調整
            # file2 の末尾に空行がなければ改行追加
            if combined_lines and not combined_lines[-1].strip() == "":
                 if not combined_lines[-1].endswith('\n'):
                     combined_lines[-1] += '\n'
                 # file1 が空でなく、combined_lines も空でない場合、間に空行を1つ入れる
                 if file1_lines and combined_lines:
                      logger.debug("ファイル間に区切りの改行を追加します。")
                      combined_lines.append('\n') # 区切りとして空行を追加

            # file1 の先頭の空行は削除 (任意)
            while file1_lines and not file1_lines[0].strip():
                 logger.debug("file1 の先頭の空行を削除します。")
                 file1_lines.pop(0)

            combined_lines.extend(file1_lines)
            logger.info(f"{file1_path} の内容を結合しました。")
        except Exception as e:
            logger.error(f"{file1_path} の処理中にエラーが発生しました: {e}", exc_info=True)
            # file1 のエラーでもバックアップを戻すか検討
            try:
                os.rename(before_merge_path, file2_path)
                logger.info(f"エラー発生のため、{before_merge_path} を {file2_path} に戻しました。")
            except Exception as rename_e:
                logger.error(f"バックアップファイルの復元中にエラー: {rename_e}", exc_info=True)
            raise # or return
    else:
        logger.info(f"ファイル {file1_path} は存在しないため、スキップします。")

    # combined_lines をブロックごとに分割
    blocks = []
    current_block = []
    logger.debug("結合後の行をブロックに分割します...")
    for i, line in enumerate(combined_lines):
        # ● の後にスペースがあるか確認
        if line.startswith('● '):
            if current_block:
                blocks.append(''.join(current_block))
                logger.debug(f"ブロックを追加 (行数: {len(current_block)}): {current_block[0][:50]}...")
            current_block = [line]
        # 空行でブロックを区切る場合 (任意)
        # elif not line.strip() and current_block:
        #     blocks.append(''.join(current_block))
        #     logger.debug(f"ブロックを追加 (空行区切り, 行数: {len(current_block)}): {current_block[0][:50]}...")
        #     current_block = [] # 空行はブロックに含めない
        elif current_block: # ブロックが開始されていれば追加
            current_block.append(line)
        elif line.strip(): # ブロックが開始されておらず、空行でもない場合 (エラーの可能性)
             logger.warning(f"ヘッダーなしで始まる行を検出 (行 {i+1}): {line[:50]}...")
             # この行を無視するか、新しいブロックとして開始するか検討
             # current_block = [line] # 新しいブロックとして開始する場合

    if current_block:
        blocks.append(''.join(current_block))
        logger.debug(f"最後のブロックを追加 (行数: {len(current_block)}): {current_block[0][:50]}...")

    logger.info(f"ブロック分割完了 ({len(blocks)} ブロック)。ソートを開始します...")
    # ブロックをソート (sort_blocks_by_time は utils にある)
    sorted_blocks = sort_blocks_by_time(blocks)
    logger.info("ブロックのソート完了。")

    # マージされたテキストを作成（ブロック間に空行を1つ入れる）
    merged_text = "\n\n".join(block.strip() for block in sorted_blocks) + "\n" # 各ブロックの末尾改行を除去し、改行2つで結合、最後に改行1つ

    # マージされたテキストを指定されたパスに出力
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(merged_text)
        logger.info(f"マージ・ソートされたテキストを {output_path} に出力しました。")
    except Exception as e:
        logger.error(f"{output_path} への書き込み中にエラーが発生しました: {e}", exc_info=True)
        # 書き込みエラー時もバックアップを戻す
        try:
            os.rename(before_merge_path, file2_path)
            logger.info(f"書き込みエラー発生のため、{before_merge_path} を {file2_path} に戻しました。")
        except Exception as rename_e:
            logger.error(f"バックアップファイルの復元中にエラー: {rename_e}", exc_info=True)
        raise

def main():
    """メイン関数"""
    # --- Logger Setup ---
    global_logger = setup_logger(level=logging.INFO)
    # ---------------------

    if len(sys.argv) != 2:
        global_logger.error("日付引数がありません。")
        print("使用法: python merge-text.py YYYYMMDD")
        sys.exit(1)

    target_date = sys.argv[1]
    global_logger.info("=== merge-text 処理開始 ===")
    global_logger.info(f"対象日付: {target_date}")

    # 日付形式のバリデーション強化
    if not re.match(r'^\d{8}$', target_date):
        global_logger.error("日付はYYYYMMDD形式で指定してください。")
        print("日付はYYYYMMDD形式で指定してください。")
        sys.exit(1)
    try:
        datetime.strptime(target_date, '%Y%m%d')
    except ValueError:
        global_logger.error("無効な日付形式です。")
        print("無効な日付形式です。YYYYMMDD形式で指定してください。")
        sys.exit(1)

    base_dir = 'output'
    file1_path = os.path.join(base_dir, f"{target_date}_tweet.txt")
    file2_path = os.path.join(base_dir, f"{target_date}.txt")
    output_path = os.path.join(base_dir, f"{target_date}.txt") # マージ結果は元のファイル名で上書き
    before_merge_path = os.path.join(base_dir, f"{target_date}_before-merge.txt")

    try:
        # sort_and_merge_text は内部でモジュールロガーを使用
        sort_and_merge_text(file1_path, file2_path, output_path, before_merge_path)
        global_logger.info("マージ処理が正常に完了しました。")
    except FileNotFoundError:
        # sort_and_merge_text内でエラーログ出力済みなので、ここでは main の終了を示す
        global_logger.error("必須ファイルが見つからなかったため、処理を終了しました。")
        sys.exit(1)
    except Exception as e:
        global_logger.error(f"マージ処理中に予期せぬエラーが発生しました: {e}", exc_info=True)
        # sort_and_merge_text内でバックアップ復元試行済み
        sys.exit(1)
    finally:
         global_logger.info("=== merge-text 処理終了 ===")


if __name__ == "__main__":
    main()
