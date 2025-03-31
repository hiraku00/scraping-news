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

def split_program(program_block_text: str, is_first_block_overall: bool, header_length: int, max_length: int = TWEET_MAX_LENGTH) -> list[str]:
    """
    1つの番組ブロックを指定された文字数制限内で分割する関数。
    分割された場合、2つ目以降のツイートには番組名ヘッダーを付けない。

    Args:
        program_block_text (str): 分割対象の番組ブロックテキスト。
        is_first_block_overall (bool): このブロックが "ファイル全体の" 最初のブロックかどうか。
        header_length (int): 最初のツイートに付加されるヘッダーの長さ。
        max_length (int): ツイートの最大文字数。

    Returns:
        list: 分割されたツイートのリスト。
              最初の要素には番組名ヘッダーが付く。
              分割された場合の2つ目以降の要素は内容のみ。
    """
    lines = program_block_text.strip().split('\n')
    if not lines:
        return []

    program_name = lines[0] # ●番組名...
    content_text = '\n'.join(lines[1:]) # 番組名を除いた内容部分

    # タイトルとURLのペアを抽出
    item_pairs_matches = re.findall(r'^(・.*?)\n(https?://.*?)$', content_text, re.MULTILINE)
    item_pairs = [f"{title}\n{url}" for title, url in item_pairs_matches]

    # --- アイテムがない場合の処理 ---
    if not item_pairs:
        # 最初のブロックならヘッダー長を考慮
        effective_max_len = max_length - header_length if is_first_block_overall else max_length
        if count_tweet_length(program_name) <= effective_max_len:
            return [program_name]
        else:
            print(f"警告: 番組名だけで文字数超過。分割できません。文字数: {count_tweet_length(program_name)}")
            return [program_name] # 投稿時にエラーになる想定

    split_tweets = []
    current_tweet_items = [] # 現在のツイート部分に含める item_pairs の文字列リスト
    is_first_part_of_this_block = True # このブロック内で最初のツイート部分か？

    for item in item_pairs:
        # --- 現在のツイート部分に追加した場合のテキストと文字数を計算 ---
        items_to_check = current_tweet_items + [item]
        current_content = "\n".join(items_to_check)

        if is_first_part_of_this_block:
            # このブロックの最初のツイート部分の場合
            potential_tweet_text = f"{program_name}\n{current_content}"
            # さらにファイル全体の最初のツイート部分ならヘッダー長を考慮
            current_max_len = max_length - header_length if is_first_block_overall else max_length
        else:
            # このブロックの2つ目以降のツイート部分の場合 (ヘッダーなし)
            potential_tweet_text = current_content
            current_max_len = max_length # ヘッダー長は考慮不要

        # --- 文字数チェック ---
        if count_tweet_length(potential_tweet_text) <= current_max_len:
            # 制限内なら現在のツイート部分に追加
            current_tweet_items.append(item)
        else:
            # 制限を超える場合
            if current_tweet_items: # 現在のツイート部分にアイテムが既にあるか？
                # --- 現在のツイート部分を確定 ---
                final_items_content = "\n".join(current_tweet_items)
                if is_first_part_of_this_block:
                    # 最初の部分だったのでヘッダー付きで確定
                    final_tweet = f"{program_name}\n{final_items_content}"
                else:
                    # 2つ目以降の部分だったので内容のみで確定
                    final_tweet = final_items_content
                split_tweets.append(final_tweet)

                # --- 新しいツイート部分を開始 ---
                is_first_part_of_this_block = False # 次からはヘッダーなし
                current_tweet_items = [item] # 新しいアイテムで開始

                # 新しいツイート部分（アイテム1つだけ）が制限を超えるかチェック (ヘッダーなし)
                new_part_text = item
                if count_tweet_length(new_part_text) > max_length:
                    print(f"警告: 新しいツイート部分開始時、アイテム1つで文字数超過: {count_tweet_length(new_part_text)} > {max_length}")
                    print(new_part_text)
            else:
                # 現在のツイート部分が空（＝最初のアイテムだけで超過）
                if is_first_part_of_this_block:
                    # ヘッダー付きでアイテム1つ
                    single_item_tweet = f"{program_name}\n{item}"
                    check_len = max_length - header_length if is_first_block_overall else max_length
                else:
                    # ヘッダーなしでアイテム1つ (理論上ほぼ起こらないはず)
                    single_item_tweet = item
                    check_len = max_length

                if count_tweet_length(single_item_tweet) > check_len:
                    print(f"警告: 最初のアイテムだけで文字数超過: {count_tweet_length(single_item_tweet)} > {check_len}")
                    print(single_item_tweet)

                split_tweets.append(single_item_tweet)
                # 次のアイテムのためにリセット
                is_first_part_of_this_block = False # 次からはヘッダーなし
                current_tweet_items = []

    # ループ終了後、残っているアイテムがあれば最後のツイート部分として追加
    if current_tweet_items:
        final_items_content = "\n".join(current_tweet_items)
        if is_first_part_of_this_block:
            # ブロック全体が1ツイートに収まった場合 (ヘッダー付き)
            final_tweet = f"{program_name}\n{final_items_content}"
        else:
            # 最後の部分（ヘッダーなし）
            final_tweet = final_items_content
        split_tweets.append(final_tweet)

    # 念のためのチェック (通常は不要)
    if not split_tweets and item_pairs:
        print("警告: アイテムがあったにも関わらず、分割結果が空になりました。")
        return [program_block_text] # 元のまま返す

    return split_tweets

