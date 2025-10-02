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
            # 新しいNHK ONE構造ではtime要素のテキストから日付を取得
            time_element = episode.find_element(By.CSS_SELECTOR, 'time')
            date_text = time_element.text.strip()
            # 日付文字列から「年」を基準に日付部分だけを抽出（年月日まで）
            parts = date_text.split('年')
            date_text = parts[0] + '年' + parts[1].split('月')[0] + '月' + parts[1].split('月')[1].split('日')[0] + '日'
            if date_text:
                return date_text
        except NoSuchElementException:
            pass

        # フォールバックとしてdatetime属性から日付を抽出
        try:
            time_element = episode.find_element(By.CSS_SELECTOR, Constants.CSSSelector.DATE_TEXT_WITH_YEAR)
            datetime_attr = time_element.get_attribute("datetime")
            if datetime_attr:
                # datetime属性から日付部分を抽出 (例: "2025-10-09T10:05:00+09:00" → "2025年10月9日")
                date_match = re.search(r'(\d{4})-(\d{2})-(\d{2})', datetime_attr)
                if date_match:
                    year, month, day = date_match.groups()
                    return f"{year}年{int(month)}月{int(day)}日"
        except NoSuchElementException:
            pass

        return None

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
            # 新しいNHK ONE構造ではa要素のhref属性からエピソードURLを取得
            episode_url_element = episode.find_element(By.CSS_SELECTOR, Constants.CSSSelector.EPISODE_URL_TAG)
            episode_url = episode_url_element.get_attribute("href")
            if episode_url:
                self.logger.debug(f"エピソード情報を抽出しました: {program_title} - {episode_url}")
                return episode_url
        except NoSuchElementException:
            self.logger.warning(f"エピソードURLの取得に失敗しました: {program_title}")
            return None

        return None

    def extract_episode_title(self, episode_or_driver, program_title: str) -> str | None:
        """エピソードタイトルを抽出する（エピソード要素またはエピソード詳細ページから）"""
        # episode_or_driverがWebDriverの場合、エピソード詳細ページからタイトルを抽出
        if hasattr(episode_or_driver, 'find_element') and hasattr(episode_or_driver, 'get'):
            driver = episode_or_driver
            try:
                # エピソード詳細ページからタイトルを抽出
                title_element = WebDriverWait(driver, Constants.Time.DEFAULT_TIMEOUT).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, Constants.CSSSelector.TITLE))
                )
                episode_title = title_element.text.strip().encode('utf-8', 'ignore').decode('utf-8', 'replace')
                if episode_title:
                    self.logger.debug(f"エピソードタイトルを抽出しました: {program_title} - {episode_title}")
                    return episode_title
            except (TimeoutException, NoSuchElementException) as e:
                self.logger.warning(f"エピソードタイトルの取得に失敗しました: {e}")
                return None
        else:
            # エピソード要素からタイトルを抽出
            episode = episode_or_driver
            try:
                title_element = episode.find_element(By.CSS_SELECTOR, 'strong')
                episode_title = title_element.text.strip()
                if episode_title:
                    self.logger.debug(f"エピソードタイトルを抽出しました: {program_title} - {episode_title}")
                    return episode_title
            except NoSuchElementException:
                self.logger.warning(f"エピソードタイトルの取得に失敗しました: {program_title}")
                return None

        return None

    def get_episode_detail_page(self, driver, episode_url: str):
        """エピソード詳細ページに遷移し、ページの準備完了を待つ"""
        driver.get(episode_url)
        WebDriverWait(driver, Constants.Time.DEFAULT_TIMEOUT).until(CustomExpectedConditions.page_is_ready())

    def find_episode_elements(self, driver, program_title: str):
        """エピソード要素リストを取得する"""
        WebDriverWait(driver, Constants.Time.DEFAULT_TIMEOUT).until(CustomExpectedConditions.page_is_ready())
        # 実際の構造ではli要素から検索し、その中のarticle要素を取得
        li_elements = WebDriverWait(driver, Constants.Time.DEFAULT_TIMEOUT).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'li.esl7kn2s'))
        )
        episode_elements = []
        for li_element in li_elements:
            try:
                # li要素自体がエピソード情報を含む場合
                episode_elements.append(li_element)
            except NoSuchElementException:
                continue
        return episode_elements
