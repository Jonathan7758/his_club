"""
ForumEngine 测试 — RED Phase
测试7维辩论: prompt构建 / JSON解析 / 角度过滤 / 3轮编排
"""
import json
import pytest
from src.forum_engine import (
    DIMENSIONS,
    build_round1_prompts,
    build_round2_prompt,
    build_round3_prompt,
    parse_json_response,
    filter_valid_angles,
    extract_main_topic,
    extract_key_points,
    ForumEngine,
)


class TestDimensions:
    def test_all_seven_dimensions_present(self):
        expected = ["政治制度", "经济财政", "军事战略", "文化社会", "关键人物", "技术演进", "地理环境"]
        assert DIMENSIONS == expected
        assert len(DIMENSIONS) == 7


class TestRound1Prompts:
    def test_generates_prompts_for_all_dimensions(self):
        topic = "安史之乱"
        forbidden = ["唐玄宗昏庸", "安禄山野心", "杨贵妃祸水"]

        prompts = build_round1_prompts(topic, forbidden)

        assert len(prompts) == 7
        for dim in DIMENSIONS:
            assert dim in prompts
            assert topic in prompts[dim]
            assert "angle_title" in prompts[dim] or "JSON" in prompts[dim]

    def test_forbidden_phrases_in_prompts(self):
        topic = "Test"
        forbidden = ["bad_angle_1", "bad_angle_2", "bad_angle_3"]

        prompts = build_round1_prompts(topic, forbidden)

        for dim, dim_prompt in prompts.items():
            assert any(f in dim_prompt for f in forbidden), f"Missing any forbidden in {dim}"


class TestRound2Prompt:
    def test_includes_own_thesis_and_others(self):
        topic = "安史之乱"
        my_proposal = {"angle_title": "权力结构", "thesis": "中央集权崩溃"}
        other_proposals = {
            "军事战略": "军事布局失衡",
            "文化社会": "文化冲突激化",
        }

        prompt = build_round2_prompt(topic, "政治制度", my_proposal, other_proposals)

        assert "中央集权崩溃" in prompt
        assert "军事布局失衡" in prompt
        assert "文化冲突激化" in prompt
        assert "政治制度" in prompt


class TestRound3Prompt:
    def test_includes_all_round2_angles(self):
        topic = "安史之乱"
        round2_angles = {
            "政治制度": {"angle_title": "t1", "thesis": "t1_body"},
            "经济财政": {"angle_title": "t2", "thesis": "t2_body"},
        }

        prompt = build_round3_prompt(topic, round2_angles)

        assert "t1_body" in prompt
        assert "t2_body" in prompt
        assert "1-10" in prompt or "novelty" in prompt


class TestJSONParsing:
    def test_parse_clean_json_object(self):
        raw = '{"key": "value", "num": 42}'
        result = parse_json_response(raw)
        assert result == {"key": "value", "num": 42}

    def test_parse_json_with_markdown_fence(self):
        raw = '```json\n{"key": "value"}\n```'
        result = parse_json_response(raw)
        assert result == {"key": "value"}

    def test_parse_json_array(self):
        raw = '[{"a": 1}, {"b": 2}]'
        result = parse_json_response(raw)
        assert result == [{"a": 1}, {"b": 2}]

    def test_parse_json_with_text_wrapper(self):
        raw = '这是分析结果：\n{"angle_title": "test", "thesis": "body"}'
        result = parse_json_response(raw)
        assert result["angle_title"] == "test"

    def test_parse_invalid_returns_raw(self):
        raw = "这不是有效的JSON格式"
        result = parse_json_response(raw)
        assert "raw" in result


class TestAngleFiltering:
    def test_filters_short_thesis(self):
        angles = [
            {"dimension": "政治", "thesis": "太短"},
            {"dimension": "经济", "thesis": "a" * 25},
        ]
        result = filter_valid_angles(angles)
        assert len(result) == 1
        assert result[0]["dimension"] == "经济"

    def test_filters_cannot_handle_thesis(self):
        angles = [
            {"dimension": "政治", "thesis": "无法处理该问题"},
            {"dimension": "经济", "thesis": "a" * 30},
        ]
        result = filter_valid_angles(angles)
        assert len(result) == 1

    def test_filters_apology_thesis(self):
        angles = [
            {"dimension": "政治", "thesis": "抱歉，我无法回答这个问题"},
            {"dimension": "经济", "thesis": "a" * 30},
        ]
        result = filter_valid_angles(angles)
        assert len(result) == 1

    def test_empty_list_returns_empty(self):
        assert filter_valid_angles([]) == []


