"""
Search 工具测试 — RED Phase
测试: 搜狗微信搜索 / 搜狗网页搜索 (mock 网络层)
"""
import pytest
from unittest.mock import patch, MagicMock
from src.search import weixin_search, sogou_web_search


class TestWeixinSearch:
    def test_returns_list_on_success(self):
        mock_html = """
        <html><body>
        <ul class="news-list">
            <li><h3><a>测试文章标题</a></h3><p>测试描述内容</p></li>
            <li><h3><a>另一篇文章</a></h3><p>另一段描述</p></li>
        </ul>
        </body></html>
        """
        mock_resp = MagicMock()
        mock_resp.text = mock_html

        with patch("requests.get", return_value=mock_resp):
            result = weixin_search("安史之乱")

        assert isinstance(result, list)
        assert len(result) >= 2
        assert "测试文章标题" in result[0]
        assert "测试描述内容" in result[0]

    def test_returns_fallback_on_empty(self):
        mock_html = "<html><body></body></html>"
        mock_resp = MagicMock()
        mock_resp.text = mock_html

        with patch("requests.get", return_value=mock_resp):
            result = weixin_search("安史之乱")

        assert result == ["无公众号文章"]

    def test_returns_empty_on_error(self):
        with patch("requests.get", side_effect=Exception("Network down")):
            result = weixin_search("安史之乱")

        assert result == []

    def test_respects_max_results(self):
        mock_html = """
        <html><body>
        <ul class="news-list">
            <li><h3><a>文章1</a></h3><p>描述1</p></li>
            <li><h3><a>文章2</a></h3><p>描述2</p></li>
            <li><h3><a>文章3</a></h3><p>描述3</p></li>
            <li><h3><a>文章4</a></h3><p>描述4</p></li>
        </ul>
        </body></html>
        """
        mock_resp = MagicMock()
        mock_resp.text = mock_html

        with patch("requests.get", return_value=mock_resp):
            result = weixin_search("test", max_results=2)

        assert len(result) == 2


class TestSogouWebSearch:
    def test_returns_list_on_success(self):
        mock_html = """
        <html><body>
        <div class="vrwrap"><h3><a>搜索结果标题</a></h3><p class="star-wiki">搜索结果摘要</p></div>
        <div class="result"><h3><a>另一个结果</a></h3><p>另一个摘要</p></div>
        </body></html>
        """
        mock_resp = MagicMock()
        mock_resp.text = mock_html

        with patch("requests.get", return_value=mock_resp):
            result = sogou_web_search("安史之乱")

        assert isinstance(result, list)
        assert len(result) >= 2

    def test_returns_empty_on_error(self):
        with patch("requests.get", side_effect=Exception("Timeout")):
            result = sogou_web_search("安史之乱")

        assert result == []

    def test_respects_max_results(self):
        mock_html = """
        <html><body>
        <div class="result"><h3><a>结果1</a></h3><p>摘要1</p></div>
        <div class="result"><h3><a>结果2</a></h3><p>摘要2</p></div>
        <div class="result"><h3><a>结果3</a></h3><p>摘要3</p></div>
        </body></html>
        """
        mock_resp = MagicMock()
        mock_resp.text = mock_html

        with patch("requests.get", return_value=mock_resp):
            result = sogou_web_search("test", max_results=1)

        assert len(result) == 1
