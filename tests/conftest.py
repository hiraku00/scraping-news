import pytest
from unittest.mock import MagicMock
from common.utils import Constants

@pytest.fixture
def mock_driver():
    """Seleniumドライバーのモック"""
    driver = MagicMock()
    return driver

@pytest.fixture
def mock_logger():
    """ロガーのモック"""
    logger = MagicMock()
    return logger

@pytest.fixture
def mock_wait():
    """WebDriverWaitのモック"""
    wait = MagicMock()
    return wait

@pytest.fixture
def test_config():
    """テスト用の設定"""
    return {
        "テスト番組": {
            "url": "https://example.com/program",
            "channel": "TEST",
            "time": "12:00-13:00"
        }
    }

@pytest.fixture
def mock_element():
    """Selenium要素のモック"""
    element = MagicMock()
    element.text = "テストテキスト"
    element.get_attribute.return_value = "https://example.com"
    return element

def create_mock_element(text="", href=None):
    """モックの要素を作成するヘルパー関数"""
    element = MagicMock()
    element.text = text
    element.get_attribute.return_value = href if href else None
    return element
