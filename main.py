#!/usr/bin/env python3
"""
メインスクリプト: ニューススクレイピングとツイート投稿のワークフローを管理します。

このスクリプトは以下の機能を提供します：
- ニュースのスクレイピング
- 関連ツイートの取得
- コンテンツのマージと最適化
- ツイート用のテキスト分割
- URLのブラウザでの表示
- ツイートの投稿
"""

import os
import sys
import subprocess
import argparse
import logging
import traceback
from datetime import datetime, timedelta
from typing import List, Optional

# ロギング設定
# ルートロガーのレベルをWARNINGに設定して不要なログを抑制
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# メインスクリプトのロガーはINFOレベルで表示
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# モジュールごとのログレベルを制御
for module in ['common', 'scrapers', 'utils']:
    logging.getLogger(module).setLevel(logging.WARNING)

# 進捗表示用のハンドラ（改行なしで出力）
class ProgressHandler(logging.StreamHandler):
    def emit(self, record):
        try:
            msg = self.format(record)
            stream = self.stream
            stream.write('\r' + msg)
            stream.write(' ' * 10)  # 前のメッセージの残りを消すためのスペース
            stream.flush()
        except Exception:
            self.handleError(record)

# 進捗表示用のフォーマッタ
progress_formatter = logging.Formatter('%(message)s')

# 進捗表示用のロガー
progress_logger = logging.getLogger('progress')
progress_logger.setLevel(logging.INFO)
progress_handler = ProgressHandler()
progress_handler.setFormatter(progress_formatter)
progress_logger.addHandler(progress_handler)
progress_logger.propagate = False

