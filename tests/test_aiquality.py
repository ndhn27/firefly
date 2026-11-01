"""Kiểm tra chất lượng kịch bản AI (scriptgen.review). Chất lượng chữ vẫn do mô hình quyết định; những gì kiểm được là các lỗi MÁY MÓC bắt được
của mô hình nhỏ: lẫn chữ ngôn ngữ khác, tiếng Việt không dấu, lặp câu, lời dẫn thừa, con số có thể bịa. Dùng Ollama giả của test_e6."""
import json

import pytest

import scriptgen as G
from test_e6 import Fake, gen, scenes_json  # noqa: F401  (fixture `fake` lấy từ test_e6 bên dưới)
from test_e6 import fake  # noqa: F401

GOOD = [
    "Đom đóm là loài côn trùng biết phát sáng trong đêm. Ánh sáng của chúng rất lạnh và gần như không toả nhiệt.",
    "Chúng nhấp nháy để gọi bạn tình. Mỗi loài có một nhịp sáng riêng, giống như một mật mã nhỏ.",
    "Ấu trùng đom đóm sống dưới nước hoặc trong đất ẩm. Chúng ăn ốc nhỏ và giun để lớn lên mỗi ngày.",
    "Ngày nay đom đóm ít dần vì ánh đèn thành phố và thuốc trừ sâu. Giữ lại một góc tối là cách giúp chúng sống tiếp.",
]


def sc(*narr):
    return [dict(title=f"Ý {i + 1}", narration=n) for i, n in enumerate(narr)]


def codes(issues, level=None):
    return [i["code"] for i in issues if level is None or i["level"] == level]


def script(narr_list, **kw):
    return json.dumps(dict(scenes=sc(*narr_list), **kw), ensure_ascii=False)


# ----------------------------------------------------------------------------- review(): từng kiểu lỗi
def test_a_clean_vietnamese_script_has_no_problems():
    assert G.review(sc(*GOOD), "Đom đóm là gì?", "vi") == []


def test_stray_chinese_in_vietnamese_is_bad_but_not_fatal_when_it_is_a_few_characters():
    narr = list(GOOD)
    narr[1] = narr[1].replace("riêng", "的riêng")
    iss = G.review(sc(*narr), "", "vi")
    f = next(i for i in iss if i["code"] == "foreign_script")
    assert f["level"] == "bad" and not f["fatal"] and f["scenes"] == [2] and "的" in f["msg"] and "Cảnh 2" in f["fix"]


def test_mostly_foreign_script_is_fatal():
    iss = G.review(sc(*GOOD[:3], "这是一个关于萤火虫的故事，它们在夜晚发光。"), "", "vi")
    assert next(i for i in iss if i["code"] == "foreign_script")["fatal"]


def test_chinese_is_fine_when_the_script_is_supposed_to_be_chinese():
    assert "foreign_script" not in codes(G.review(sc("萤火虫在夜晚发光，它们用光来交流。" * 3), "", "zh"))


def test_vietnamese_without_diacritics_or_in_english_is_fatal():
    en = sc("Fireflies are insects that glow in the dark. Their light is cold and gives off almost no heat at all.",
            "They flash to call a mate. Every species has its own rhythm, like a tiny secret code.")
    iss = G.review(en, "", "vi")
    assert next(i for i in iss if i["code"] == "not_vietnamese")["fatal"]
    assert "not_vietnamese" not in codes(G.review(en, "", "en")), "tiếng Anh cho video tiếng Anh thì đúng"
    nodau = sc("Dom dom la loai con trung biet phat sang trong dem. Anh sang cua chung rat lanh va gan nhu khong toa nhiet.",
               "Chung nhap nhay de goi ban tinh. Moi loai co mot nhip sang rieng giong nhu mot mat ma nho.")
    assert "not_vietnamese" in codes(G.review(nodau, "", "vi"))


def test_a_sentence_repeated_four_times_is_a_loop_but_three_is_not():
    rep = "Ánh sáng của đom đóm rất đẹp và rất lạnh."
    assert "loop" in codes(G.review(sc(GOOD[0] + " " + rep, GOOD[1] + " " + rep, GOOD[2] + " " + rep, GOOD[3] + " " + rep), "", "vi"), "bad")
    assert "loop" not in codes(G.review(sc(GOOD[0] + " " + rep, GOOD[1] + " " + rep, GOOD[2] + " " + rep, GOOD[3]), "", "vi"))


