import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime
from selenium.webdriver.support.ui import WebDriverWait
from common.episode_processor import EpisodeProcessor
from selenium.common.exceptions import NoSuchElementException, TimeoutException

class TestEpisodeProcessor(unittest.TestCase):
    def setUp(self):
        self.logger = MagicMock()
        self.processor = EpisodeProcessor(self.logger)
        self.program_title = "テスト番組"

    def create_mock_element(self, text="", href=None):
        """モックの要素を作成するヘルパーメソッド"""
        mock_element = MagicMock()
        mock_element.text = text
        mock_element.get_attribute.return_value = href if href else None
        return mock_element

    def test_extract_date_text_with_year(self):
        """年付きの日付テキスト抽出のテスト"""
        mock_year = self.create_mock_element(text="2025年")
        mock_day = self.create_mock_element(text="4月10日")
        mock_date = MagicMock()
        mock_date.find_element.side_effect = [mock_year, mock_day]
        mock_episode = MagicMock()
        mock_episode.find_element.return_value = mock_date

        result = self.processor._extract_date_text(mock_episode, self.program_title)
        expected = "2025年4月10日"
        self.assertEqual(result, expected)

    def test_parse_date_text(self):
        """日付テキストのパースのテスト"""
        date_text = "2025年4月10日"
        result = self.processor._parse_date_text(date_text, self.program_title)
        expected = datetime(2025, 4, 10)
        self.assertEqual(result, expected)

    def test_extract_episode_url(self):
        """エピソードURLの抽出テスト"""
        expected_url = "https://example.com/episode/1"
        mock_element = self.create_mock_element(href=expected_url)
        mock_episode = MagicMock()
        mock_episode.find_element.return_value = mock_element

        result = self.processor.extract_episode_url(mock_episode, self.program_title)
        self.assertEqual(result, expected_url)

    def test_extract_episode_url_not_found(self):
        """エピソードURL抽出失敗時のテスト"""
        mock_episode = MagicMock()
        mock_episode.find_element.side_effect = NoSuchElementException()

        result = self.processor.extract_episode_url(mock_episode, self.program_title)
        self.assertIsNone(result)
        self.logger.warning.assert_called_once()

    @patch('selenium.webdriver.support.ui.WebDriverWait')
    def test_extract_episode_title(self, mock_wait):
        """エピソードタイトル抽出のテスト"""
        expected_title = "テストエピソード"
        mock_element = MagicMock()
        mock_element.text = expected_title
        mock_wait.return_value.until.return_value = mock_element

        mock_driver = MagicMock()
        mock_driver.find_element.return_value.text = expected_title
        result = self.processor.extract_episode_title(mock_driver)
        self.assertEqual(result, expected_title)

    @patch('selenium.webdriver.support.ui.WebDriverWait')
    def test_extract_episode_title_timeout(self, mock_wait):
        """エピソードタイトル抽出タイムアウト時のテスト"""
        mock_wait.return_value.until.side_effect = TimeoutException()
        mock_driver = MagicMock()
        mock_driver.find_element.side_effect = TimeoutException()

        result = self.processor.extract_episode_title(mock_driver)
        self.assertIsNone(result)
        self.logger.warning.assert_called_once()
    def test_find_episode_elements(self):
        """エピソード要素リスト取得のテスト"""
        expected_elements = [MagicMock(), MagicMock()]
        mock_driver = MagicMock()
        mock_driver.find_elements.return_value = expected_elements

        # document.readyStateの戻り値を設定
        mock_driver.execute_script.return_value = "complete"

        # page_is_readyの戻り値を設定
        mock_condition = MagicMock()
        mock_condition.return_value = True

        with patch('selenium.webdriver.support.ui.WebDriverWait') as mock_wait, \
             patch('common.CustomExpectedConditions.CustomExpectedConditions.page_is_ready',
                   return_value=mock_condition):

            mock_wait.return_value.until.return_value = expected_elements
            result = self.processor.find_episode_elements(mock_driver, self.program_title)
            self.assertEqual(result, expected_elements)

    def test_get_episode_detail_page(self):
        """エピソード詳細ページ取得のテスト"""
        mock_driver = MagicMock()
        mock_driver.execute_script.return_value = "complete"

        # page_is_readyの戻り値を設定
        mock_condition = MagicMock()
        mock_condition.return_value = True

        with patch('selenium.webdriver.support.ui.WebDriverWait') as mock_wait, \
             patch('common.CustomExpectedConditions.CustomExpectedConditions.page_is_ready',
                   return_value=mock_condition):

            self.processor.get_episode_detail_page(mock_driver, "https://example.com")
            mock_driver.get.assert_called_once_with("https://example.com")

if __name__ == '__main__':
    unittest.main()
