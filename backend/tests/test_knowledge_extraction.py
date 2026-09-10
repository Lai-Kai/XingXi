from wu_culture.extraction import extract_knowledge
from wu_culture.models import EntityType
from wu_culture.relations import RelationType


def test_extracts_entities_relations_events_and_aliases_from_simple_text() -> None:
    result = extract_knowledge("永安桥位于木渎镇。永安桥由孙公冕营建。1497年永安桥完成修建。木渎镇旧称渎川。")

    by_name = {item.name: item for item in result.entities}
    assert by_name["永安桥"].entity_type is EntityType.BRIDGE
    assert by_name["木渎镇"].entity_type is EntityType.PLACE
    assert by_name["孙公冕"].entity_type is EntityType.PERSON
    assert {item.relation_type for item in result.relations} == {
        RelationType.LOCATED_IN,
        RelationType.BUILT_BY,
    }
    assert result.events[0].start_time == "1497"
    assert result.aliases[0].canonical_name == "木渎镇"
    assert result.aliases[0].alias == "渎川"


def test_does_not_promote_placeholder_person_into_historical_graph() -> None:
    result = extract_knowledge("永安桥由张三营建。")

    assert "张三" not in {item.name for item in result.entities}
    assert not result.relations


def test_empty_text_is_rejected() -> None:
    try:
        extract_knowledge("  ")
    except ValueError as exc:
        assert str(exc) == "text cannot be empty"
    else:
        raise AssertionError("empty input must be rejected")


def test_extracts_person_and_place_relation_vocabulary() -> None:
    result = extract_knowledge(
        "李明与王芳是姐弟。李明居住于木渎镇。王芳游览木渎镇。"
    )

    assert {item.relation_type for item in result.relations} == {
        RelationType.SIBLING_OF,
        RelationType.LIVED_IN,
        RelationType.VISITED,
    }
    by_name = {item.name: item for item in result.entities}
    assert by_name["李明"].entity_type is EntityType.PERSON
    assert by_name["王芳"].entity_type is EntityType.PERSON
    assert by_name["木渎镇"].entity_type is EntityType.PLACE


def test_extracts_documentary_activity_relations() -> None:
    result = extract_knowledge("康熙帝游览灵岩山。罗楚珍卒于木渎。皎然在上真观赋诗。")

    assert {
        item.relation_type
        for item in result.relations
    } == {
        RelationType.VISITED,
        RelationType.DIED_AT,
        RelationType.COMPOSED_AT,
    }
    assert {(item.subject_name, item.object_name) for item in result.relations} == {
        ("康熙帝", "灵岩山"),
        ("罗楚珍", "木渎"),
        ("皎然", "上真观"),
    }


def test_does_not_turn_generic_arrival_words_into_relations() -> None:
    result = extract_knowledge(
        "自吴亡至今仅二千载。系统支持多角色切换，用户到员工端查看记录。"
    )

    assert result.relations == ()


def test_classical_headings_and_distances_are_normalized() -> None:
    result = extract_knowledge(
        "右五乾元觀，在常熟一里虞山下。梁天監五年，張裕先生來此山，栖遁十餘載。"
    )

    by_name = {item.name: item for item in result.entities}
    assert "乾元觀" in by_name
    assert "虞山" in by_name
    assert "張裕" in by_name
    assert "右五乾元觀" not in by_name
    assert "常熟一里虞山" not in by_name
    assert {
        (item.subject_name, item.relation_type, item.object_name)
        for item in result.relations
    } >= {
        ("乾元觀", RelationType.LOCATED_IN, "虞山"),
        ("張裕", RelationType.LIVED_IN, "乾元觀"),
    }


def test_tombs_homes_and_poetry_create_person_centered_edges() -> None:
    result = extract_knowledge(
        "右七言偃墓，在虞山上。右十范文正公義宅，在普濟橋旁。"
        "右四上真觀，在洞庭山上。唐僧皎然嘗陪湖州鄭使君登此，却望湖水賦詩。"
    )

    by_name = {item.name: item for item in result.entities}
    assert by_name["言偃"].entity_type is EntityType.PERSON
    assert by_name["范文正公"].entity_type is EntityType.PERSON
    assert by_name["皎然"].entity_type is EntityType.PERSON
    assert {
        (item.subject_name, item.relation_type, item.object_name)
        for item in result.relations
    } >= {
        ("言偃", RelationType.DIED_AT, "言偃墓"),
        ("范文正公", RelationType.LIVED_IN, "范文正公義宅"),
        ("皎然", RelationType.VISITED, "上真觀"),
        ("皎然", RelationType.COMPOSED_AT, "上真觀"),
    }


def test_non_historical_hr_text_is_not_promoted_to_history() -> None:
    result = extract_knowledge(
        "大家好，今天介绍苏大HR智能管理系统。Mutty智能助手支持员工端和招聘流程，"
        "可以查看在职员工并给候选人发送Offer。"
    )

    assert result.entities == ()
    assert result.relations == ()
    assert result.events == ()


def test_classical_compound_names_and_context_do_not_create_cross_section_edges() -> None:
    result = extract_knowledge(
        "袁山松城，在滬瀆江側。袁山松城東三十里，夾江又有二城相對，闔閭所築以控越處。"
        "封域蘇州，在《禹貢》為揚州之域。"
    )

    relation_keys = {
        (item.subject_name, item.relation_type, item.object_name)
        for item in result.relations
    }
    assert ("袁山松城", RelationType.LOCATED_IN, "滬瀆江") in relation_keys
    assert ("松城", RelationType.LOCATED_IN, "滬瀆") not in relation_keys
    assert ("袁山松城", RelationType.BUILT_BY, "松城") not in relation_keys
    assert not any(
        item.relation_type is RelationType.BUILT_BY
        and item.object_name == "袁山松城"
        for item in result.relations
    )
    assert not any(item.subject_name == "封域蘇州" for item in result.relations)
    assert not any(item.object_name == "為揚州" for item in result.relations)


