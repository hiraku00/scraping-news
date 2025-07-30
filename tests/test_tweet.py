import os
import sys
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

# テスト対象のモジュールをインポートできるようにパスを追加
sys.path.append(str(Path(__file__).parent.parent))

# テスト用の一時ディレクトリとファイルを作成するためのフィクスチャ
@pytest.fixture
def setup_test_files(tmp_path):
    # テスト用の一時ディレクトリにoutputディレクトリを作成
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    
    # テスト用のツイートファイルを作成
    tweet_file = output_dir / "20250129.txt"
    tweet_content = """これは最初のツイートです。テスト用のツイート内容です。
複数行にわたるツイートもテストします。

2つ目のツイートです。スレッドとして投稿されます。

3つ目のツイートです。最後のツイートです。"""
    tweet_file.write_text(tweet_content, encoding="utf-8")
    
    # 環境変数を設定
    env_vars = {
        "API_KEY": "test_api_key",
        "API_SECRET": "test_api_secret",
        "ACCESS_TOKEN": "test_access_token",
        "ACCESS_SECRET": "test_access_secret",
        "BEARER_TOKEN": "test_bearer_token"
    }
    
    # 元の環境変数を保存して、テスト用の環境変数を設定
    original_env = {}
    for key, value in env_vars.items():
        original_env[key] = os.environ.get(key)
        os.environ[key] = value
    
    yield str(tmp_path), str(tweet_file)
    
    # 環境変数を元に戻す
    for key, value in original_env.items():
        if value is not None:
            os.environ[key] = value
        else:
            os.environ.pop(key, None)

# ログ出力をキャプチャするためのフィクスチャ
@pytest.fixture
def captured_logs(capsys):
    import logging
    from io import StringIO
    
    # ログをキャプチャするためのストリームを作成
    log_stream = StringIO()
    
    # ルートロガーを取得して設定
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # 既存のハンドラを削除
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # ストリームハンドラを追加
    handler = logging.StreamHandler(log_stream)
    handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    logger.addHandler(handler)
    
    # キャプチャ用のストリームを返す
    yield log_stream
    
    # 後片付け
    logger.removeHandler(handler)
    log_stream.close()

def test_tweet_main_success(setup_test_files, captured_logs):
    """tweet.main()の正常系テスト"""
    tmp_dir, tweet_file = setup_test_files
    
    # モックのレスポンスを作成
    mock_response = MagicMock()
    mock_response.data = {"id": "1234567890"}
    
    # tweepy.Clientのモックを作成
    with patch('tweepy.Client') as mock_client_class:
        # モックのインスタンスを設定
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        # get_meメソッドの戻り値を設定
        mock_user = MagicMock()
        mock_user.data = MagicMock(username="testuser")
        mock_client.get_me.return_value = mock_user
        
        # create_tweetメソッドの戻り値を設定
        mock_client.create_tweet.return_value = mock_response
        
        # テスト対象の関数をインポート（パッチ後にインポートするのがポイント）
        from tweet import main
        
        # テスト実行（一時ディレクトリを出力先として指定）
        result = main(date="20250129", output_dir=os.path.join(tmp_dir, "output"))
        
        # 結果を検証
        assert result == 0  # 正常終了コード
        
        # ログ出力を取得
        captured_logs.seek(0)
        logs = captured_logs.read()
        
        # 期待されるログメッセージが含まれているか確認
        assert "APIキー/トークン環境変数を読み込みました。" in logs
        assert "Twitter API認証成功: @testuser" in logs
        assert "対象日付: 20250129" in logs
        assert "3 件のツイート候補を読み込みました。" in logs
        
        # ツイート内容がログに出力されているか確認
        assert "1/3 件目のツイート内容:" in logs
        assert "これは最初のツイートです。" in logs
        assert "2/3 件目のツイート内容" in logs
        assert "2つ目のツイートです。" in logs
        assert "3/3 件目のツイート内容" in logs
        assert "3つ目のツイートです。" in logs
        
        # ツイートが正しい回数呼び出されたか確認
        assert mock_client.create_tweet.call_count == 3
        
        # 最初のツイートの内容を確認
        first_call_args = mock_client.create_tweet.call_args_list[0]
        assert "text" in first_call_args[1]
        # 期待する日付フォーマット: "25/01/29(水)のニュース・ドキュメンタリー番組など"
        assert "25/01/29(水)のニュース・ドキュメンタリー番組など" in first_call_args[1]["text"]
        assert "これは最初のツイートです。" in first_call_args[1]["text"]
        
        # 2つ目のツイートがスレッドとして投稿されているか確認
        second_call_args = mock_client.create_tweet.call_args_list[1]
        assert "in_reply_to_tweet_id" in second_call_args[1]
        assert second_call_args[1]["in_reply_to_tweet_id"] == "1234567890"

def test_tweet_main_file_not_found():
    """ファイルが存在しない場合のテスト"""
    with patch('tweepy.Client'):
        # テスト対象の関数をインポート
        from tweet import main
        
        # テスト実行（存在しない日付を指定）
        result = main(date="99999999")
        
        # 結果を検証（ファイルが見つからない場合は1を返す）
        assert result == 1

# テストを実行するためのコード
if __name__ == "__main__":
    pytest.main(["-v", __file__])
