import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime
from scraping_news import NHKScraper

class TestNHKScraper(unittest.TestCase):
    def setUp(self):
        self.config = {
            "テスト番組": {
                "url": "https://example.com/program",
                "channel": "NHK"
            }
        }
        self.scraper = NHKScraper(self.config)
        # episode_processorをモック化
        self.scraper.episode_processor = MagicMock()

    def test_extract_nhk_episode_info_success(self):
        """エピソード情報抽出の正常系テスト"""
        program_title = "テスト番組"
        target_date = "20250410"
        mock_driver = MagicMock()

        # モックの設定
        mock_episodes = [MagicMock()]
        mock_date = datetime(2025, 4, 10)
        expected_url = "https://example.com/episode/1"

        self.scraper.episode_processor.find_episode_elements.return_value = mock_episodes
        self.scraper.episode_processor.extract_episode_date.return_value = mock_date
        self.scraper.episode_processor.extract_episode_url.return_value = expected_url

        result = self.scraper._extract_nhk_episode_info(mock_driver, target_date, program_title)
        self.assertEqual(result, expected_url)

    def test_extract_nhk_episode_info_no_matching_date(self):
        """エピソード情報抽出で日付が一致しない場合のテスト"""
        program_title = "テスト番組"
        target_date = "20250410"
        mock_driver = MagicMock()

        # モックの設定
        mock_episodes = [MagicMock()]
        mock_date = datetime(2025, 4, 11)  # 異なる日付

        self.scraper.episode_processor.find_episode_elements.return_value = mock_episodes
        self.scraper.episode_processor.extract_episode_date.return_value = mock_date

        result = self.scraper._extract_nhk_episode_info(mock_driver, target_date, program_title)
        self.assertIsNone(result)

    def test_get_nhk_formatted_episode_info_success(self):
        """エピソード情報のフォーマット処理の正常系テスト"""
        mock_driver = MagicMock()
        program_title = "テスト番組"
        episode_url = "https://example.com/episode/1"
        channel = "NHK"
        episode_title = "テストエピソード"

        # モックの設定
        self.scraper.episode_processor.extract_episode_title.return_value = episode_title
        self.scraper._extract_nhk_plus_url = MagicMock(return_value=None)
        self.scraper._process_eyecatch_or_iframe = MagicMock(return_value=None)
        self.scraper._extract_time_from_json_ld = MagicMock(return_value="22:00-23:00")

        expected = "●テスト番組(NHK 22:00-23:00)\n・テストエピソード\nhttps://example.com/episode/1\n"

        result = self.scraper._get_nhk_formatted_episode_info(mock_driver, program_title, episode_url, channel)
        self.assertEqual(result, expected)

    def test_get_program_info_complete_flow(self):
        """get_program_info メソッドの完全なフローのテスト"""
        program_name = "テスト番組"
        target_date = "20250410"
        episode_url = "https://example.com/episode/1"
        episode_title = "テストエピソード"

        # モックの設定
        mock_driver = MagicMock()
        self.scraper.execute_with_driver = MagicMock()
        def mock_execute(operation):
            return operation(mock_driver)
        self.scraper.execute_with_driver.side_effect = mock_execute

        # _extract_nhk_episode_info のモック
        self.scraper._extract_nhk_episode_info = MagicMock(return_value=episode_url)

        # episode_processor のモック
        self.scraper.episode_processor.extract_episode_title.return_value = episode_title

        # 実行
        result = self.scraper.get_program_info(program_name, target_date)

        # 検証
        self.assertIsNotNone(result)
        status, content = result
        from common.utils import ScrapeStatus
        self.assertEqual(status, ScrapeStatus.SUCCESS)
        self.assertIn(program_name, content)
        self.assertIn(episode_title, content)
        self.assertIn(episode_url, content)

    def test_get_program_info_invalid_config(self):
        """無効な設定での get_program_info のテスト"""
        program_name = "存在しない番組"
        target_date = "20250410"

        result = self.scraper.get_program_info(program_name, target_date)
        status, content = result
        from common.utils import ScrapeStatus
        self.assertEqual(status, ScrapeStatus.FAILURE)
        self.assertEqual(content, "設定情報が見つかりません")

if __name__ == '__main__':
    unittest.main()
