from abc import ABC, abstractmethod
import logging
import functools
from typing import TypeVar, Callable, Any, Optional, Union, List, Tuple
import time
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException, WebDriverException
from common.utils import WebDriverManager

T = TypeVar('T')

ScrapeResultData = Optional[Union[str, List[str]]]
ScrapeResult = Tuple[str, ScrapeResultData] # (status, data_or_message)

class BaseScraper(ABC):
    """スクレイパーの抽象基底クラス"""

    def __init__(self, config):
        self.config = config
        # クラス固有のロガーを取得
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.debug(f"{self.__class__.__name__} を初期化しました。")

    # --- デコレータを修正 ---
    # @staticmethod ではなく、メソッド内で self.logger を使えるようにする
    # (またはクラスメソッドとして定義し、loggerを引数で渡すか、selfから取得)
    # ここではメソッドとして定義し、インスタンスメソッドに適用する形にする

    def _handle_selenium_error_decorator(self, func: Callable[..., T]) -> Callable[..., T | None]:
        """Seleniumの一般的なエラーを処理する内部デコレータ"""
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T | None: # self は wrapper の引数に含まれる
            # self は args[0] になる想定
            instance_self = args[0]
            try:
                return func(*args, **kwargs)
            except (TimeoutException, NoSuchElementException, StaleElementReferenceException, WebDriverException) as e:
                # より具体的にエラーログを出力
                instance_self.logger.warning(f"{func.__name__} でSeleniumエラー: {e.__class__.__name__} - 引数: {args[1:]}, {kwargs}")
            except Exception as e:
                instance_self.logger.error(f"{func.__name__} で予期せぬエラー: {e} - 引数: {args[1:]}, {kwargs}", exc_info=True)
            return None
        return wrapper

    def _log_operation_decorator(self, operation_name: str) -> Callable[[Callable[..., T]], Callable[..., T]]:
        """操作のログを記録する内部デコレータ"""
        def decorator(func: Callable[..., T]) -> Callable[..., T]:
            @functools.wraps(func)
            def wrapper(*args, **kwargs) -> T: # self は wrapper の引数に含まれる
                # self は args[0] になる想定
                instance_self = args[0]
                instance_self.logger.info(f"[{operation_name}] 開始: {args[1:] if len(args) > 1 else ''} {kwargs if kwargs else ''}")
                start_time = time.time() # time をインポートする必要あり
                result = func(*args, **kwargs)
                end_time = time.time()
                duration = end_time - start_time
                if result is not None:
                    # 結果がリストの場合、件数を表示
                    count_str = f" ({len(result)}件)" if isinstance(result, list) else ""
                    instance_self.logger.info(f"[{operation_name}] 完了{count_str} ({duration:.2f}秒)")
                else:
                    instance_self.logger.warning(f"[{operation_name}] 失敗または結果なし ({duration:.2f}秒)")
                return result
            return wrapper
        return decorator

    # --- デコレータの適用方法を変更 (クラス定義時に適用する) ---
    # 例: get_program_info に適用する場合
    # @BaseScraper._log_operation_decorator("番組情報の取得") のようには直接書けないので、
    # クラスの外でデコレータ関数を定義するか、__init_subclass__ などを使う必要がある。
    # 今回はシンプルにするため、各サブクラスのメソッド定義で @BaseScraper.log_operation のように
    # 従来通り使えるように、デコレータを staticmethod に戻し、内部で logger を取得するように修正する。

    @staticmethod
    def handle_selenium_error(func: Callable[..., T]) -> Callable[..., T | None]:
        """Seleniumの一般的なエラーを処理するデコレータ"""
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs) -> T | None: # self を受け取る
            logger = getattr(self, 'logger', logging.getLogger(func.__module__)) # selfからloggerを取得、なければモジュールロガー
            try:
                return func(self, *args, **kwargs)
            except (TimeoutException, NoSuchElementException, StaleElementReferenceException, WebDriverException) as e:
                logger.warning(f"{func.__name__} でSeleniumエラー: {e.__class__.__name__} - 引数: {args}, {kwargs}")
            except Exception as e:
                logger.error(f"{func.__name__} で予期せぬエラー: {e} - 引数: {args}, {kwargs}", exc_info=True)
            return None
        return wrapper

    @staticmethod
    def log_operation(operation_name: str) -> Callable[[Callable[..., ScrapeResult]], Callable[..., ScrapeResult]]:
        """
        操作の開始ログを記録し、結果タプル (status, data_or_message) を返すデコレータ。
        完了/失敗ログは出力しない。
        """
        def decorator(func: Callable[..., ScrapeResult]) -> Callable[..., ScrapeResult]:
            @functools.wraps(func)
            def wrapper(self, *args, **kwargs) -> ScrapeResult: # 戻り値の型を ScrapeResult に
                logger = getattr(self, 'logger', logging.getLogger(func.__module__))
                log_args = args[0] if args else "" # 最初の引数をログに出力する例
                logger.info(f"[{operation_name}] 開始: {log_args}")
                start_time = time.time()
                try:
                    # 元の関数を実行し、結果タプル (status, data_or_msg) を受け取る
                    status, data_or_msg = func(self, *args, **kwargs)
                    end_time = time.time()
                    duration = end_time - start_time
                    # 処理時間を DEBUG レベルでログ出力（任意）
                    logger.debug(f"[{operation_name}] 処理完了: {log_args} ({duration:.2f}秒) - Status: {status}")
                    # 結果タプルをそのまま返す
                    return status, data_or_msg
                except Exception as e:
                    # get_program_info 内でキャッチされずにデコレータまで来た例外
                    logger.error(f"[{operation_name}] 実行中に予期せぬエラー: {log_args} - {e}", exc_info=True)
                    # エラー発生時は failure タプルを返す
                    return "failure", f"予期せぬエラー: {e}"
            return wrapper
        return decorator
    # --- デコレータここまで ---

    @abstractmethod
    def get_program_info(self, program_name: str, target_date: str) -> ScrapeResult:
        """
        指定された番組の情報を取得する。
        成功時は ("success", 結果データ) を、失敗時は ("failure", 理由メッセージ) を返す。
        """
        pass

    def validate_config(self, program_name: str) -> bool:
        """設定の妥当性を検証する"""
        if not self.config:
            self.logger.error("設定が初期化されていません")
            return False
        if program_name not in self.config:
            # ログレベルを warning に変更し、処理は継続させる場合もある
            self.logger.warning(f"{program_name} の設定情報が見つかりません")
            return False
        # 必要であれば、urlなどの必須キーの存在チェックも追加
        program_data = self.config[program_name]
        if not isinstance(program_data, dict):
            self.logger.error(f"{program_name} の設定データが辞書ではありません。")
            return False
        return True

    def execute_with_driver(self, operation: Callable[[Any], T]) -> T | None:
        """WebDriverを使用する操作を実行する"""
        # WebDriverManager は内部で自身のロガーを使用
        with WebDriverManager() as driver:
            try:
                return operation(driver)
            except Exception as e:
                # WebDriver 操作中のエラーはここでキャッチし、詳細をログに出力
                self.logger.error(f"WebDriver操作中にエラーが発生しました: {e}", exc_info=True)
                return None

    def _format_program_output(self, program_title: str, program_time: str | None, episode_title: str, url_to_display: str) -> str:
        """番組情報の出力をフォーマットする共通関数"""
        if not program_time: # program_time が None や空文字列の場合
            program_time = "(放送時間不明)"
            self.logger.warning(f"放送時間が不明です。デフォルト値を設定: {program_title} - {episode_title}")

        # タイトルが空の場合の対処
        if not episode_title:
            episode_title = "(タイトル不明)"
            self.logger.warning(f"エピソードタイトルが不明です: {program_title}")

        # URLが空の場合の対処
        if not url_to_display:
            url_to_display = "(URL不明)"
            self.logger.warning(f"表示URLが不明です: {program_title} - {episode_title}")

        return f"●{program_title}{program_time}\n・{episode_title}\n{url_to_display}\n"
