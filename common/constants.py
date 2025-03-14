from datetime import datetime
from common.utils import count_characters  # 文字カウント関数をインポート

# Twitterの文字数制限 (本来は280文字だが、少なめに-10にして設定)
TWEET_MAX_LENGTH = 270

# ヘッダーテキストのフォーマット文字列
HEADER_TEXT_FORMAT = "{date}({weekday})のニュース・ドキュメンタリー番組など\n\n"

def get_header_text(date_str: str) -> str:
    """日付文字列からヘッダーテキストを生成する"""
    try:
        target_date_dt = datetime.strptime(date_str, '%Y%m%d')
        formatted_date = target_date_dt.strftime('%y/%m/%d')
        weekdays = ["月", "火", "水", "木", "金", "土", "日"]
        japanese_weekday = weekdays[target_date_dt.weekday()]
        header_text = HEADER_TEXT_FORMAT.format(date=formatted_date, weekday=japanese_weekday)
        return header_text
    except ValueError:
        return ""  # エラー時は空文字列

def get_header_length(date_str: str) -> int:
    """日付文字列からヘッダーテキストの長さを計算する"""
    header_text = get_header_text(date_str)
    return count_characters(header_text)  # 文字カウント関数を使用
