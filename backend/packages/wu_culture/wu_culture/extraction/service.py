from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field

from wu_culture.models import EntityType
from wu_culture.relations import RelationType

_HAN = r"[\u3400-\u4dbf\u4e00-\u9fff]"
_NAME = rf"{_HAN}{{2,12}}?"
_TERMINATOR = r"(?=[，。；、]|$)"
_CLASSICAL_OBJECT_SUFFIX = (
    r"縣|县|府|州|郡|邑|鎮|镇|村|山|峰|嶺|岭|湖|江|河|溪|港|浜|瀆|渎|涇|泾|洲|浦|池|塘|澤|泽|城|寺|院|庵|菴|宮|宫|觀|观|廟|庙|橋|桥|亭|宅|墓|墳|坟|冢|堂|臺|台|門|门|坊|洞|祠|壇|坛|閣|阁|樓|楼|館|馆|碑|園|园|邱|丘|塢|坞|墅|疁|潭"
)
_CLASSICAL_BUILDING_SUFFIX = (
    "寺", "院", "庵", "菴", "宮", "宫", "觀", "观", "廟", "庙", "橋", "桥",
    "亭", "宅", "堂", "臺", "台", "門", "门", "祠", "壇", "坛", "閣", "阁",
    "樓", "楼", "館", "馆", "園", "园", "塢", "坞",
)
_CLASSICAL_TITLE_PREFIXES = (
    "資政殿學士",
    "資政殿学士",
    "太子少保",
    "郡守",
    "禮部郎中",
    "礼部郎中",
    "直史館",
    "直史馆",
)
_CLASSICAL_TITLE_MARKERS = (
    "郡守",
    "禮部郎中",
    "礼部郎中",
    "直史館",
    "直史馆",
    "資政殿學士",
    "資政殿学士",
    "太子少保",
)
_CLASSICAL_ERA_NAMES = {
    "貞觀",
    "开元",
    "開元",
    "天寶",
    "天宝",
    "元和",
    "長慶",
    "长庆",
}
_CLASSICAL_OBJECT = rf"{_HAN}{{1,12}}?(?:{_CLASSICAL_OBJECT_SUFFIX})"
_CLASSICAL_LOCATION_OBJECT = rf"{_HAN}{{0,12}}?(?:{_CLASSICAL_OBJECT_SUFFIX})"
_CLASSICAL_SECTION_NUMBER = r"(?:[一二三四五六七八九]|十[一二三四五六七八九]?|[二三四五六七八九]十[一二三四五六七八九]?|\d{1,2})"
_CLASSICAL_PERSON_NAMES = (
    "闔閭", "闔廬", "夫差", "西施", "范蠡", "勾踐", "子胥", "伍子胥", "壽夢", "寿梦",
    "泰伯", "太伯", "仲雍", "周章", "言偃", "子游", "吳王僚", "僚", "慶忌", "秦始皇", "朱買臣", "朱买臣", "嚴助", "严助",
    "白樂天", "白居易", "劉禹錫", "刘禹锡", "劉夢得", "皎然", "皮日休", "陸魯望", "陸龜蒙",
    "陸玩", "陸僧瓉", "戴顒", "戴逵", "吳夫人", "孫權", "孫堅", "孫策", "陸遜", "陸機", "陸瑁", "周瑜",
    "丁法海", "王廷堅", "夏日長", "錢子高", "皋伯通", "梁鴻", "孟光", "顧訓", "顧野王", "顧綜",
    "孫公冕", "孫冕", "王元之", "呂濟叔", "陸襄", "顧彥先", "張融", "張岱", "薛曇", "何曾", "梁武帝",
    "武帝", "則天皇后", "袁山松", "張翰", "范文正公", "范仲淹", "韋應物", "支遁", "陸杲", "韓鴻",
    "劉根", "周先生隱遙", "張裕", "昭明太子", "簡文帝", "鄭使君", "方士楚芝蘭", "楚芝蘭", "太宗",
    "唐武宗", "宣宗", "錢氏", "韓公子文", "麋豹", "顧況", "王獻之", "顧辟疆", "王珣", "王珉",
    "蘇子美", "孫承祐", "程正議", "晏公", "周思輯", "申公巫臣", "史惟則", "李道昌", "李衛公",
    "張長史", "元璙", "范蠡", "勾践", "孔子", "蘇峻", "華歆", "何皇后", "公孫捷", "田開疆", "古冶子",
)
_CLASSICAL_PERSON = "(?:" + "|".join(sorted(_CLASSICAL_PERSON_NAMES, key=len, reverse=True)) + ")"
_CLASSICAL_PERSON_REFERENCE_ALIASES = {
    "樂天": "白樂天",
    "乐天": "白樂天",
    "夢得": "劉夢得",
    "梦得": "劉夢得",
    "白公": "白樂天",
    "魯望": "陸魯望",
    "鲁望": "陸魯望",
}
_CLASSICAL_PERSON_REFERENCE_NAMES = tuple(
    dict.fromkeys((*_CLASSICAL_PERSON_NAMES, *_CLASSICAL_PERSON_REFERENCE_ALIASES))
)
_PLACEHOLDER_PERSON_NAMES = frozenset({"张三", "李四", "王五", "赵六"})
_CLASSICAL_PERSON_REFERENCE = "(?:" + "|".join(
    sorted(_CLASSICAL_PERSON_REFERENCE_NAMES, key=len, reverse=True)
) + ")"
_CLASSICAL_SHORT_POET_PAIR = r"(?:皮|陸|陆)"
_CLASSICAL_LOCATION_PATTERN = re.compile(
    r"(?P<subject>[^，,。；]{1,40})[，,](?:在|位於|位于)(?P<object>[^，,。；]{1,80})"
)
_CLASSICAL_BUILDING_VERB_PATTERN = re.compile(
    rf"(?P<person>{_CLASSICAL_PERSON})"
    rf"(?P<verb>舍宅(?:所)?(?:置|爲|為|为)|所(?:建|置|造|築|筑|立)|"
    rf"(?:營建|营建|創建|创建|建造|造|置|築|筑|建|立))"
)
_CLASSICAL_PERSON_BUILDING_PATTERN = re.compile(
    rf"(?P<person>{_CLASSICAL_PERSON})[^。；]{{0,18}}?"
    rf"(?P<verb>舍宅(?:所)?(?:置|爲|為|为)|所(?:建|置|造|築|筑|立)|"
    rf"(?:營建|营建|創建|创建|建造|造|置|築|筑|建|立|作))"
    rf"(?P<building>{_CLASSICAL_OBJECT})"
)
_CLASSICAL_DIRECT_RELATION_PATTERNS = (
    (
        re.compile(rf"(?P<subject>{_CLASSICAL_PERSON})(?:卒|薨|殂)[，,]?(?:葬|葬於|葬于)(?P<object>{_CLASSICAL_OBJECT})"),
        RelationType.DIED_AT,
    ),
    (
        re.compile(rf"(?P<subject>{_CLASSICAL_PERSON})(?:葬|葬於|葬于)(?P<object>{_CLASSICAL_OBJECT})"),
        RelationType.DIED_AT,
    ),
    (
        re.compile(rf"(?P<subject>{_CLASSICAL_PERSON_REFERENCE})(?:嘗|曾|晝|昼|夜|常|遂|乃)?(?:游|遊|登|過|过|至|到)(?:於|于)?(?P<object>{_CLASSICAL_OBJECT})"),
        RelationType.VISITED,
    ),
    (
        re.compile(rf"(?P<subject>{_CLASSICAL_PERSON_REFERENCE})(?:於|于|在)(?P<object>{_CLASSICAL_OBJECT})(?:作詩|作诗|賦詩|赋诗|題詩|题诗)"),
        RelationType.COMPOSED_AT,
    ),
    (
        re.compile(rf"(?P<subject>{_CLASSICAL_PERSON_REFERENCE})(?:於|于|在)(?P<object>{_CLASSICAL_OBJECT})命宴"),
        RelationType.VISITED,
    ),
    (
        re.compile(rf"(?P<subject>{_CLASSICAL_PERSON_REFERENCE})詩(?:嘗|曾)?及(?P<object>{_CLASSICAL_OBJECT})"),
        RelationType.MENTIONED_IN_POETRY,
    ),
)
_CLASSICAL_ACTIVITY_GROUP_PATTERN = re.compile(
    rf"(?P<people>{_CLASSICAL_PERSON_REFERENCE}(?:\s*[、,，及與与和]\s*(?:{_CLASSICAL_PERSON_REFERENCE}|{_CLASSICAL_SHORT_POET_PAIR})){{0,3}})"
    rf"(?:嘗|曾|晝|昼|夜|常|遂|乃)?"
    rf"(?P<verb>游|遊|登|過|过|至|到)(?:於|于)?"
    rf"(?P<object>{_CLASSICAL_OBJECT})"
    rf"(?P<poetry>[，,、]?\s*(?:作詩|作诗|賦詩|赋诗|題詩|题诗))?"
)
_CLASSICAL_POETRY_MENTION_PATTERN = re.compile(
    rf"(?:此橋|此桥|此亭|此臺|此台|此寺|此院|此觀|此观|此宮|此宫|此樓|此楼)"
    rf"[^。；]{{0,80}}(?P<person>{_CLASSICAL_PERSON_REFERENCE})詩(?:嘗)?及之"
)
_RELATION_PATTERNS = (
    (re.compile(rf"(?P<subject>{_NAME})(?:位于|坐落于)(?P<object>{_NAME}){_TERMINATOR}"), RelationType.LOCATED_IN),
    (re.compile(rf"(?P<subject>{_NAME})由(?P<object>{_NAME})(?:修建|营建|建造|创建){_TERMINATOR}"), RelationType.BUILT_BY),
    (re.compile(rf"(?P<subject>{_NAME})跨越(?P<object>{_NAME}){_TERMINATOR}"), RelationType.CROSSES),
    (re.compile(rf"(?P<subject>{_NAME})与(?P<object>{_NAME})(?:是|为)(?:亲兄弟|亲姐妹|兄弟姐妹|姐弟|兄妹|兄弟|姐妹){_TERMINATOR}"), RelationType.SIBLING_OF),
    (re.compile(rf"(?P<subject>{_NAME})与(?P<object>{_NAME})(?:是|为)(?:夫妻|配偶){_TERMINATOR}"), RelationType.SPOUSE_OF),
    (re.compile(rf"(?P<subject>{_NAME})是(?P<object>{_NAME})的(?:父亲|母亲|父母){_TERMINATOR}"), RelationType.PARENT_OF),
    (re.compile(rf"(?P<subject>{_NAME})(?:居住于|居住在)(?P<object>{_NAME}){_TERMINATOR}"), RelationType.LIVED_IN),
    (re.compile(rf"(?P<subject>{_NAME})(?:游览|到访|访问)(?P<object>{_NAME}){_TERMINATOR}"), RelationType.VISITED),
    (re.compile(rf"(?P<subject>{_NAME})(?:游于|遊於|游历|遊歷|登临|登臨)(?P<object>{_NAME}){_TERMINATOR}"), RelationType.VISITED),
    (re.compile(rf"(?P<subject>{_NAME})出生于(?P<object>{_NAME}){_TERMINATOR}"), RelationType.BORN_IN),
    (re.compile(rf"(?P<subject>{_NAME})(?:任职于|任职在)(?P<object>{_NAME}){_TERMINATOR}"), RelationType.WORKED_AT),
    (re.compile(rf"(?P<subject>{_NAME})(?:求学于|就读于)(?P<object>{_NAME}){_TERMINATOR}"), RelationType.STUDIED_AT),
    (re.compile(rf"(?P<subject>{_NAME})(?:卒于|卒於|死于|死於|殂于|殂於)(?P<object>{_NAME}){_TERMINATOR}"), RelationType.DIED_AT),
    (re.compile(rf"(?P<subject>{_NAME})(?:在|于|於)(?P<object>{_NAME})(?:赋诗|賦詩|作诗|作詩|题诗|題詩|题咏|題詠){_TERMINATOR}"), RelationType.COMPOSED_AT),
)
_PERSON_RELATIONS = {
    RelationType.SIBLING_OF,
    RelationType.SPOUSE_OF,
    RelationType.PARENT_OF,
}
_PERSON_TO_PLACE_RELATIONS = {
    RelationType.LIVED_IN,
    RelationType.VISITED,
    RelationType.BORN_IN,
    RelationType.WORKED_AT,
    RelationType.STUDIED_AT,
    RelationType.DIED_AT,
    RelationType.COMPOSED_AT,
    RelationType.MENTIONED_IN_POETRY,
}
_ALIAS_PATTERN = re.compile(rf"(?P<canonical>{_NAME})(?:又称|旧称|俗称)(?P<alias>{_NAME}){_TERMINATOR}")
_YEAR_EVENT_PATTERN = re.compile(r"(?P<year>\d{3,4})年(?P<title>[^。；]{2,80})")
_TEMPORAL_NAME = re.compile(r"(?:\d{2,4}|年|歲|岁|月|日|(?:初|中|末)$)")
_CLASSICAL_OBJECT_RE = re.compile(rf"(?P<name>{_HAN}{{1,12}}(?:{_CLASSICAL_OBJECT_SUFFIX}))")
_CLASSICAL_DISTANCE_RE = re.compile(r"[東西南北上下左右內外中間]{0,4}\s*[一二三四五六七八九十百千万萬\d]+里")
_CLASSICAL_NAME_ALIASES = {
    "闔廬": "闔閭",
    "闔卢": "闔閭",
    "太伯": "泰伯",
    "朱买臣": "朱買臣",
    "严助": "嚴助",
    "寿梦": "壽夢",
    "刘禹锡": "劉禹錫",
    "勾践": "勾踐",
    "子游": "言偃",
}
_NON_HISTORICAL_MARKERS = (
    "HR智能管理系统",
    "HR智能管理",
    "AI智能体",
    "Mutty",
    "员工端",
    "在职员工",
    "招聘流程",
    "候选人",
)


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class ExtractedEntity(_M):
    name: str = Field(min_length=1, max_length=255)
    entity_type: EntityType
    reason: str


