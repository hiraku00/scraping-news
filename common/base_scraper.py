from abc import ABC, abstractmethod
import logging
import functools
from typing import TypeVar, Callable, Any
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from common.utils import WebDriverManager

T = TypeVar('T')

class BaseScraper(ABC):
    """スクレイパーの抽象基底クラス"""

    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def handle_selenium_error(func: Callable[..., T]) -> Callable[..., T | None]:
        """Seleniumの一般的なエラーを処理するデコレータ"""
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs) -> T | None:
            try:
                return func(self, *args, **kwargs)
            except TimeoutException:
                self.logger.warning(f"タイムアウトが発生しました: {func.__name__}")
            except NoSuchElementException:
                self.logger.warning(f"要素が見つかりませんでした: {func.__name__}")
            except StaleElementReferenceException:
                self.logger.warning(f"要素が古くなっています: {func.__name__}")
            except Exception as e:
                self.logger.error(f"予期せぬエラーが発生しました: {func.__name__} - {str(e)}")
            return None
        return wrapper

    @staticmethod
    def log_operation(operation_name: str) -> Callable[[Callable[..., T]], Callable[..., T]]:
        """操作のログを記録するデコレータ"""
        def decorator(func: Callable[..., T]) -> Callable[..., T]:
            @functools.wraps(func)
            def wrapper(self, *args, **kwargs) -> T:
                self.logger.info(f"{operation_name}を開始します")
                result = func(self, *args, **kwargs)
                if result is not None:
                    self.logger.info(f"{operation_name}が完了しました")
                else:
                    self.logger.warning(f"{operation_name}が失敗しました")
                return result
            return wrapper
        return decorator

    @abstractmethod
    def get_program_info(self, program_name: str, target_date: str) -> str | None:
        """指定された番組の情報を取得する"""
        pass

    def validate_config(self, program_name: str) -> bool:
        """設定の妥当性を検証する"""
        if not self.config:
            self.logger.error("設定が初期化されていません")
            return False
        if program_name not in self.config:
            self.logger.warning(f"{program_name}の設定情報が見つかりません")
            return False
        return True

    def execute_with_driver(self, operation: Callable[[Any], T]) -> T | None:
        """WebDriverを使用する操作を実行する"""
        with WebDriverManager() as driver:
            try:
                return operation(driver)
            except Exception as e:
                self.logger.error(f"WebDriver操作中にエラーが発生しました: {str(e)}")
                return None

    def _format_program_output(self, program_title: str, program_time: str, episode_title: str, url_to_display: str) -> str:
        """番組情報の出力をフォーマットする共通関数"""
        return f"●{program_title}{program_time}\n・{episode_title}\n{url_to_display}\n"
