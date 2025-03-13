# merge-text.py
import os
import sys
import re
from datetime import datetime
from common.utils import setup_logger, extract_time_from_block, sort_blocks_by_time

def extract_time_from_line(line: str) -> tuple[int, int] | None:
    """
    行から放送開始時間を抽出する。
    '●' で始まり、時刻情報（例：'05:45'）を含む行を対象とする。
    """
    if line.startswith('●'):
        time_match = re.search(r'(\d{2}:\d{2})', line)
        if time_match:
            time_str = time_match.group(1)
            hour, minute = map(int, time_str.split(':'))
            return hour, minute
    return None

def sort_and_merge_text(file1_path: str, file2_path: str, output_path: str, before_merge_path: str) -> None:
    """
    2つのテキストファイルを読み込み、時間でソートしてマージする。
    元のファイルをリネームしてから、マージ結果を出力する。
    file1_path が存在しない場合は file2_path のみを処理する。
    """
    logger = setup_logger(__name__)

    # file2_path (YYYYMMDD.txt) は必須
    if not os.path.exists(file2_path):
        logger.error(f"必須ファイル {file2_path} が見つかりません。")
        raise FileNotFoundError(f"必須ファイル {file2_path} が見つかりません。")

    # 元のファイル (file2_path) をリネーム (バックアップ)
    try:
        os.rename(file2_path, before_merge_path)
        logger.info(f"{file2_path} を {before_merge_path} にリネームしました。")
    except Exception as e:
        logger.error(f"{file2_path} のリネーム中にエラーが発生しました: {e}")
        raise


    # ファイルの存在確認と読み込み
    combined_lines = []

    try:
        with open(before_merge_path, 'r', encoding='utf-8') as f: #リネーム後のファイルを読む
            combined_lines.extend(f.readlines())
        logger.info(f"{before_merge_path} を読み込みました。")
    except Exception as e:
        logger.error(f"{before_merge_path} の読み込み中にエラーが発生しました: {e}")
        raise


    # file1_path (YYYYMMDD_tweet.txt) は任意
    if os.path.exists(file1_path):
        try:
            with open(file1_path, 'r', encoding='utf-8') as f:
                combined_lines.extend(f.readlines())
            logger.info(f"{file1_path} を読み込みました。")
        except Exception as e:
            logger.error(f"{file1_path} の読み込み中にエラーが発生しました: {e}")
            raise  # file1_path が存在しても読み込みエラーなら停止


    # combined_lines をブロックごとに分割
    blocks = []
    current_block = []
    for line in combined_lines:
        if line.startswith('●'):
            if current_block:
                blocks.append(''.join(current_block))
            current_block = [line]
        else:
            current_block.append(line)
    if current_block:
        blocks.append(''.join(current_block))

    # ブロックをソート
    sorted_blocks = sort_blocks_by_time(blocks)
    sorted_lines = []
    for block in sorted_blocks:
        sorted_lines.extend(block.splitlines(True))

    # マージされたテキストを指定されたパスに出力
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.writelines(sorted_lines)
        logger.info(f"マージされたテキストを {output_path} に出力しました。")
    except Exception as e:
        logger.error(f"{output_path} への書き込み中にエラーが発生しました: {e}")
        raise


def main():
    """
    メイン関数。
    """
    if len(sys.argv) != 2:
        print("使用法: python merge-text.py YYYYMMDD")
        sys.exit(1)

    target_date = sys.argv[1]
    if not re.match(r'^\d{8}$', target_date):
        print("日付はYYYYMMDD形式で指定してください。")
        sys.exit(1)
    try:
        datetime.strptime(target_date, '%Y%m%d')
    except ValueError:
        print("無効な日付形式です。YYYYMMDD形式で指定してください。")
        sys.exit(1)

    base_dir = 'output'
    file1_path = os.path.join(base_dir, f"{target_date}_tweet.txt")  # 任意
    file2_path = os.path.join(base_dir, f"{target_date}.txt")      # 必須
    output_path = os.path.join(base_dir, f"{target_date}.txt")      # 上書き
    before_merge_path = os.path.join(base_dir, f"{target_date}_before-merge.txt") # リネーム後

    sort_and_merge_text(file1_path, file2_path, output_path, before_merge_path)

if __name__ == "__main__":
    main()