class ExtractedRelation(_M):
    subject_name: str
    relation_type: RelationType
    object_name: str
    source_text: str


class ExtractedEvent(_M):
    title: str
    start_time: str | None = None
    time_certainty: str = "unknown"
    place_name: str | None = None
    source_text: str


class ExtractedAlias(_M):
    canonical_name: str
    alias: str
    source_text: str


class KnowledgeExtractionResult(_M):
    text: str
    entities: tuple[ExtractedEntity, ...]
    relations: tuple[ExtractedRelation, ...]
    events: tuple[ExtractedEvent, ...]
    aliases: tuple[ExtractedAlias, ...]


def _entity_type(name: str, *, person_hint: bool = False) -> EntityType:
    if person_hint:
        return EntityType.PERSON
    suffixes = {
        EntityType.BRIDGE: ("桥", "橋"),
        EntityType.GARDEN: ("园", "園", "花园", "花園"),
        EntityType.WATERWAY: ("河", "浜", "港", "溪", "湖", "江", "瀆", "渎", "泾", "涇", "浦", "池", "塘", "澤", "泽", "潭"),
        EntityType.RELIC: ("墓", "墳", "坟", "冢", "墩", "碑"),
        EntityType.BUILDING: (
            "寺", "庙", "廟", "宅", "馆", "館", "樓", "楼", "亭", "塔", "觀", "观", "宮", "宫",
            "院", "庵", "菴", "祠", "堂", "閣", "阁", "壇", "坛",
        ),
        EntityType.PLACE: ("府", "州", "郡", "縣", "县", "镇", "鎮", "村", "街", "巷", "山", "峰", "嶺", "岭", "邱", "丘", "坊", "城", "門", "门", "洞", "塢", "坞"),
        EntityType.WORK: ("志", "录", "谱"),
    }
    for entity_type, endings in suffixes.items():
        if name.endswith(endings):
            return entity_type
    return EntityType.PLACE


