from abc import ABC, abstractmethod
import logging

class BaseScraper(ABC):
    """スクレイパーの抽象基底クラス"""

    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger(__name__)

    @abstractmethod
    def get_program_info(self, program_name: str, target_date: str) -> str | None:
        """指定された番組の情報を取得する"""
        pass
