import os
import configparser
import webbrowser
import re
import sys

def load_config(config_path):
    config = configparser.ConfigParser()
    config.read(config_path, encoding='utf-8')
    return config

def parse_programs_from_config(config, prefix):
    programs = {}
    for section in config.sections():
        if section.startswith(prefix):
            program_name = config.get(section, 'name').strip()
            url = config.get(section, 'url').strip()
            time = config.get(section, 'time').strip() if config.has_option(section, 'time') else None
            if program_name not in programs: # 番組名がprogramsになければ、リストを新規作成
                programs[program_name] = []
            programs[program_name].append({"url": url, "time": time}) # URLとtimeをリストに追加
    return programs

def extract_urls_from_file(file_path):
    """テキストファイルからURLを抽出する関数"""
    urls = []
    with open(file_path, 'r', encoding='utf-8') as file:
        for line in file:
            url_match = re.search(r'https?://[^\s]+', line)
            if url_match:
                urls.append(url_match.group(0))
    return urls

def open_urls_from_config(config_programs, program_name, output_urls):
    """設定ファイルのURLと出力されたURLを開く関数"""
    if program_name in config_programs:
        config_urls = config_programs[program_name] # config_programs[program_name] はURLリスト
        selected_config_url = None # 選択された設定ファイルURLを初期化

        wbs_feature_url = None
        wbs_trend_tamago_url = None

        for program_config in config_urls: # WBS の設定URLを検索
            if "feature" in program_config['url']:
                wbs_feature_url = program_config['url']
            elif "trend_tamago" in program_config['url']:
                wbs_trend_tamago_url = program_config['url']

        if program_name == "WBS": # WBS の場合のみURL判定
            has_feature_url = False
            has_trend_tamago_url = False
            for url in output_urls: # 出力ファイルURLをチェック
                if "feature" in url:
                    has_feature_url = True
                elif "trend_tamago" in url:
                    has_trend_tamago_url = True

            print(f"設定ファイル内のURL (WBS):") # 設定ファイルURL表示開始

            if has_feature_url: # feature URL が出力ファイルにあれば feature URL を選択
                selected_config_url = wbs_feature_url
                if selected_config_url:
                    print(f"- {selected_config_url} (feature)") # 選択されたURLを表示 (feature)
                    webbrowser.open(selected_config_url)
            elif has_trend_tamago_url: # trend_tamago URL が出力ファイルにあれば trend_tamago URL を選択
                selected_config_url = wbs_trend_tamago_url
                if selected_config_url:
                    print(f"- {selected_config_url} (trend_tamago)") # 選択されたURLを表示 (trend_tamago)
                    webbrowser.open(selected_config_url)
            else: # どちらのURLも出力ファイルになければ、設定ファイルURLは開かない
                print("- (出力ファイルにWBSのURLが見つかりませんでした)") # 設定ファイルURLを開かないことを表示

        else: # WBS 以外の場合は、最初の設定ファイルURLを開く (従来通り)
            selected_config_url = config_urls[0]['url'] # 最初のURLを取得
            print(f"設定ファイル内のURL ({program_name}): {selected_config_url}")
            webbrowser.open(selected_config_url)

    else:
        print(f"設定ファイルに {program_name} のURLが見つかりませんでした")

    if output_urls:
        print(f"出力ファイルのURL ({program_name}):")
        for url in output_urls:
            print(url)
            webbrowser.open(url)
    else:
        print(f"出力ファイルにURLが見つかりませんでした")


def main():
    # コマンドライン引数から日付を取得
    if len(sys.argv) != 2:
        print("日付を引数で指定してください (例: python script.py 20250124)")
        sys.exit(1)

    date_input = sys.argv[1]

    # 設定ファイルのパスと出力ファイルのパスを設定
    nhk_config_path = 'ini/nhk_config.ini'
    tvtokyo_config_path = 'ini/tvtokyo_config.ini'
    output_dir = 'output'

    # 指定された日付のtxtファイルのパスを取得
    output_file_path = os.path.join(output_dir, f"{date_input}.txt")

    # 設定ファイルを読み込み
    nhk_config = load_config(nhk_config_path)
    tvtokyo_config = load_config(tvtokyo_config_path)

    # 設定ファイルから番組情報を取得
    nhk_programs = parse_programs_from_config(nhk_config, 'program_')
    tvtokyo_programs = parse_programs_from_config(tvtokyo_config, 'program_')

    # 出力ファイルを読み込み
    if os.path.exists(output_file_path):
        with open(output_file_path, 'r', encoding='utf-8') as file:
            content = file.read()
    else:
        print(f"エラー: 指定された出力ファイル {output_file_path} は存在しません。")
        return

    # テキストファイルからURLを抽出
    output_urls = extract_urls_from_file(output_file_path)

    # ファイルから番組情報を抽出
    program_blocks = content.split("●")[1:]  # 「●」で分割し、最初のヘッダーを除く

    for block in program_blocks:
        lines = block.strip().split('\n')
        if lines:
            program_info = lines[0].strip()
            program_name = program_info.split("（")[0]

            block_urls = []
            for line in lines:
                url_match = re.search(r'https?://[^\s]+', line)
                if url_match:
                    block_urls.append(url_match.group(0))

            if program_name in nhk_programs:
                open_urls_from_config(nhk_programs, program_name, block_urls)
            elif program_name in tvtokyo_programs:
                open_urls_from_config(tvtokyo_programs, program_name, block_urls)
            else:
                print(f"警告: 番組 {program_name} は設定ファイルに存在しません")

if __name__ == "__main__":
    main()