def test_two_identical_scenes_are_bad():
    iss = G.review(sc(GOOD[0], GOOD[1], GOOD[0]), "", "vi")
    d = next(i for i in iss if i["code"] == "duplicate_scene")
    assert d["level"] == "bad" and d["scenes"] == [1, 3]


@pytest.mark.parametrize("bad", ["Dưới đây là kịch bản cho video của bạn: đom đóm phát sáng trong đêm tối.",
                                 "Chắc chắn rồi! Đom đóm phát sáng trong đêm tối nhờ một phản ứng hoá học.",
                                 "Đom đóm phát sáng trong đêm tối, xem thêm tại [tên kênh của bạn] nhé các bạn.",
                                 "Here is the script: đom đóm phát sáng trong đêm tối nhờ phản ứng hoá học."])
def test_leftover_assistant_chatter_and_placeholders_are_bad(bad):
    assert "boilerplate" in codes(G.review(sc(bad, GOOD[1], GOOD[2]), "", "vi"), "bad")


def test_the_word_kich_ban_inside_a_sentence_is_not_chatter():
    assert G.review(sc("Biên kịch viết kịch bản trước, rồi mới quay phim. Đây là kịch bản đầu tiên của nhiều người.", GOOD[1], GOOD[2]), "", "vi") == []


def test_web_address_is_only_a_warning():
    iss = G.review(sc(GOOD[0], "Xem thêm tại github.com để biết cách chia sẻ mã nguồn với mọi người trên thế giới.", GOOD[2]), "", "vi")
    assert codes(iss, "bad") == [] and "url" in codes(iss, "warn")


def test_numbers_without_a_source_are_flagged_for_checking():
    iss = G.review(sc("Đom đóm có hơn 2000 loài trên thế giới. Chúng xuất hiện từ khoảng 1947 theo một số ghi chép, và 38% sống gần nước.", GOOD[1]), "Đom đóm là gì?", "vi")
    n = next(i for i in iss if i["code"] == "numbers")
    assert n["level"] == "warn" and all(x in n["msg"] for x in ("2000", "1947", "38%")) and "tự đưa ra" in n["msg"]


def test_numbers_are_checked_against_pasted_source():
    source = "Đom đóm: theo ghi chép năm 1947 có hơn 2000 loài đã được mô tả. " * 6
    iss = G.review(sc("Có hơn 2000 loài đom đóm, được ghi lại từ năm 1947, và 38% sống gần nước.", GOOD[1]), source, "vi")
    n = next(i for i in iss if i["code"] == "numbers")
    assert "38%" in n["msg"] and "2000" not in n["msg"] and "1947" not in n["msg"] and "KHÔNG có trong tư liệu" in n["msg"]


def test_small_numbers_are_not_flagged():
    assert "numbers" not in codes(G.review(sc("Đom đóm có 6 chân và 2 cánh, sống khoảng 3 tuần trong đêm hè.", GOOD[1]), "", "vi"))


def test_very_uneven_scenes_and_too_long_sentences_are_warnings():
    long_scene = " ".join(["Đom đóm phát sáng trong đêm và chúng rất đẹp mắt đối với mọi người."] * 9)
    iss = G.review(sc(GOOD[0], long_scene, GOOD[1], GOOD[2]), "", "vi")
    assert "unbalanced" in codes(iss, "warn")
    run_on = "Đom đóm " + " và ".join(["phát sáng trong đêm tối rất đẹp"] * 8) + "."
    assert "long_sentence" in codes(G.review(sc(GOOD[0], run_on, GOOD[1]), "", "vi"), "warn")


# ----------------------------------------------------------------------------- generate(): thử lại và chọn bản tốt nhất
def request_texts(fake):
    return [m["content"] for r in fake.requests for m in r["messages"] if m["role"] == "user"]


