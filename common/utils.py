from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import logging
import configparser

def setup_logger(name: str = __name__) -> logging.Logger:
    """ロガーを設定する"""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)  # INFOレベル以上のログを処理
    console_handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # ルートロガーのレベルをERRORに設定（ルートロガーのハンドラは削除しない）
    logging.getLogger().setLevel(logging.ERROR)

    logger.info("ロガーを設定しました。")
    return logger

def load_config(config_path: str) -> configparser.ConfigParser:
    """設定ファイルを読み込む"""
    config = configparser.ConfigParser()
    try:
        config.read(config_path, encoding='utf-8')
        logger.info(f"設定ファイル {config_path} を読み込みました。")
    except Exception as e:
        logger.error(f"設定ファイル {config_path} の読み込みに失敗しました: {e}")
        raise
    return config

class WebDriverManager:
    """WebDriverをコンテキストマネージャーで管理するクラス"""

    def __init__(self, options=None):
        self.options = options or self.default_options()
        self.driver = None  # 初期化時にdriverはNone

    @staticmethod
    def default_options():
        """デフォルトのChromeオプションを設定する"""
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--log-level=ERROR")  # SeleniumのログレベルをERRORに設定
        return options

    def __enter__(self):
        """コンテキストに入ったときにWebDriverを作成する"""
        try:
            self.driver = webdriver.Chrome(options=self.options)
            logger.info("Chrome WebDriverを作成しました。")
            return self.driver
        except Exception as e:
            logger.error(f"Chrome WebDriverの作成に失敗しました: {e}")
            raise

    def __exit__(self, exc_type, exc_val, exc_tb):
        """コンテキストを抜けるときにWebDriverを終了する"""
        if self.driver:
            self.driver.quit()
            logger.info("Chrome WebDriverを終了しました。")
        # 例外を再送出しない場合はNoneを返す
        # (呼び出し元で例外を処理する必要がある場合は、Trueを返して例外を再送出)

# utils.py の中でロガーを初期化 (他のモジュールで使うため)
logger = setup_logger()
