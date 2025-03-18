from selenium.webdriver.remote.webdriver import WebDriver

class CustomExpectedConditions:
    """Seleniumのカスタム条件"""
    @staticmethod
    def page_is_ready():
        """ページが完全に読み込まれたことを確認する"""
        return lambda driver: driver.execute_script("return document.readyState") == "complete"