# プログラム（ブロック）ごとにテキストを分割する関数 (既存のものを流用)
def split_by_program(text):
    # ●で始まる行を探し、その行を含めて次の●まで（または終端まで）をブロックとする
    programs = re.split(r'(?=^●)', text, flags=re.MULTILINE)
    # 先頭の空要素や空白のみの要素を除去
    program_list = [p.strip() for p in programs if p and p.strip()]
    return program_list

# テキストをプログラムごとに分割
programs = split_by_program(text)

all_split_tweets = [] # 全ての分割されたツイートを格納するリスト
needs_split = False
header_length = get_header_length(date)

print("\n")
print("============================== 分割前のテキスト ==============================")
# まず分割が必要かチェック (可読性のため分割処理とは別ループにする)
for i, program_block in enumerate(programs):
    length = count_tweet_length(program_block)
    print(program_block)
    print(f"文字数: {length}")
    print("-" * 20)

    # 最初のブロックの場合はヘッダーを考慮して判定
    effective_max_len = TWEET_MAX_LENGTH - header_length if i == 0 else TWEET_MAX_LENGTH
    if length > effective_max_len:
        needs_split = True
        # 1つでも分割が必要ならチェックを終了しても良い
        # break # チェックだけならここで抜けてもOK

print(f"\n分割が必要か: {needs_split}")

if needs_split:
    # ファイルバックアップ (変更なし)
    try:
        os.rename(file_path, backup_file_path)
        print(f"ファイルを {backup_file_path} にバックアップしました。")
    except FileNotFoundError:
        print(f"バックアップ元ファイル {file_path} が見つかりませんでした。処理を中断します。")
        sys.exit(1)
    except Exception as e:
        print(f"バックアップ処理中にエラーが発生しました: {e}")
        sys.exit(1)


    # 各プログラムブロックを分割
    for i, program_block in enumerate(programs):
        # is_first_block_overall は、ループのインデックス i が 0 かどうかで判定
        is_first_overall = (i == 0)
        length = count_tweet_length(program_block)
        # 有効な最大長を計算（分割判定用）
        effective_max_len = TWEET_MAX_LENGTH - header_length if is_first_overall else TWEET_MAX_LENGTH

        if length > effective_max_len:
            # 分割が必要なブロック
            print(f"\nブロック分割実行: {program_block.splitlines()[0]}...")
            # ★修正: is_first_overall を渡す
            split_tweets_for_block = split_program(program_block, is_first_overall, header_length)
            all_split_tweets.extend(split_tweets_for_block)
        else:
            # 分割不要なブロックはそのまま追加
            all_split_tweets.append(program_block.strip())

    # 分割されたテキストをファイルに書き込む
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            for i, item in enumerate(all_split_tweets):
                f.write(item)
                if i < len(all_split_tweets) - 1:
                    # tweet.py が \n\n で分割しているので、それに合わせる
                    f.write("\n\n")
        print(f"\n分割されたツイートは {file_path} に保存しました。")
    except Exception as e:
        # (エラー処理とバックアップ復元 - 変更なし)
        print(f"分割されたツイートの保存中にエラーが発生しました: {e}")
        try:
            os.rename(backup_file_path, file_path)
            print(f"バックアップファイル {backup_file_path} を {file_path} に復元しました。")
        except Exception as restore_e:
            print(f"バックアップファイルの復元中にエラーが発生しました: {restore_e}")
        sys.exit(1)

    # 分割後の文字数と内容を出力
    print("\n")
    print("============================== 分割後のテキスト ==============================")
    for item in all_split_tweets:
        length = count_tweet_length(item)
        print(item)
        print(f"文字数: {length}")
        print("-" * 60)

else:
    # 分割が不要だった場合 (変更なし)
    print("\n分割は不要でした。ファイルは変更されません。")

print("\n処理完了")
