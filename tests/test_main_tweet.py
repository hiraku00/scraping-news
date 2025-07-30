"""
main.py の --tweet オプションのテスト

このテストは実際にツイートを送信せず、コンソール出力のみを検証します。
"""
import os
import sys
import pytest
from unittest.mock import patch, MagicMock, call
from io import StringIO

# テスト用のツイートデータ
TEST_TWEETS = [
    "25/01/29(水)のニュース・ドキュメンタリー番組など\n\n25/01/29(水)のニュース・ドキュメンタリー番組など",
    "これはテスト用のツイートです。\n---\n2つ目のツイートです。スレッドとして投稿されます。\n---\n3つ目のツイートです。最後のツイートです。"
]

@pytest.fixture
def setup_test_files(tmp_path):
    """テスト用の一時ファイルとディレクトリをセットアップ"""
    # 出力ディレクトリを作成
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    
    # テスト用のツイートファイルを作成
    tweet_file = output_dir / "20250129.txt"
    tweet_file.write_text("\n---\n".join(TEST_TWEETS))
    
    return str(output_dir), str(tweet_file)

@pytest.fixture
def mock_tweepy():
    """tweepyのモックを設定"""
    with patch('tweepy.Client') as mock_client_class, \
         patch('tweepy.API') as mock_api_class:
        
        # モックのレスポンスを作成
        mock_response = MagicMock()
        mock_response.data = {"id": "1234567890"}
        
        # モックのインスタンスを設定
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        # get_meメソッドの戻り値を設定
        mock_user = MagicMock()
        mock_user.data = MagicMock(username="testuser")
        mock_client.get_me.return_value = mock_user
        
        # create_tweetメソッドの戻り値を設定
        mock_client.create_tweet.return_value = mock_response
        
        # APIモック
        mock_api = MagicMock()
        mock_api_class.return_value = mock_api
        
        yield mock_client, mock_api

def test_main_tweet_command(setup_test_files, mock_tweepy, capsys):
    """main.py の run_tweet 関数のテスト"""
    output_dir, tweet_file = setup_test_files
    mock_client, _ = mock_tweepy
    
    # テスト対象の関数をインポート
    from main import run_tweet
    
    # テスト実行
    with patch('tweepy.Client', return_value=mock_client):
        # run_tweet 関数を直接呼び出す
        result = run_tweet("20250129", output_dir=output_dir)
        
        # 正常終了することを確認
        assert result is True
    
    # 標準出力を取得
    captured = capsys.readouterr()
    output = captured.out + captured.err  # 標準エラーも含める
    
    # 期待される出力が含まれているか確認
    expected_outputs = [
        "=== tweet 処理開始 ===",
        "対象日付: 20250129",
        "2 件のツイート候補を読み込みました。"
    ]
    
    for expected in expected_outputs:
        assert expected in output, f"Expected output not found: {expected}"
    
    # ツイート内容が表示されているか確認
    for tweet in TEST_TWEETS:
        assert tweet in output, f"Tweet not found in output: {tweet}"
    
    # ツイートが正しい回数呼び出されたか確認
    assert mock_client.create_tweet.call_count == 2, \
        f"Expected 2 tweets, but got {mock_client.create_tweet.call_count}"