# 定数
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def run_command(command: List[str], cwd: Optional[str] = None) -> bool:
    """コマンドを実行し、成功したかどうかを返します。"""
    try:
        process = subprocess.Popen(
            command,
            cwd=cwd or SCRIPT_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        # リアルタイムで出力を表示
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                print(output.strip(), flush=True)
        
        return process.returncode == 0
        
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return False


def get_target_date(date_str: Optional[str] = None) -> str:
    """日付文字列を検証し、フォーマットして返します。
    
    Args:
        date_str: 日付文字列（YYYYMMDD形式）。Noneの場合は前日の日付を使用。
    """
    if date_str:
        try:
            # 日付の形式を検証
            datetime.strptime(date_str, "%Y%m%d")
            return date_str
        except ValueError:
            logger.error(f"無効な日付形式です。YYYYMMDD形式で指定してください。入力値: {date_str}")
            sys.exit(1)
    
    # デフォルトは前日の日付
    yesterday = datetime.now() - timedelta(days=1)
    return yesterday.strftime("%Y%m%d")


def get_output_file(prefix: str, date_str: str) -> str:
    """出力ファイルのパスを生成します。"""
    # scraping_news.py の出力形式に合わせる
    if prefix == "scraped":
        return os.path.join(OUTPUT_DIR, f"{date_str}.txt")
    # tweet.py の出力形式に合わせる
    elif prefix == "tweets":
        return os.path.join(OUTPUT_DIR, f"{date_str}_tweet.txt")
    # その他の場合は従来通り
    return os.path.join(OUTPUT_DIR, f"{prefix}_{date_str}.txt")


def run_scrape(target_date: str) -> bool:
    """スクレイピングを実行します。"""
    logger.info(f"Running scraping for date: {target_date}")
    try:
        from scraping_news import main as scrape_main
        # モジュールのmain関数を直接呼び出す
        sys.argv = ['scraping_news.py', target_date]
        scrape_main()
        return True
    except Exception as e:
        logger.error(f"Scraping failed: {str(e)}")
        return False


def get_tweets(target_date: str) -> bool:
    """ツイートを取得する"""
    logger.info("=== ツイート取得を開始します ===")
    logger.info(f"Fetching tweets for date: {target_date}")
    
    try:
        # 直接get_tweet.pyのmain関数を呼び出す
        from get_tweet import main as get_tweet_main
        success = get_tweet_main(target_date)
        if not success:
            logger.error("ツイート取得に失敗しました")
            return False
        return True
    except Exception as e:
        logger.error(f"Tweet fetching failed: {str(e)}")
        logger.error(traceback.format_exc())
        return False


def run_merge(target_date: str) -> bool:
    """マージを実行します。"""
    logger.info(f"Merging content for date: {target_date}")
    try:
        from merge_text import sort_and_merge_text
        
        # ファイルパスを生成
        base_dir = 'output'
        file1_path = os.path.join(base_dir, f"{target_date}_tweet.txt")
        file2_path = os.path.join(base_dir, f"{target_date}.txt")
        output_path = os.path.join(base_dir, f"{target_date}.txt")  # マージ結果は元のファイル名で上書き
        before_merge_path = os.path.join(base_dir, f"{target_date}_before-merge.txt")
        
        if not os.path.exists(file1_path) or not os.path.exists(file2_path):
            logger.error(f"Required files not found: {file1_path} or {file2_path}")
            return False
        
        # 直接sort_and_merge_text関数を呼び出す
        sort_and_merge_text(file1_path, file2_path, output_path, before_merge_path)
        logger.info("マージ処理が正常に完了しました。")
        return True
        
    except Exception as e:
        logger.error(f"Merge failed: {str(e)}")
        logger.error(traceback.format_exc())
        return False


def run_split(target_date: str) -> bool:
    """テキスト分割を実行します。
    
    split_text.pyの仕様に合わせて、以下のファイル操作を行います：
    - 入力ファイル: output/{target_date}.txt
    - バックアップ: output/{target_date}_before-split.txt (分割が必要な場合のみ)
    - 出力ファイル: output/{target_date}.txt (入力ファイルを上書き)
    """
    from split_text import split_program, split_by_program, count_tweet_length, get_header_length, TWEET_MAX_LENGTH
    
    # ファイルパスの設定
    input_file = os.path.join('output', f"{target_date}.txt")
    backup_file = os.path.join('output', f"{target_date}_before-split.txt")
    
    # 入力ファイルの存在確認
    if not os.path.exists(input_file):
        logger.error(f"ファイル {input_file} が見つかりません。")
        return False
    
    try:
        # ファイルを読み込む
        with open(input_file, 'r', encoding='utf-8') as f:
            content = f.read().strip()
        logger.info(f"ファイル {input_file} を読み込みました。")
        
        # プログラムごとに分割
        programs = split_by_program(content)
        if not programs:
            logger.warning("処理対象のプログラムブロックが見つかりませんでした。")
            return False
        
        # 分割前の文字数チェック
        needs_split = False
        header_length = get_header_length(target_date)
        
        logger.info("\n分割前の文字数チェック:")
        for i, program_text in enumerate(programs):
            length = count_tweet_length(program_text)
            limit = TWEET_MAX_LENGTH - (header_length if i == 0 else 0)
            header_info = f"(ヘッダー長 {header_length} 相当分を考慮)" if i == 0 else ""
            logger.info(f"- ブロック {i+1}: {length} 文字 (制限: {limit}) {header_info}")
            
            if length > limit:
                logger.warning(f"  -> ブロック {i+1} は文字数制限 ({limit}) を超えているため分割が必要です。")
                needs_split = True
        
        if not needs_split:
            logger.info("分割は不要でした。ファイルは変更されません。")
            return True
            
        # バックアップを作成（分割が必要な場合のみ）
        try:
            import shutil
            shutil.copy2(input_file, backup_file)
            logger.info(f"ファイルを {backup_file} にバックアップしました。")
        except Exception as e:
            logger.error(f"バックアップ処理中にエラーが発生しました: {e}")
            return False
        
        # 分割処理
        new_tweet_list = []
        try:
            for i, program_text in enumerate(programs):
                current_limit = TWEET_MAX_LENGTH - (header_length if i == 0 else 0)
                if count_tweet_length(program_text) > current_limit:
                    # 分割が必要な場合
                    split_tweets = split_program(
                        program_text,
                        max_length=TWEET_MAX_LENGTH,
                        header_length=(header_length if i == 0 else 0)
                    )
                    new_tweet_list.extend(split_tweets)
                else:
                    # 分割不要なブロックはそのまま追加
                    new_tweet_list.append(program_text)
            
            # 分割されたテキストをファイルに書き込む (間に空行を入れる)
            content_to_write = "\n\n".join(new_tweet_list) + "\n"
            with open(input_file, 'w', encoding='utf-8') as f:
                f.write(content_to_write)
            logger.info(f"分割されたツイート ({len(new_tweet_list)}件) は {input_file} に保存しました。")
            
            # 分割後の文字数チェック
            logger.info("\n分割後のテキストチェック:")
            all_ok = True
            for i, item in enumerate(new_tweet_list):
                length = count_tweet_length(item)
                limit = TWEET_MAX_LENGTH - (header_length if i == 0 else 0)
                status = "OK" if length <= limit else "NG (制限超過)"
                if length > limit:
                    all_ok = False
                logger.info(f"- ツイート {i+1}: {length} 文字 (制限: {limit}) - {status}")
            
            if not all_ok:
                logger.warning("分割後も文字数制限を超過しているツイートがあります。")
            
            return True
            
        except Exception as e:
            logger.error(f"分割処理中にエラーが発生しました: {e}")
            logger.error(traceback.format_exc())
            
            # エラー発生時はバックアップから復元を試みる
            try:
                if os.path.exists(backup_file):
                    shutil.copy2(backup_file, input_file)
                    logger.info(f"エラー発生のため、バックアップファイル {backup_file} を {input_file} に復元しました。")
            except Exception as restore_error:
                logger.error(f"バックアップファイルの復元中にエラーが発生しました: {restore_error}")
            
            return False
            
    except Exception as e:
        logger.error(f"処理中にエラーが発生しました: {e}")
        logger.error(traceback.format_exc())
        return False


def run_open_urls(target_date: str) -> bool:
    """URLをブラウザで開きます。
    
    元のopen_url.pyの仕様に合わせて、YYYYMMDD形式の日付を引数として渡します。
    """
    print(f"\n=== open_url.py を実行中 (日付: {target_date}) ===\n")
    
    # 日付形式のバリデーション
    import re
    if not re.fullmatch(r"\d{8}", target_date):
        print(f"エラー: 日付の形式が不正です: {target_date} (YYYYMMDD形式で指定してください)")
        return False
    
    try:
        import subprocess
        import sys
        
        # コマンドライン引数を設定
        cmd = [sys.executable, 'open_url.py', target_date]
        
        # サブプロセスとして実行し、標準出力と標準エラーをリアルタイムで表示
        process = subprocess.Popen(
            cmd,
            stdout=None,  # コンソールに直接出力
            stderr=None,  # コンソールに直接出力
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        # プロセスが終了するのを待つ
        return_code = process.wait()
        
        print(f"\n=== open_url.py 終了 (終了コード: {return_code}) ===\n")
        
        return return_code == 0
        
    except Exception as e:
        error_msg = f"URLのオープン中にエラーが発生しました: {str(e)}"
        print(error_msg, file=sys.stderr)
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        return False


def run_tweet(target_date: str) -> bool:
    """ツイートを投稿します。"""
    logger.info(f"Posting tweets for date: {target_date}")
    try:
        from tweet import main as tweet_main
        
        split_file = get_output_file("split", target_date)
        
        if not os.path.exists(split_file):
            logger.error(f"Split file not found: {split_file}")
            return False
        
        # モジュールのmain関数を直接呼び出す
        sys.argv = ['tweet.py', split_file]
        tweet_main()
        return True
    except Exception as e:
        logger.error(f"Tweet posting failed: {str(e)}")
        return False


def parse_args() -> argparse.Namespace:
    """コマンドライン引数を解析します。"""
    parser = argparse.ArgumentParser(description='ニューススクレイピングとツイート投稿のワークフローを管理します。')
    
    # メインオプション
    parser.add_argument('--date', type=str, help='処理する日付 (YYYYMMDD形式、デフォルト: 今日)')
    parser.add_argument('--debug', action='store_true', help='デバッグモードで実行（詳細なログを表示）')
    
    # アクションオプション（排他的）
    action_group = parser.add_mutually_exclusive_group()
    action_group.add_argument('--all', action='store_true', help='全ステップを実行（スクレイピング→ツイート取得→マージ→分割→URLオープン）')
    action_group.add_argument('--scrape', action='store_true', help='スクレイピングのみ実行')
    action_group.add_argument('--get-tweets', action='store_true', help='ツイート取得のみ実行')
    action_group.add_argument('--merge', action='store_true', help='マージのみ実行')
    action_group.add_argument('--split', action='store_true', help='分割のみ実行')
    action_group.add_argument('--open', action='store_true', help='URLオープンのみ実行')
    action_group.add_argument('--tweet', action='store_true', help='ツイート投稿のみ実行')
    
    # 引数が指定されていない場合はヘルプを表示
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(1)
    
    return parser.parse_args()


def main() -> int:
    """メイン関数。"""
    args = parse_args()
    
    # デバッグモードの設定
    if args.debug:
        logger.setLevel(logging.DEBUG)
        logger.debug("Debug mode enabled")
    
    # ターゲット日付の取得
    target_date = get_target_date(args.date)
    logger.info(f"Processing date: {target_date}")
    
    # 各アクションの実行
    success = True
    
    try:
        if args.all:
            # 全ステップ実行
            steps = [
                (run_scrape, "スクレイピング"),
                (get_tweets, "ツイート取得"),
                (run_merge, "マージ"),
                (run_split, "分割"),
                (run_open_urls, "URLオープン")
            ]
            
            for step_func, step_name in steps:
                logger.info(f"=== {step_name}を開始します ===")
                if not step_func(target_date):
                    logger.error(f"{step_name}に失敗しました")
                    success = False
                    break
                logger.info(f"=== {step_name}が完了しました ===\n")
        
        # 個別のアクション
        elif args.scrape:
            success = run_scrape(target_date)
        elif args.get_tweets:
            success = get_tweets(target_date)
        elif args.merge:
            success = run_merge(target_date)
        elif args.split:
            success = run_split(target_date)
        elif args.open:
            success = run_open_urls(target_date)
        elif args.tweet:
            success = run_tweet(target_date)
        
        if not success:
            logger.error("処理が失敗しました")
            return 1
            
        logger.info("処理が正常に完了しました")
        return 0
        
    except Exception as e:
        logger.error(f"予期しないエラーが発生しました: {str(e)}", exc_info=args.debug)
        return 1


if __name__ == "__main__":
    sys.exit(main())
