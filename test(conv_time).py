import re

def extract_time_from_text(text):
    """文字列から時間部分を抽出する"""
    match = re.search(r'((午前|午後)?(\d{1,2}:\d{2}))-((午前|午後)?(\d{1,2}:\d{2}))', text)
    if match:
        start_ampm = match.group(2)
        start_time = match.group(3)
        end_ampm = match.group(5)
        end_time = match.group(6)
        return start_ampm, start_time, end_ampm, end_time
    else:
        return None, None, None, None

def _convert_to_24h(ampm, time_str):
    """午前/午後表記の時刻を24時間表記に変換するヘルパー関数"""
    hour, minute = map(int, time_str.split(":"))
    if ampm == "午後":
        if hour != 12:
          hour += 12
    elif ampm == "午前" and hour == 12:
      hour = 0
    return f"{hour:02}:{minute:02}"

# テスト用の文字列
time_text = "1/22(水) 午後11:59-午前0:28\n配信期限 : 1/29(水) 午前0:28 まで"
time_text2 = "1/22(水) 午後0:20-午後0:28\n配信期限 : 1/29(水) 午後0:28 まで"
time_text3 = "1/22(水) 午前10:00-午前10:50\n配信期限 : 1/29(水) 午後0:28 まで"
time_text4 = "1/22(水) 10:00-10:50\n配信期限 : 1/29(水) 午後0:28 まで"
time_text5 = "1/22(水)午前10:00-10:50"
time_text6 = "1/22(水)午後10:00-午前10:50"
time_text7 = "1/22(水) 午前10:00-午前10:50\n配信期限 : 1/29(水) 午後0:28 まで"
time_text8 = "10:00-10:50"

# 時間部分を抽出
start_ampm, start_time, end_ampm, end_time = extract_time_from_text(time_text)
start_ampm2, start_time2, end_ampm2, end_time2 = extract_time_from_text(time_text2)
start_ampm3, start_time3, end_ampm3, end_time3 = extract_time_from_text(time_text3)
start_ampm4, start_time4, end_ampm4, end_time4 = extract_time_from_text(time_text4)
start_ampm5, start_time5, end_ampm5, end_time5 = extract_time_from_text(time_text5)
start_ampm6, start_time6, end_ampm6, end_time6 = extract_time_from_text(time_text6)
start_ampm7, start_time7, end_ampm7, end_time7 = extract_time_from_text(time_text7)
start_ampm8, start_time8, end_ampm8, end_time8 = extract_time_from_text(time_text8)

# 結果を出力
if start_time and end_time:
    print(f"抽出された時間: {start_ampm or ''}{start_time} - {end_ampm or ''}{end_time} -> {_convert_to_24h(start_ampm,start_time)}-{_convert_to_24h(end_ampm, end_time)}")
else:
    print("時間情報が見つかりませんでした。")
if start_time2 and end_time2:
    print(f"抽出された時間2: {start_ampm2 or ''}{start_time2} - {end_ampm2 or ''}{end_time2} -> {_convert_to_24h(start_ampm2,start_time2)}-{_convert_to_24h(end_ampm2, end_time2)}")
else:
    print("時間情報が見つかりませんでした2。")
if start_time3 and end_time3:
  print(f"抽出された時間3: {start_ampm3 or ''}{start_time3} - {end_ampm3 or ''}{end_time3} -> {_convert_to_24h(start_ampm3,start_time3)}-{_convert_to_24h(end_ampm3, end_time3)}")
else:
    print("時間情報が見つかりませんでした3。")
if start_time4 and end_time4:
    print(f"抽出された時間4: {start_time4} - {end_time4} -> {_convert_to_24h('午前',start_time4)}-{_convert_to_24h('午前', end_time4)}")
else:
    print("時間情報が見つかりませんでした4。")
if start_time5 and end_time5:
    print(f"抽出された時間5: {start_ampm5 or ''}{start_time5} - {end_ampm5 or ''}{end_time5} -> {_convert_to_24h(start_ampm5,start_time5)}-{_convert_to_24h(end_ampm5,end_time5)}")
else:
    print("時間情報が見つかりませんでした5。")
if start_time6 and end_time6:
    print(f"抽出された時間6: {start_ampm6 or ''}{start_time6} - {end_ampm6 or ''}{end_time6} -> {_convert_to_24h(start_ampm6,start_time6)}-{_convert_to_24h(end_ampm6,end_time6)}")
else:
    print("時間情報が見つかりませんでした6。")
if start_time7 and end_time7:
    print(f"抽出された時間7: {start_ampm7 or ''}{start_time7} - {end_ampm7 or ''}{end_time7} -> {_convert_to_24h(start_ampm7,start_time7)}-{_convert_to_24h(end_ampm7,end_time7)}")
else:
    print("時間情報が見つかりませんでした7。")
if start_time8 and end_time8:
  print(f"抽出された時間8: {start_time8} - {end_time8} -> {_convert_to_24h('午前',start_time8)}-{_convert_to_24h('午前', end_time8)}")
else:
  print("時間情報が見つかりませんでした8。")