def test_prompt_tells_the_model_not_to_invent_figures_or_mix_scripts():
    sysmsg = G.build_messages("Đom đóm", 60, "explain", "vi")[0]["content"]
    assert "Không bịa số liệu" in sysmsg and "Không chen chữ Hán" in sysmsg
    assert "Không chen chữ Hán" not in G.build_messages("萤火虫", 60, "explain", "zh")[0]["content"]


def test_model_that_mixes_in_chinese_is_asked_again_with_the_exact_problem(fake):
    mixed = [n for n in GOOD]
    mixed[2] = mixed[2].replace("nước", "水nước")
    fake.replies = [script(mixed), script(GOOD)]
    r = gen(fake, duration=30)
    assert r["attempts"] == 2 and not any(w["code"] == "foreign_script" for w in r["warnings"])
    feedback = request_texts(fake)[-1]
    assert "Cảnh 3" in feedback and "水" in feedback and "Chỉ viết bằng tiếng Việt" in feedback


def test_clean_attempt_beats_a_better_length_attempt_that_has_chatter(fake):
    chatter = [GOOD[0].replace("Đom đóm", "Dưới đây là kịch bản: đom đóm", 1)] + GOOD[1:]
    fake.replies = [script(chatter), script(GOOD)]
    r = gen(fake, duration=30)
    assert r["attempts"] == 2 and "boilerplate" not in [w["code"] for w in r["warnings"]]


def test_when_every_attempt_has_a_fixable_problem_the_best_one_is_returned_with_warnings(fake):
    mixed = list(GOOD)
    mixed[2] = mixed[2].replace("nước", "水nước")
    fake.replies = [script(mixed)] * 3
    r = gen(fake, duration=30)
    w = next(x for x in r["warnings"] if x["code"] == "foreign_script")
    assert r["attempts"] in (1, 2, 3) and w["level"] == "bad" and w["scenes"] == [3]
    assert "水" in r["text"], "chữ lạ để nguyên trong ô dán cho người dùng thấy và sửa, không lặng lẽ xoá"


def test_wrong_language_every_time_is_an_error_not_a_useless_draft(fake):
    english = ["Fireflies are insects that glow in the dark. Their light is cold and gives off almost no heat at all.",
               "They flash to call a mate. Every species has its own rhythm, like a tiny secret code in the night.",
               "The larvae live in water or damp soil. They eat small snails and worms to grow bigger every day.",
               "Today fireflies are fewer because of city lights. Keeping one dark corner helps them survive."]
    fake.replies = [script(english)] * 3
    with pytest.raises(G.ScriptError) as ei:
        gen(fake, duration=30)
    assert "viết sai ngôn ngữ 3 lần liền" in str(ei.value) and "lớn hơn" in str(ei.value)
    assert len(fake.requests) == 3


def test_warnings_reach_the_result_even_when_nothing_needs_a_retry(fake):
    fake.replies = [script(["Đom đóm có hơn 2000 loài trên thế giới, theo một thống kê năm 1947 của các nhà côn trùng học.", GOOD[1], GOOD[2], GOOD[3]])]
    r = gen(fake, duration=30)
    assert r["attempts"] == 1 and [w["code"] for w in r["warnings"]] == ["numbers"]


# ----------------------------------------------------------------------------- danh sách mô hình
def test_model_size_is_parsed_and_small_models_are_marked():
    assert G._params({"details": {"parameter_size": "7.6B"}}) == dict(params="7.6B", small=False)
    assert G._params({"details": {"parameter_size": "494M"}}) == dict(params="494M", small=True)
    assert G._params({"details": {"parameter_size": "3.2B"}}) == dict(params="3.2B", small=True)
    assert G._params({"details": {"parameter_size": "3.8B"}}) == dict(params="3.8B", small=False)
    assert G._params({"details": {"parameter_size": "unknown"}}) == {} and G._params({}) == {} and G._params({"details": None}) == {}


def test_list_models_includes_size_info_when_ollama_reports_it(fake):
    fake.details = {"llama3.1:8b": {"parameter_size": "8.0B"}, "qwen2.5:7b": {"parameter_size": "1.5B"}}
    ms = {m["name"]: m for m in G.list_models(fake.url)}
    assert ms["llama3.1:8b"]["params"] == "8.0B" and not ms["llama3.1:8b"]["small"] and ms["qwen2.5:7b"]["small"]