def _clean_classical_name(name: str) -> str:
    """Remove catalogue headings and locative tails from a classical name."""
    clean = name.strip(" ，。；、:：()（）[]［］「」『』〈〉<>\"'")
    # Catalogue section numbers in this corpus are at most two digits. Do not
    # consume 百/千/... here: those characters can begin a real name such as
    # 百口橋 after an OCR-flattened heading like "右四百口橋".
    clean = re.sub(rf"^(?:右|左|前|後|后)\s*{_CLASSICAL_SECTION_NUMBER}", "", clean)
    # Some transcriptions omit the directional catalogue marker and leave the
    # section number attached to the named object, e.g. "十一望亭".
    clean = re.sub(
        rf"^{_CLASSICAL_SECTION_NUMBER}(?={_HAN}{{1,12}}(?:{_CLASSICAL_OBJECT_SUFFIX}))",
        "",
        clean,
    )
    clean = re.sub(r"^[^，,。；]{0,12}凡[一二三四五六七八九十百千万萬\d]+節", "", clean)
    clean = re.sub(r"^(?:有|又有)(?=[\u3400-\u4dbf\u4e00-\u9fff])", "", clean)
    clean = re.sub(r"^.*(?:有|又有)(?=[\u3400-\u4dbf\u4e00-\u9fff])", "", clean)
    clean = re.sub(r"^(?:在|於|于|至|到|自|從|从)(?=[\u3400-\u4dbf\u4e00-\u9fff])", "", clean)
    clean = re.sub(r"^(?:以|因|遂|乃|又)?(?:游|遊)(?=[\u3400-\u4dbf\u4e00-\u9fff])", "", clean)
    clean = clean.lstrip("之")
    for _ in range(4):
        previous = clean
        clean = re.sub(r"^(?:故|先|前|今|舊|旧)", "", clean)
        clean = re.sub(
            rf"^(?:{'|'.join(map(re.escape, _CLASSICAL_TITLE_PREFIXES))})",
            "",
            clean,
        )
        clean = re.sub(r"^(?:在|於|于|至|到|自|從|从)(?=[\u3400-\u4dbf\u4e00-\u9fff])", "", clean)
        if clean == previous:
            break
    clean = re.sub(r"(?:之)?(?:上|下|旁|前|後|外|內|内|中|側|侧)$", "", clean)
    return _CLASSICAL_NAME_ALIASES.get(clean, clean)


