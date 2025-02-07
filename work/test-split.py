import re
import sys
import os
from datetime import datetime

def split_program(text, max_length):
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


def count_tweet_length(text):
    url_pattern = re.compile(r'https?://\S+')
    urls = url_pattern.findall(text)

    # 全角文字を2文字としてカウント
    text_length = 0
    for char in text:
        if ord(char) > 255:  # Unicodeコードポイントが255より大きい場合は全角とみなす
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

# ファイルの存在チェック
if not os.path.exists(file_path):
    print(f"エラー: ファイル {file_path} は存在しません。")
    sys.exit(1)

# ファイルからテキストを読み込む
try:
    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read()
except Exception as e:
    print(f"ファイル読み込みエラー: {e}")
    sys.exit(1)

# 実行例
result = split_program(text,max_length=230)

output_file = "output_split.txt"  # 出力ファイル名（分割後のファイル名）
with open(output_file, "w", encoding="utf-8") as f:
    for i, item in enumerate(result):
        f.write(item)
        if i < len(result) - 1:  # 最後の要素以外に改行を挿入
            f.write("\n")  # 分割単位の間に空行を挿入

print(f"結果は {output_file} に出力されました。")
