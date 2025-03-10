import sys
import os
import re

# URLの文字数計算関数を修正
def count_tweet_length(text):
    url_pattern = re.compile(r'https?://\S+')
    urls = url_pattern.findall(text)

    # 全角文字を2文字としてカウント
    text_length = 0
    for char in text:
        if ord(char) > 255: # Unicodeコードポイントが255より大きい場合は全角とみなす
            text_length += 2
        else:
            text_length += 1

    # URLを11.5文字として計算
    url_length = 11.5 * len(urls)

    # 全角・半角文字とURLを考慮した長さを返す
    total_length = text_length - sum(len(url) for url in urls) + url_length
    return total_length

# コマンドライン引数から日付を取得
if len(sys.argv) < 2:
    print("使用方法: python tweet.py <日付 (例: 20250129)>")
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

def split_program(text, max_length=230):
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

    program_name = "" # 現在処理中の番組名
    current_tweet = "" # 現在作成中のツイート

    i = 0
    while i < len(lines):
        if lines[i].startswith("●"):
            program_name = lines[i] # 現在の番組名を設定

            #新しい番組なのでcurrent_tweetをリセット
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

            #結合したものが制限以下なら
            if count_tweet_length(current_tweet + combined) <= max_length:
                current_tweet += combined + "\n"
                i += 1
            else:
                #現在のツイートに追加すると制限を超える場合
                split_tweets.append(current_tweet)
                current_tweet = combined + "\n" #新しいツイート
                i += 1

        elif not lines[i].strip():
            # 空行は無視するが、current_tweetが空でない場合は追加
            if current_tweet:
                split_tweets.append(current_tweet)
            current_tweet = "" # リセット
            i += 1
        else :
            i += 1

    #最後の処理
    if current_tweet:
        split_tweets.append(current_tweet)

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
            program_list.append(programs[i].strip() + '\n' + programs[i+1].strip() + '\n') # 前後の空白を削除して改行を挟む
        else:
            program_list.append(programs[i].strip())
    return program_list

# テキストをプログラムごとに分割
programs = split_by_program(text)

# 分割が必要なプログラムがあるかどうかを判定
needs_split = False

# 分割前の文字数と内容を出力
print("--- 分割前のテキスト ---")
for i, program in enumerate(programs):
    length = count_tweet_length(program)
    print(program)
    print(f"文字数: {length}")
    print("-" * 20)

    if count_tweet_length(program) > 230:
        needs_split = True
        break

if needs_split:
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
    for program in programs:
        if count_tweet_length(program) > 230:
            # プログラムを分割
            split_tweets = split_program(program, max_length=230)
            new_programs.extend(split_tweets)
        else:
            # 分割不要なプログラムはそのまま追加
            new_programs.append(program)

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
    print("--- 分割後のテキスト ---")
    for item in new_programs:
        length = count_tweet_length(item)
        print(item)
        print(f"文字数: {length}")
        print("-" * 20)

else:
    # 分割が必要ない場合
    print("分割は不要でした。ファイルは変更されません。")

print("処理完了")