def _canonical_person_name(name: str) -> str:
    clean = _clean_classical_name(name)
    return _CLASSICAL_PERSON_REFERENCE_ALIASES.get(clean, clean)


def _classical_location_targets(value: str) -> tuple[str, ...]:
    """Return named places from a locative phrase, excluding distance prose."""
    if re.search(r"[《〈「『]", value) or re.match(r"\s*(?:為|爲|为|是|即|乃|屬|属|謂|谓)", value):
        return ()
    separated = _CLASSICAL_DISTANCE_RE.sub("、", value)
    candidates: list[str] = []
    for match in _CLASSICAL_OBJECT_RE.finditer(separated):
        name = _clean_classical_name(match.group("name"))
        name = re.sub(r"^(?:縣|县|郡|州)[東西南北上下左右內外中間]{1,4}", "", name)
        name = re.sub(r"^[東西南北上下左右內外中間]{1,4}(?=[\u3400-\u4dbf\u4e00-\u9fff]{2,})", "", name)
        name = name.lstrip("之")
        if _is_usable_entity_name(name) and name not in candidates:
            candidates.append(name)
    return tuple(candidates)


def _classical_heading_name(value: str) -> str:
    """Use the final named object in a catalogue heading as its subject."""
    candidates = [
        _clean_classical_name(match.group("name"))
        for match in _CLASSICAL_OBJECT_RE.finditer(value)
    ]
    return candidates[-1] if candidates else _clean_classical_name(value)


