from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import logging
import configparser

def setup_logger(name: str = __name__) -> logging.Logger:
    """ロガーを設定する"""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)  # INFOレベル以上のログを処理

    # 同じハンドラが重複して追加されるのを防ぐ
    if not logger.handlers:
        console_handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    # ルートロガーのレベルをERRORに設定（ルートロガーのハンドラは削除しない）
    # logging.getLogger().setLevel(logging.ERROR) # コメントアウト or 削除

    logger.info("ロガーを設定しました。")
    return logger

def load_config(config_path: str) -> configparser.ConfigParser:
    """設定ファイルを読み込む"""
    config = configparser.ConfigParser()
    try:
        config.read(config_path, encoding='utf-8')
        logging.getLogger(__name__).info(f"設定ファイル {config_path} を読み込みました。")
    except Exception as e:
        logging.getLogger(__name__).error(f"設定ファイル {config_path} の読み込みに失敗しました: {e}")
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
            logging.getLogger(__name__).info("Chrome WebDriverを作成しました。")
            return self.driver
        except Exception as e:
            logging.getLogger(__name__).error(f"Chrome WebDriverの作成に失敗しました: {e}")
            raise

    def __exit__(self, exc_type, exc_val, exc_tb):
        """コンテキストを抜けるときにWebDriverを終了する"""
        if self.driver:
            self.driver.quit()
            logging.getLogger(__name__).info("Chrome WebDriverを終了しました。")
