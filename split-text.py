import sys
import os
import re
from common.constants import (
    TWEET_MAX_LENGTH,
    get_header_text,
    get_header_length
)
from common.utils import count_tweet_length

# コマンドライン引数から日付を取得
if len(sys.argv) < 2:
    print("使用方法: python split-text.py <日付 (例: 20250129)>")
    sys.exit(1)

date = sys.argv[1]
file_path = f"output/{date}.txt"
backup_file_path = f"output/{date}_before-split.txt"

# 指定された日付のファイルを読み込む
try:
    with open(file_path, "r", encoding="utf-8") as file:
        text = file.read().strip()  # ファイル全体を文字列として読み込む
except FileNotFoundError:
    print(f"エラー: {file_path} が見つかりません。")
    sys.exit(1)

def split_program(text, max_length=TWEET_MAX_LENGTH, header_length=0):
    """
    番組テキストを指定された文字数制限内で分割する関数（ヘッダーなし）。

    Args:
        text (str): 分割対象の番組テキスト（番組名、タイトル、URLを含む）。
        max_length (int): 文字数制限。

    Returns:
        list: 分割されたテキストのリスト。
    """
    split_tweets = []
    lines = text.split('\n')

    program_name = ""  # 現在処理中の番組名
    current_tweet = ""  # 現在作成中のツイート
    is_first_program = True  # 最初のプログラムかどうかを判定するフラグ

    i = 0
    while i < len(lines):
        if lines[i].startswith("●"):
            program_name = lines[i]  # 現在の番組名を設定

            # 新しい番組なのでcurrent_tweetをリセット
            if current_tweet:
                split_tweets.append(current_tweet)
            current_tweet = ""
            i += 1

        elif i < len(lines) and lines[i].startswith("・"):
            title = lines[i]
            i += 1
            url = lines[i] if i < len(lines) else ""
            combined = f"{title}\n{url}"

            # 番組名を追加
            if not current_tweet:
                current_tweet = program_name + '\n'

            # 最初のプログラムの最初のツイートのみ、ヘッダー長を考慮
            if is_first_program and not split_tweets:
                if count_tweet_length(current_tweet + combined) <= max_length - header_length:
                    current_tweet += combined + "\n"
                    i += 1
                else:
                    split_tweets.append(current_tweet)
                    current_tweet = combined + "\n"
                    i += 1
            else:
                if count_tweet_length(current_tweet + combined) <= max_length:
                    current_tweet += combined + "\n"
                    i += 1
                else:
                    split_tweets.append(current_tweet)
                    current_tweet = combined + "\n"
                    i += 1

        elif not lines[i].strip():
            # 空行は無視するが、current_tweetが空でない場合は追加
            if current_tweet:
                split_tweets.append(current_tweet)
            current_tweet = ""  # リセット
            i += 1
        else:
            i += 1

    # 最後の処理
    if current_tweet:
        split_tweets.append(current_tweet)

    is_first_program = False
    return split_tweets

# プログラム（ブロック）ごとにテキストを分割する関数
def split_by_program(text):
    programs = re.split(r'(^●.*?\n)', text, flags=re.MULTILINE)
    # 空文字列を削除
    programs = [p for p in programs if p]
    # プログラム名と内容を組み合わせる
    program_list = []
    for i in range(0, len(programs), 2):
        if i + 1 < len(programs):
            program_list.append(programs[i].strip() + '\n' + programs[i+1].strip() + '\n')  # 前後の空白を削除して改行を挟む
        else:
            program_list.append(programs[i].strip())
    return program_list

# テキストをプログラムごとに分割
programs = split_by_program(text)

# 分割が必要なプログラムがあるかどうかを判定
needs_split = False

# 分割前の文字数と内容を出力
print("\n")
print("============================== 分割前のテキスト ==============================")
for i, program in enumerate(programs):
    length = count_tweet_length(program)
    print(program)
    print(f"文字数: {length}")
    print("-" * 20)

    # 最初のブロックの場合はヘッダーを考慮して判定
    header_length = get_header_length(date)  # ヘッダーの長さを計算
    if i == 0:
        if length + header_length > TWEET_MAX_LENGTH:
            needs_split = True
            break
    elif length > TWEET_MAX_LENGTH:  # 2番目以降のブロックは TWEET_MAX_LENGTH で判定
        needs_split = True
        break

if needs_split:
    # (ファイルバックアップ、分割、ファイル書き込み処理は変更なし)
    # ファイルバックアップ
    try:
        os.rename(file_path, backup_file_path)
        print(f"ファイルを {backup_file_path} にバックアップしました。")
    except FileNotFoundError:
        print(f"バックアップ元ファイル {file_path} が見つかりませんでした。処理を中断します。")
        sys.exit(1)
    except Exception as e:
        print(f"バックアップ処理中にエラーが発生しました: {e}")
        sys.exit(1)

    # 分割されたプログラムを格納するリスト
    new_programs = []
    header_length = get_header_length(date)
    for program in programs:
        if i == 0:  # 最初のブロック
            if count_tweet_length(program)  > TWEET_MAX_LENGTH - header_length:
                split_tweets = split_program(program, header_length=header_length)
                new_programs.extend(split_tweets)
            else:
                new_programs.append(program) # 分割不要
        else:  # 2番目以降のブロック
            if count_tweet_length(program) > TWEET_MAX_LENGTH:
                split_tweets = split_program(program)  # header_length は不要
                new_programs.extend(split_tweets)
            else:
                new_programs.append(program)  # 分割不要

    # 分割されたテキストをファイルに書き込む
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            for i, item in enumerate(new_programs):
                f.write(item)
                if i < len(new_programs) - 1:  # 最後の要素以外に改行を挿入
                    f.write("\n")  # 分割単位の間に空行を挿入

        print(f"分割されたツイートは {file_path} に保存しました。")

    except Exception as e:
        print(f"分割されたツイートの保存中にエラーが発生しました: {e}")

        # バックアップファイルを元に戻す
        try:
            os.rename(backup_file_path, file_path)
            print(f"バックアップファイル {backup_file_path} を {file_path} に復元しました。")
        except Exception as e:
            print(f"バックアップファイルの復元中にエラーが発生しました: {e}")
        sys.exit(1)

    # 分割後の文字数と内容を出力
    print("\n")
    print("============================== 分割後のテキスト ==============================")
    for item in new_programs:
        length = count_tweet_length(item)
        print(item)
        print(f"文字数: {length}")
        print("-" * 60)

else:
    # 分割が必要ない場合
    print("分割は不要でした。ファイルは変更されません。")

print("処理完了")