def _is_classical_object_name(name: str) -> bool:
    return bool(re.search(rf"(?:{_CLASSICAL_OBJECT_SUFFIX})$", name))


def _is_classical_building_name(name: str) -> bool:
    if not re.search(rf"(?:{'|'.join(_CLASSICAL_BUILDING_SUFFIX)})$", name):
        return False
    building_verbs = ("建", "造", "置", "築", "筑", "立", "營建", "营建", "創建", "创建", "建造", "舍宅", "所")
    return not any(
        name.startswith(person)
        and name[len(person) :].startswith(building_verbs)
        for person in _CLASSICAL_PERSON_NAMES
    )


def _next_classical_heading(text: str, start: int) -> int:
    match = re.search(
        r"[。；][「」『』〈〉<>]*[右左]\s*[一二三四五六七八九十百千万萬\d]+",
        text[start:],
    )
    return start + match.start() if match else len(text)


def _embedded_person(name: str) -> str | None:
    clean = _clean_classical_name(name)
    for person in sorted(_CLASSICAL_PERSON_NAMES, key=len, reverse=True):
        canonical = _CLASSICAL_NAME_ALIASES.get(person, person)
        if clean == canonical or canonical in clean or person in clean:
            return canonical
    return None


def _classical_location_subject(value: str) -> str:
    """Return a heading candidate, rejecting prose that only ends in a place suffix."""
    clean = _classical_heading_name(value)
    if re.match(r"^(?:封域|疆域|地名|水名|古今|今名|旧名|舊名)", clean):
        return ""
    return clean


