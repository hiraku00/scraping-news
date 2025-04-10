from datetime import datetime
import re
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from common.utils import Constants
from common.CustomExpectedConditions import CustomExpectedConditions

class EpisodeProcessor:
    """エピソード情報を処理するクラス"""
    def __init__(self, logger):
        self.logger = logger

    def extract_episode_date(self, episode, program_title: str) -> datetime | None:
        """エピソード要素から日付を抽出する"""
        date_text = self._extract_date_text(episode, program_title)
        if date_text:
            return self._parse_date_text(date_text, program_title)
        return None

    def _extract_date_text(self, episode, program_title: str) -> str | None:
        """エピソード要素から日付テキストを抽出する"""
        try:
            date_element = episode.find_element(By.CLASS_NAME, Constants.CSSSelector.DATE_TEXT_WITH_YEAR)
            year_element = date_element.find_element(By.CLASS_NAME, Constants.CSSSelector.DATE_YEAR)
            day_element = date_element.find_element(By.CLASS_NAME, Constants.CSSSelector.DATE_DAY)
            year_text = year_element.text.strip()
            day_text = day_element.text.strip()
            return f"{year_text}{day_text}"
        except NoSuchElementException:
            date_element = episode.find_element(By.CLASS_NAME, Constants.CSSSelector.DATE_TEXT_NO_YEAR)
            return date_element.text.strip()

    def _parse_date_text(self, date_text: str, program_title: str) -> datetime | None:
        """日付テキストをdatetimeオブジェクトにパースする"""
        match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', date_text)
        if match:
            year, month, day = map(int, match.groups())
            return datetime(year, month, day)
        return None

    def extract_episode_url(self, episode, program_title: str) -> str | None:
        """エピソード要素からURLを抽出する"""
        try:
            episode_url = episode.find_element(By.TAG_NAME, Constants.CSSSelector.EPISODE_URL_TAG).get_attribute("href")
            self.logger.debug(f"エピソード情報を抽出しました: {program_title} - {episode_url}")
            return episode_url
        except NoSuchElementException:
            self.logger.warning(f"エピソードURLの取得に失敗しました: {program_title}")
            return None

    def extract_episode_title(self, driver) -> str | None:
        """エピソードタイトルを抽出する"""
        try:
            target_element = WebDriverWait(driver, Constants.Time.DEFAULT_TIMEOUT).until(
                EC.presence_of_element_located((By.CLASS_NAME, Constants.CSSSelector.TITLE))
            )
            episode_title = target_element.text.strip().encode('utf-8', 'ignore').decode('utf-8', 'replace')
            return episode_title
        except (TimeoutException, NoSuchElementException) as e:
            self.logger.warning(f"エピソードタイトルの取得に失敗しました: {e}")
            return None

    def get_episode_detail_page(self, driver, episode_url: str):
        """エピソード詳細ページに遷移し、ページの準備完了を待つ"""
        driver.get(episode_url)
        WebDriverWait(driver, Constants.Time.DEFAULT_TIMEOUT).until(CustomExpectedConditions.page_is_ready())

    def find_episode_elements(self, driver, program_title: str):
        """エピソード要素リストを取得する"""
        WebDriverWait(driver, Constants.Time.DEFAULT_TIMEOUT).until(CustomExpectedConditions.page_is_ready())
        return WebDriverWait(driver, Constants.Time.DEFAULT_TIMEOUT).until(
            EC.presence_of_all_elements_located((By.CLASS_NAME, Constants.CSSSelector.EPISODE_INFO))
        )
