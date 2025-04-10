import unittest
from unittest.mock import MagicMock
from common.base_scraper import BaseScraper

class TestBaseScraper(unittest.TestCase):
    def setUp(self):
        # テスト用の具象クラスを作成
        class ConcreteScraper(BaseScraper):
            def get_program_info(self, program_name: str, target_date: str) -> str | None:
                pass

        self.config = {
            "test_program": {
                "url": "https://example.com",
                "channel": "TEST"
            }
        }
        self.scraper = ConcreteScraper(self.config)

    def test_format_program_output(self):
        """_format_program_output メソッドのテスト"""
        result = self.scraper._format_program_output(
            program_title="テスト番組",
            program_time="(TEST 12:00-13:00)",
            episode_title="テストエピソード",
            url_to_display="https://example.com"
        )
        expected = "●テスト番組(TEST 12:00-13:00)\n・テストエピソード\nhttps://example.com\n"
        self.assertEqual(result, expected)

    def test_validate_config_with_valid_program(self):
        """validate_config メソッドのテスト - 有効な設定の場合"""
        result = self.scraper.validate_config("test_program")
        self.assertTrue(result)

    def test_validate_config_with_invalid_program(self):
        """validate_config メソッドのテスト - 無効な設定の場合"""
        result = self.scraper.validate_config("nonexistent_program")
        self.assertFalse(result)

    def test_handle_selenium_error_decorator(self):
        """handle_selenium_error デコレータのテスト"""
        mock_function = MagicMock(side_effect=Exception("Test error"))
        mock_function.__name__ = "test_func"  # __name__属性を追加
        decorated_func = BaseScraper.handle_selenium_error(mock_function)
        result = decorated_func(self.scraper)
        self.assertIsNone(result)

if __name__ == '__main__':
    unittest.main()