def _classical_sentences(text: str) -> tuple[str, ...]:
    return tuple(part for part in re.split(r"(?<=[。；])", text) if part)


def _is_non_historical_noise(text: str) -> bool:
    upper = text.upper()
    marker_count = sum(marker.upper() in upper for marker in _NON_HISTORICAL_MARKERS)
    return marker_count >= 2 or ("HR" in upper and "AI" in upper and "员工" in text)


def is_non_historical_text(text: str) -> bool:
    """Identify known product/demo text that must not enter the history corpus."""
    return _is_non_historical_noise(text)


def _is_usable_entity_name(name: str) -> bool:
    """Keep dates and empty OCR fragments out of the entity graph."""
    stripped = name.strip()
    if len(stripped) < 2 or _TEMPORAL_NAME.search(stripped):
        return False
    if stripped in _CLASSICAL_ERA_NAMES or any(marker in stripped for marker in _CLASSICAL_TITLE_MARKERS):
        return False
    # Demonstratives in Classical Chinese refer to the current section's
    # place; they are not standalone historical place names.
    return stripped not in {"此山", "此地", "此寺", "此處", "此处", "其地", "其寺", "是山", "之山"}


def extract_knowledge(text: str) -> KnowledgeExtractionResult:
    normalized = re.sub(r"[ \t\f\v]+", " ", text.strip())
    normalized = re.sub(r"\r\n?", "\n", normalized)
    if not normalized:
        raise ValueError("text cannot be empty")
    if is_non_historical_text(normalized):
        return KnowledgeExtractionResult(
            text=normalized,
            entities=(),
            relations=(),
            events=(),
            aliases=(),
        )
    entities: dict[str, ExtractedEntity] = {}
    relations: list[ExtractedRelation] = []
    seen_relations: set[tuple[str, RelationType, str]] = set()
    aliases: list[ExtractedAlias] = []

    def add_entity(name: str, reason: str, *, person_hint: bool = False) -> None:
        clean = _clean_classical_name(name)
        if person_hint and clean in _PLACEHOLDER_PERSON_NAMES:
            return
        if _is_usable_entity_name(clean) and clean not in entities:
            entities[clean] = ExtractedEntity(
                name=clean,
                entity_type=_entity_type(clean, person_hint=person_hint),
                reason=reason,
            )

    def add_relation(subject: str, relation_type: RelationType, object_: str, source_text: str) -> None:
        for prefix in ("一名", "又名", "今名", "舊名", "旧名", "俗稱", "俗称"):
            if subject.startswith(prefix) and len(subject) > len(prefix):
                subject = subject[len(prefix):]
                break
        person_subject = relation_type in _PERSON_RELATIONS or relation_type in _PERSON_TO_PLACE_RELATIONS
        person_object = relation_type in _PERSON_RELATIONS or relation_type is RelationType.BUILT_BY
        subject = _canonical_person_name(subject) if person_subject else _clean_classical_name(subject)
        object_ = _canonical_person_name(object_) if person_object else _clean_classical_name(object_)
        if relation_type is RelationType.LOCATED_IN and len(object_) < 2:
            return
        if not _is_usable_entity_name(subject) or not _is_usable_entity_name(object_):
            return
        if (person_subject and subject in _PLACEHOLDER_PERSON_NAMES) or (
            person_object and object_ in _PLACEHOLDER_PERSON_NAMES
        ):
            return
        add_entity(subject, f"关系主语：{relation_type.value}", person_hint=person_subject)
        add_entity(object_, f"关系宾语：{relation_type.value}", person_hint=person_object)
        relation_key = (subject, relation_type, object_)
        if relation_key in seen_relations:
            return
        seen_relations.add(relation_key)
        relations.append(
            ExtractedRelation(
                subject_name=subject,
                relation_type=relation_type,
                object_name=object_,
                source_text=source_text,
            )
        )

    # Keep named historical figures even when a chunk mentions them without a
    # relation construction. Avoid creating a short duplicate such as 武帝
    # when the source explicitly names 梁武帝.
    for person in sorted(_CLASSICAL_PERSON_NAMES, key=len, reverse=True):
        canonical = _CLASSICAL_NAME_ALIASES.get(person, person)
        if person not in normalized:
            continue
        if any(
            longer != person
            and person in longer
            and longer in normalized
            for longer in _CLASSICAL_PERSON_NAMES
        ):
            continue
        add_entity(canonical, "文献中出现的人物", person_hint=True)

    for pattern, relation_type in _RELATION_PATTERNS:
        for match in pattern.finditer(normalized):
            subject = match.group("subject")
            object_ = match.group("object")
            if not _is_usable_entity_name(subject) or not _is_usable_entity_name(object_):
                continue
            add_relation(subject, relation_type, object_, match.group(0))

    # The source corpus is a Classical Chinese transcription. These patterns
    # intentionally cover only explicit documentary constructions; they do not
    # turn every occurrence of "在", "至", or "游" into a historical claim.
    location_matches = tuple(_CLASSICAL_LOCATION_PATTERN.finditer(normalized))
    for match in location_matches:
        subject = _classical_location_subject(match.group("subject"))
        if not _is_usable_entity_name(subject) or not _is_classical_object_name(subject):
            continue
        targets = _classical_location_targets(match.group("object"))
        for target in targets:
            add_relation(subject, RelationType.LOCATED_IN, target, match.group(0))

        embedded_person = _embedded_person(subject)
        if embedded_person and subject.endswith(("墓", "墳", "坟", "冢", "墩")):
            add_relation(embedded_person, RelationType.DIED_AT, subject, match.group(0))
        elif embedded_person and subject.endswith(("宅", "園", "园", "第")):
            add_relation(embedded_person, RelationType.LIVED_IN, subject, match.group(0))

        # A section heading gives the local subject for the short passage that
        # follows it. This resolves constructions such as "登此而賦詩" while
        # keeping the scope bounded to avoid linking unrelated sections.
        next_heading_start = _next_classical_heading(normalized, match.end())
        next_location_start = next(
            (next_match.start() for next_match in location_matches if next_match.start() > match.start()),
            len(normalized),
        )
        context = normalized[match.end() : min(match.end() + 240, next_heading_start, next_location_start)]
        person_mentions = sorted(
            (
                context.find(person),
                person,
            )
            for person in _CLASSICAL_PERSON_NAMES
            if person in context
        )
        for _position, person in person_mentions:
            if person not in context:
                continue
            person_position = context.find(person)
            person_window = context[person_position : person_position + 180]
            canonical_person = _CLASSICAL_NAME_ALIASES.get(person, person)
            if re.search(r"(?:栖遁|棲遁|隱居|隐居|卜居|居此|居於|居于|終焉)", person_window):
                add_relation(canonical_person, RelationType.LIVED_IN, subject, person_window)
            if re.search(r"(?:來此|来此|登此|遊此|游此|過此|过此|至此|到此)", person_window):
                add_relation(canonical_person, RelationType.VISITED, subject, person_window)
            if re.search(r"(?:詩|诗)(?:嘗|曾)?及之", person_window):
                add_relation(
                    canonical_person,
                    RelationType.MENTIONED_IN_POETRY,
                    subject,
                    person_window,
                )
        if person_mentions:
            composition_position, composition_person = person_mentions[0]
            composition_window = context[composition_position : composition_position + 180]
            if re.search(r"(?:賦詩|赋诗|作詩|作诗|題詩|题诗|題詠|题咏)", composition_window):
                add_relation(
                    _CLASSICAL_NAME_ALIASES.get(composition_person, composition_person),
                    RelationType.COMPOSED_AT,
                    subject,
                    composition_window,
                )

    # Keep building attribution inside one Classical Chinese sentence. A
    # previous implementation scanned a large global window and attached the
    # next section's person to the previous mountain or building.
    classical_sentences = _classical_sentences(normalized)

    def valid_building_matches(value: str) -> tuple[re.Match[str], ...]:
        return tuple(
            candidate
            for candidate in _CLASSICAL_OBJECT_RE.finditer(value)
            if (
                _is_usable_entity_name(_clean_classical_name(candidate.group("name")))
                and _is_classical_building_name(_clean_classical_name(candidate.group("name")))
            )
        )

    for sentence_index, sentence in enumerate(classical_sentences):
        for match in _CLASSICAL_BUILDING_VERB_PATTERN.finditer(sentence):
            prefix = sentence[: match.start()].rsplit("，", 1)[-1]
            building_matches = valid_building_matches(prefix)
            if not building_matches:
                # A catalogue heading may put the building in the first
                # clause, followed by a date and an attribution clause.
                verb = match.group("verb")
                if verb in {"置", "所置", "建", "所建", "造", "所造", "建造", "營建", "营建"}:
                    building_matches = valid_building_matches(sentence.split("，", 1)[0])
            if not building_matches and sentence_index:
                verb = match.group("verb")
                if verb in {"置", "所置", "建", "所建", "造", "所造", "建造", "營建", "营建"}:
                    building_matches = valid_building_matches(classical_sentences[sentence_index - 1])
            if not building_matches:
                continue
            building = _clean_classical_name(building_matches[-1].group("name"))
            add_relation(building, RelationType.BUILT_BY, match.group("person"), sentence)
        for match in _CLASSICAL_PERSON_BUILDING_PATTERN.finditer(sentence):
            if match.group("building").startswith("之"):
                continue
            building = _clean_classical_name(match.group("building"))
            if _is_usable_entity_name(building) and _is_classical_building_name(building):
                add_relation(building, RelationType.BUILT_BY, match.group("person"), sentence)

    for pattern, relation_type in _CLASSICAL_DIRECT_RELATION_PATTERNS:
        for match in pattern.finditer(normalized):
            add_relation(match.group("subject"), relation_type, match.group("object"), match.group(0))

    for match in _CLASSICAL_ACTIVITY_GROUP_PATTERN.finditer(normalized):
        people = re.split(r"\s*[、,，及與与和]\s*", match.group("people"))
        for person in people:
            canonical_person = _canonical_person_name(person)
            add_relation(
                canonical_person,
                RelationType.VISITED,
                match.group("object"),
                match.group(0),
            )
            if match.group("poetry"):
                add_relation(
                    canonical_person,
                    RelationType.COMPOSED_AT,
                    match.group("object"),
                    match.group(0),
                )

    # "此山" and "之" are safe to resolve only inside the short descriptive
    # passage introduced by a named mountain or structure.
    contextual_patterns = (
        (
            re.compile(rf"(?P<object>{_CLASSICAL_OBJECT})[，,][^。；]{{0,100}}[。；][^。；]{{0,240}}?(?P<subject>{_CLASSICAL_PERSON})[^。；]{{0,80}}?(?:隱|隱居|隐|隐居)\s*此山"),
            RelationType.LIVED_IN,
        ),
        (
            re.compile(rf"(?P<object>{_CLASSICAL_OBJECT})[，,][^。；]{{0,100}}[。；][^。；]{{0,240}}?(?P<subject>{_CLASSICAL_PERSON})(?:葬|所葬)\s*此山"),
            RelationType.DIED_AT,
        ),
        (
            re.compile(rf"(?P<object>{_CLASSICAL_OBJECT})[，,][^。；]{{0,100}}[。；][^。；]{{0,240}}?(?P<subject>{_CLASSICAL_PERSON})詩(?:嘗)?及之"),
            RelationType.MENTIONED_IN_POETRY,
        ),
    )
    for pattern, relation_type in contextual_patterns:
        for match in pattern.finditer(normalized):
            add_relation(match.group("subject"), relation_type, match.group("object"), match.group(0))

    for match in _ALIAS_PATTERN.finditer(normalized):
        canonical = match.group("canonical")
        alias = match.group("alias")
        add_entity(canonical, "别名规范名")
        aliases.append(ExtractedAlias(canonical_name=canonical, alias=alias, source_text=match.group(0)))

    events: list[ExtractedEvent] = []
    for match in _YEAR_EVENT_PATTERN.finditer(normalized):
        title = match.group("title").strip(" ，")
        place = next((name for name, entity in entities.items() if entity.entity_type in {EntityType.PLACE, EntityType.BRIDGE, EntityType.GARDEN, EntityType.BUILDING} and name in title), None)
        events.append(
            ExtractedEvent(
                title=title,
                start_time=match.group("year"),
                time_certainty="exact",
                place_name=place,
                source_text=match.group(0),
            )
        )

    return KnowledgeExtractionResult(
        text=normalized,
        entities=tuple(entities.values()),
        relations=tuple(relations),
        events=tuple(events),
        aliases=tuple(aliases),
    )
