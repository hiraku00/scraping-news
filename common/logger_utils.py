import logging

def setup_logger(name: str = __name__) -> logging.Logger:
    """ロガーを設定する"""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.info("ロガーを設定しました。")
    return logger
