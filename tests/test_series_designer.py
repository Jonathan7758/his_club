"""
SeriesDesigner 测试 — RED Phase
测试: 主主题→7维子系列拆分，每项含名称/核心观点/大纲/金句
"""
import pytest
from src.series_designer import SeriesDesigner, DIMENSION_LABELS


class TestDimensionLabels:
    def test_seven_labels_mapped(self):
        assert len(DIMENSION_LABELS) == 7
        assert DIMENSION_LABELS["政治制度"] == "政"
        assert "技术演进" in DIMENSION_LABELS
        assert "地理环境" in DIMENSION_LABELS


class TestSeriesDesigner:
    def test_init_stores_llm_fn(self):
        def fake_llm(prompt, **kwargs):
            return "test"

        sd = SeriesDesigner(llm_fn=fake_llm)
        assert sd.llm_fn is fake_llm

    def test_design_sub_series_generates_structured_output(self):
        fake_responses = [
            '{"name":"权力的代价","viewpoint":"节度使制度是根本原因","outline":["府兵到募兵","三权合一","中央与地方","制度代价"],"quotes":["忠诚成了奢侈品","权力失衡的代价"]}',
            '{"name":"叛乱的经济账","viewpoint":"经济结构失衡","outline":["赋税体系","军费开支","财政崩溃"],"quotes":["战争是最昂贵的消费","经济崩溃加速"]}',
            '{"name":"军事地理","viewpoint":"军事布局漏洞","outline":["关隘分布","兵力配置","后勤线"],"quotes":["地理决定战争","后勤是命脉"]}',
            '{"name":"文化碰撞","viewpoint":"胡汉文化冲突","outline":["华夷之辨","文化融合","社会断层"],"quotes":["文化的边界","碰撞后的火花"]}',
            '{"name":"人物群像","viewpoint":"边缘人物视角","outline":["被忽视的幕僚","地方势力","偶然的个体"],"quotes":["历史是人的历史"]}',
            '{"name":"技术决定","viewpoint":"技术路径依赖","outline":["冶铁技术","马政制度","信息传递"],"quotes":["技术改变历史"]}',
            '{"name":"地理棋局","viewpoint":"环境约束","outline":["气候变迁","水系分布","人口密度"],"quotes":["地理是历史的舞台"]}',
        ]

        resp_counter = [0]

        def fake_llm(prompt, **kwargs):
            idx = resp_counter[0]
            resp_counter[0] += 1
            return fake_responses[idx % len(fake_responses)]

        sd = SeriesDesigner(llm_fn=fake_llm)
        result = sd.design_series("安史之乱", key_points=["论点1", "论点2"])

        assert len(result) == 7
        for item in result:
            assert "dimension" in item
            assert "name" in item
            assert "viewpoint" in item
            assert "outline" in item
            assert "quotes" in item
            assert len(item["outline"]) >= 2
            assert len(item["quotes"]) >= 1

    def test_design_prompt_includes_topic(self):
        call_captured = []

        def fake_llm(prompt, **kwargs):
            call_captured.append(prompt)
            return '{"name":"test","viewpoint":"test vp","outline":["a","b","c"],"quotes":["q1","q2"]}'

        sd = SeriesDesigner(llm_fn=fake_llm)
        sd.design_series("测试主题", key_points=["k1"])

        assert len(call_captured) > 0
        assert "测试主题" in call_captured[0]

    def test_design_with_no_key_points_still_works(self):
        def fake_llm(prompt, **kwargs):
            return '{"name":"test","viewpoint":"vp","outline":["a","b"],"quotes":["q"]}'

        sd = SeriesDesigner(llm_fn=fake_llm)
        result = sd.design_series("主题", key_points=None)

        assert len(result) == 7

    def test_modify_sub_series_item(self):
        def fake_llm(prompt, **kwargs):
            return '{"name":"test","viewpoint":"vp","outline":["a","b"],"quotes":["q"]}'

        sd = SeriesDesigner(llm_fn=fake_llm)
        series = sd.design_series("主题")

        modified = sd.modify_item(series, 0, name="新的名称")
        assert modified[0]["name"] == "新的名称"

        modified2 = sd.modify_item(series, 1, viewpoint="新观点")
        assert modified2[1]["viewpoint"] == "新观点"

    def test_modify_item_index_bounds(self):
        sd = SeriesDesigner(llm_fn=lambda p, **kw: "{}")
        series = [{"dimension": "政治制度", "name": "x", "viewpoint": "v", "outline": [], "quotes": []}]

        with pytest.raises(IndexError):
            sd.modify_item(series, 5, name="bad")

    def test_get_dimension_summary(self):
        def fake_llm(prompt, **kwargs):
            return '{"name":"权力的代价","viewpoint":"节度使制度是根本原因","outline":["府兵到募兵","三权合一","中央与地方","制度代价"],"quotes":["忠诚成了奢侈品"]}'

        sd = SeriesDesigner(llm_fn=fake_llm)
        series = sd.design_series("安史之乱")

        summary = sd.get_summary(series)

        assert "权力的代价" in summary and len(summary) > 0