def test_building_relations_are_bounded_to_the_same_classical_sentence() -> None:
    result = extract_knowledge(
        "花山，在吳縣西三十里。山東二里有胥葬亭，吳王闔閭置。"
        "亭東二里有館娃宮，吳人呼西施作娃，夫差置。"
    )

    relation_keys = {
        (item.subject_name, item.relation_type, item.object_name)
        for item in result.relations
    }
    assert ("胥葬亭", RelationType.BUILT_BY, "闔閭") in relation_keys
    assert ("館娃宮", RelationType.BUILT_BY, "夫差") in relation_keys
    assert ("花山", RelationType.BUILT_BY, "闔閭") not in relation_keys
    assert ("花山", RelationType.BUILT_BY, "夫差") not in relation_keys


def test_classical_name_cleaning_rejects_prose_and_official_titles() -> None:
    result = extract_knowledge(
        "闔閭造以游姑胥之臺而望太湖也。伍子胥曰：吾死，必抉吾目置之吳東門。"
        "周先生住山碑，在洞庭山。孫老橋，在運河上。天聖初，郡守禮部郎中直史館孫公冕所建也。"
        "貞觀七年，分吳縣界。"
    )

    names = {item.name for item in result.entities}
    assert "以游姑胥之臺" not in names
    assert "姑胥之臺" in names
    assert "之吳東門" not in names
    assert "周先生住山" not in names
    assert "周先生住山碑" in names
    assert "郡守禮部郎中直史館" not in names
    assert "貞觀" not in names

    relation_keys = {
        (item.subject_name, item.relation_type, item.object_name)
        for item in result.relations
    }
    assert ("孫老橋", RelationType.BUILT_BY, "孫公冕") in relation_keys
    assert ("郡守禮部郎中直史館", RelationType.BUILT_BY, "孫公冕") not in relation_keys


def test_classical_name_cleaning_removes_heading_numbers_without_right_marker() -> None:
    result = extract_knowledge("十一望亭，在虎丘。十三秀峰寺，在天平山。")

    names = {item.name for item in result.entities}
    assert "望亭" in names
    assert "秀峰寺" in names
    assert "十一望亭" not in names
    assert "十三秀峰寺" not in names


def test_person_verb_phrase_is_not_promoted_to_a_building_entity() -> None:
    result = extract_knowledge("自梁武帝建寺，經唐武宗殘毀，至是乃移額於此。")

    assert "梁武帝建寺" not in {entity.name for entity in result.entities}
    assert not any(relation.subject_name == "梁武帝建寺" for relation in result.relations)


def test_classical_group_activity_creates_visit_and_poetry_edges_for_each_person() -> None:
    result = extract_knowledge("樂天、夢得遊報恩寺，作詩。")

    relation_keys = {
        (item.subject_name, item.relation_type, item.object_name)
        for item in result.relations
    }
    assert relation_keys >= {
        ("白樂天", RelationType.VISITED, "報恩寺"),
        ("劉夢得", RelationType.VISITED, "報恩寺"),
        ("白樂天", RelationType.COMPOSED_AT, "報恩寺"),
        ("劉夢得", RelationType.COMPOSED_AT, "報恩寺"),
    }
    assert "樂天" not in {item.name for item in result.entities}
    assert "夢得" not in {item.name for item in result.entities}


def test_poetry_mentions_are_linked_to_the_named_place() -> None:
    result = extract_knowledge("白樂天詩嘗及烏鵲橋。")

    assert (
        "白樂天",
        RelationType.MENTIONED_IN_POETRY,
        "烏鵲橋",
    ) in {
        (item.subject_name, item.relation_type, item.object_name)
        for item in result.relations
    } 


def test_contextual_poetry_mention_resolves_this_bridge_to_section_subject() -> None:
    result = extract_knowledge(
        "右一烏鵲橋，在郡前。舊傳有古館八，曰全吳、通波、龍門、臨頓、升羽、烏鵲、江風、夷亭。"
        "此橋因館得名，白樂天詩嘗及之。"
    )

    assert (
        "白樂天",
        RelationType.MENTIONED_IN_POETRY,
        "烏鵲橋",
    ) in {
        (item.subject_name, item.relation_type, item.object_name)
        for item in result.relations
    }
    assert "此橋" not in {item.name for item in result.entities}


def test_classical_daytime_visit_is_extracted() -> None:
    result = extract_knowledge("闔閭晝游蘇臺。")

    assert (
        "闔閭",
        RelationType.VISITED,
        "蘇臺",
    ) in {
        (item.subject_name, item.relation_type, item.object_name)
        for item in result.relations
    }


def test_hosting_a_banquet_is_not_mistaken_for_composing_poetry() -> None:
    result = extract_knowledge("白樂天於西樓命宴。")

    relation_keys = {
        (item.subject_name, item.relation_type, item.object_name)
        for item in result.relations
    }
    assert ("白樂天", RelationType.VISITED, "西樓") in relation_keys
    assert ("白樂天", RelationType.COMPOSED_AT, "西樓") not in relation_keys