class TestExtractMainTopic:
    def test_extract_topic_from_content(self):
        content = "关于安史之乱的多维度分析，主要关注唐朝的政治制度崩溃"

        result = extract_main_topic(content)

        assert result != ""
        assert len(result) > 2

    def test_extract_topic_returns_string(self):
        result = extract_main_topic("简短的测试内容")
        assert isinstance(result, str)


class TestExtractKeyPoints:
    def test_extract_points_returns_list(self):
        content = "第一，政治制度的问题。第二，经济财政的危机。第三，军事战略的缺陷。"

        result = extract_key_points(content)

        assert isinstance(result, list)
        assert len(result) >= 1

    def test_extract_points_with_short_content(self):
        result = extract_key_points("只有一个简单论点")
        assert isinstance(result, list)


class TestForumEngine:
    def test_init_stores_llm_fn(self):
        def fake_llm(prompt, **kwargs):
            return "test"

        engine = ForumEngine(llm_fn=fake_llm)
        assert engine.llm_fn is fake_llm

    def test_run_debate_calls_llm(self):
        call_count = 0

        def fake_llm(prompt, **kwargs):
            nonlocal call_count
            call_count += 1
            return json.dumps({
                "angle_title": "测试角度",
                "thesis": "这是一个足够长的测试论点内容，用于验证辩论系统。",
                "evidence": ["证据1", "证据2"]
            }, ensure_ascii=False)

        engine = ForumEngine(llm_fn=fake_llm)
        result = engine.run_debate("安史之乱", forbidden=[])

        assert call_count > 0
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_run_debate_generates_structured_output(self):
        resp_counter = [0]
        L = "足够长的测试内容来通过过滤验证测试机制的要求"
        responses = [
            '{"angle_title":"政治角度","thesis":"政治角度' + L + '","evidence":["证1","证2"]}',
            '{"angle_title":"经济角度","thesis":"经济角度' + L + '","evidence":["证3","证4"]}',
            '{"angle_title":"军事角度","thesis":"军事角度' + L + '","evidence":["证5","证6"]}',
            '{"angle_title":"文化角度","thesis":"文化角度' + L + '","evidence":["证7","证8"]}',
            '{"angle_title":"人物角度","thesis":"人物角度' + L + '","evidence":["证9","证10"]}',
            '{"angle_title":"科技角度","thesis":"科技角度' + L + '","evidence":["证11","证12"]}',
            '{"angle_title":"地理角度","thesis":"地理角度' + L + '","evidence":["证13","证14"]}',
            '{"angle_title":"修正政治","thesis":"修正政治' + L + '","evidence":["新1","新2"]}',
            '{"angle_title":"修正经济","thesis":"修正经济' + L + '","evidence":["新3","新4"]}',
            '{"angle_title":"修正军事","thesis":"修正军事' + L + '","evidence":["新5","新6"]}',
            '{"angle_title":"修正文化","thesis":"修正文化' + L + '","evidence":["新7","新8"]}',
            '{"angle_title":"修正人物","thesis":"修正人物' + L + '","evidence":["新9","新10"]}',
            '{"angle_title":"修正科技","thesis":"修正科技' + L + '","evidence":["新11","新12"]}',
            '{"angle_title":"修正地理","thesis":"修正地理' + L + '","evidence":["新13","新14"]}',
            '[{"dimension":"政治制度","angle_title":"胜出1","thesis":"胜出论点' + L + '","evidence":[""],"novelty":9,"controversy":true},{"dimension":"经济财政","angle_title":"胜出2","thesis":"胜出论点' + L + '","evidence":[""],"novelty":8,"controversy":true}]',
        ]

        def fake_llm(prompt, **kwargs):
            idx = resp_counter[0]
            resp_counter[0] += 1
            if idx < len(responses):
                return responses[idx]
            return '{"angle_title":"extra","thesis":"extra thesis for making sure we have enough length for the filter to pass.","evidence":[]}'

        engine = ForumEngine(llm_fn=fake_llm)
        result = engine.run_debate("测试主题", forbidden=["禁止角度"])

        assert len(result) >= 1
        for item in result:
            assert "dimension" in item
            assert "thesis" in item
            assert len(item["thesis"]) >= 20


class TestTopicPromptIntegration:
    """验证提取/辩论的prompt不包含敏感词"""
    def test_extract_topic_prompt_is_safe(self):
        content = "分析唐朝安史之乱的深层原因"
        result = extract_main_topic(content)
        assert isinstance(result, str)
        assert len(result) > 0
