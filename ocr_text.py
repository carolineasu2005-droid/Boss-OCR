"""Pure text processing for screen-based OCR keyword detection."""

from dataclasses import dataclass
import re
import unicodedata
from typing import Iterable, List, Optional, Sequence, Tuple, Union


@dataclass(frozen=True)
class OCRItem:
    """One OCR text box in screen coordinates."""

    text: str
    confidence: float = 1.0
    box: Optional[Sequence[Sequence[float]]] = None

    @property
    def anchor(self) -> Tuple[float, float]:
        if self.box is None or len(self.box) == 0:
            return (0.0, 0.0)
        xs = [float(point[0]) for point in self.box]
        ys = [float(point[1]) for point in self.box]
        return (min(xs), min(ys))

    @property
    def vertical_bounds(self) -> Optional[Tuple[float, float]]:
        if self.box is None or len(self.box) == 0:
            return None
        ys = [float(point[1]) for point in self.box]
        return (min(ys), max(ys))


@dataclass(frozen=True)
class KeywordTerm:
    """One positive or negated quoted keyword in an AND group."""

    keyword: str
    negated: bool = False


@dataclass(frozen=True)
class KeywordAnyGroup:
    """One atomic condition matching any of its quoted keywords."""

    keywords: Tuple[str, ...]
    negated: bool = False


KeywordAtom = Union[KeywordTerm, KeywordAnyGroup]


@dataclass(frozen=True)
class KeywordRule:
    """One parsed keyword expression represented as OR-ed AND groups."""

    source: str
    or_groups: Tuple[Tuple[KeywordAtom, ...], ...]


class KeywordRuleSyntaxError(ValueError):
    """Raised when a keyword rule string does not match the supported grammar."""


def _rule_error(message: str, position: int) -> KeywordRuleSyntaxError:
    return KeywordRuleSyntaxError(f"{message}（位置 {position + 1}）")


def parse_keyword_rules(value: str) -> List[KeywordRule]:
    """Parse quoted keyword rules with NOT, AND, then OR precedence."""

    text = "" if value is None else str(value)
    length = len(text)
    index = 0

    def skip_whitespace(position):
        while position < length and text[position].isspace():
            position += 1
        return position

    def parse_quoted_keyword(position):
        if position >= length or text[position] != '"':
            raise _rule_error('关键词必须使用英文双引号包裹', position)
        start = position
        position += 1
        closing_quote = text.find('"', position)
        if closing_quote < 0:
            raise _rule_error('关键词缺少结束英文双引号', start)
        keyword = text[position:closing_quote]
        if not keyword.strip():
            raise _rule_error('关键词不能为空', start)
        return keyword, closing_quote + 1

    def starts_token(position, token):
        end = position + len(token)
        return text[position:end].lower() == token and (
            end == length or text[end].isspace()
        )

    def starts_any(position):
        end = position + 3
        return text[position:end].lower() == 'any' and (
            end == length or text[end].isspace() or text[end] == '('
        )

    def parse_any_group(position, negated=False):
        any_start = position
        position = skip_whitespace(position + 3)
        if position >= length or text[position] != '(':
            raise _rule_error('any 后必须跟随括号参数', any_start)

        position = skip_whitespace(position + 1)
        if position < length and text[position] == ')':
            raise _rule_error('any(...) 至少需要一个关键词', position)
        if position >= length:
            raise _rule_error('any(...) 缺少右括号', position)

        keywords = []
        normalized_keywords = set()
        while True:
            if text[position] != '"':
                if starts_any(position):
                    raise _rule_error('any(...) 不支持嵌套', position)
                raise _rule_error(
                    'any(...) 参数必须使用英文双引号包裹',
                    position,
                )

            keyword_start = position
            keyword, position = parse_quoted_keyword(position)
            normalized_keyword = normalize_text(keyword)
            if normalized_keyword in normalized_keywords:
                raise _rule_error(
                    f'any(...) 中存在重复关键词 "{keyword}"',
                    keyword_start,
                )
            normalized_keywords.add(normalized_keyword)
            keywords.append(keyword)

            position = skip_whitespace(position)
            if position >= length:
                raise _rule_error('any(...) 缺少右括号', position)
            if text[position] == ')':
                return KeywordAnyGroup(tuple(keywords), negated), position + 1
            if text[position] == ',':
                comma_position = position
                position = skip_whitespace(position + 1)
                if position >= length or text[position] == ')':
                    raise _rule_error(
                        'any(...) 逗号后缺少英文双引号关键词',
                        comma_position,
                    )
                continue
            if text[position] == '"':
                raise _rule_error(
                    'any(...) 参数之间必须使用英文逗号分隔',
                    position,
                )
            raise _rule_error(
                'any(...) 内只支持英文双引号关键词，不支持组合表达式',
                position,
            )

    def parse_atom(position, negated=False):
        if position < length and text[position] == '"':
            keyword, position = parse_quoted_keyword(position)
            return KeywordTerm(keyword=keyword, negated=negated), position
        if starts_any(position):
            return parse_any_group(position, negated=negated)
        raise _rule_error('关键词必须使用英文双引号包裹或 any(...)', position)

    def parse_term(position):
        if text[position:position + 3].lower() == 'not':
            not_start = position
            after_not = position + 3
            if after_not >= length or not text[after_not].isspace():
                raise _rule_error('not 后必须是带英文双引号的关键词', not_start)
            position = skip_whitespace(after_not)
            if position >= length:
                raise _rule_error('not 后缺少带英文双引号的关键词', position)
            if starts_token(position, 'not'):
                raise _rule_error('not 只能修饰一个关键词或 any(...)', position)
            if text[position] == '(':
                raise _rule_error(
                    'not 后必须是关键词或 any(...)，不支持修饰组合表达式',
                    position,
                )
            return parse_atom(position, negated=True)

        return parse_atom(position)

    def finish_group(group, position):
        if not any(not term.negated for term in group):
            raise _rule_error('每个 OR 分支至少需要一个正向关键词或 any 条件', position)
        return tuple(group)

    def build_rule(groups):
        def atom_source(atom):
            if isinstance(atom, KeywordAnyGroup):
                value = 'any(' + ', '.join(
                    f'"{keyword}"' for keyword in atom.keywords
                ) + ')'
            else:
                value = f'"{atom.keyword}"'
            return f'not {value}' if atom.negated else value

        source = ' or '.join(
            ' and '.join(
                atom_source(atom) for atom in group
            )
            for group in groups
        )
        return KeywordRule(source, tuple(groups))

    index = skip_whitespace(index)
    if index >= length:
        return []

    rules = []
    while index < length:
        if text[index] == ';':
            raise _rule_error('分号之间不能存在空规则', index)

        groups = []
        current_group = []
        term_start = index
        term, index = parse_term(index)
        current_group.append(term)

        while True:
            whitespace_start = index
            index = skip_whitespace(index)
            had_whitespace = index > whitespace_start

            if index >= length:
                groups.append(finish_group(current_group, term_start))
                rules.append(build_rule(groups))
                return rules

            if text[index] == ';':
                groups.append(finish_group(current_group, term_start))
                rules.append(build_rule(groups))
                index = skip_whitespace(index + 1)
                if index >= length:
                    return rules
                if text[index] == ';':
                    raise _rule_error('分号之间不能存在空规则', index)
                break

            if not had_whitespace:
                raise _rule_error('关键词与连接符之间必须有空格', index)

            operator = None
            for candidate in ('and', 'or'):
                if starts_token(index, candidate):
                    operator = candidate
                    index += len(candidate)
                    break
            if operator is None:
                if starts_token(index, 'not'):
                    raise _rule_error('not 前必须使用 and 或 or 连接关键词', index)
                raise _rule_error('仅支持 and、or、not 或分号连接关键词', index)

            index = skip_whitespace(index)
            if index >= length or text[index] == ';':
                raise _rule_error(f'{operator} 后缺少带英文双引号的关键词', index)

            if operator == 'or':
                groups.append(finish_group(current_group, term_start))
                current_group = []
            term_start = index
            term, index = parse_term(index)
            current_group.append(term)

    return rules


def normalize_text(value: str) -> str:
    """Normalize layout noise without introducing fuzzy matching."""

    normalized = unicodedata.normalize("NFKC", value or "").lower()
    return re.sub(r"\s+", "", normalized)


def order_items(items: Iterable[OCRItem]) -> List[OCRItem]:
    """Return OCR boxes in adaptive line order, then left-to-right order."""

    items = list(items)
    positioned = [item for item in items if item.vertical_bounds is not None]
    unpositioned = [item for item in items if item.vertical_bounds is None]
    positioned.sort(key=lambda item: (item.anchor[1], item.anchor[0]))

    lines = []
    for item in positioned:
        top, bottom = item.vertical_bounds
        center = (top + bottom) / 2.0
        height = max(1.0, bottom - top)
        target = None
        for line in lines:
            tolerance = max(8.0, min(height, line["height"]) * 0.5)
            if abs(center - line["center"]) <= tolerance:
                target = line
                break
        if target is None:
            lines.append(
                {"items": [item], "center": center, "height": height}
            )
        else:
            target["items"].append(item)
            count = len(target["items"])
            target["center"] = ((target["center"] * (count - 1)) + center) / count
            target["height"] = ((target["height"] * (count - 1)) + height) / count

    ordered = []
    for line in sorted(lines, key=lambda value: value["center"]):
        ordered.extend(sorted(line["items"], key=lambda item: item.anchor[0]))
    ordered.extend(unpositioned)
    return ordered


def searchable_text(items: Iterable[OCRItem], min_confidence: float = 0.0) -> str:
    """Build normalized searchable text from accepted OCR boxes."""

    accepted = [item for item in items if item.confidence >= min_confidence]
    return normalize_text("\n".join(item.text for item in order_items(accepted)))


def exact_keyword_match(text: str, keywords: Iterable[str]) -> Optional[str]:
    """Return the first normalized exact substring match, otherwise None."""

    normalized_text = normalize_text(text)
    for keyword in keywords:
        cleaned = keyword.strip()
        if cleaned and normalize_text(cleaned) in normalized_text:
            return cleaned
    return None


def keyword_rule_matches(text: str, rule: KeywordRule) -> bool:
    """Return whether one parsed rule matches normalized OCR text."""

    normalized_text = normalize_text(text)
    return any(
        all(
            (
                normalize_text(term.keyword) not in normalized_text
                if term.negated
                else normalize_text(term.keyword) in normalized_text
            )
            for term in group
        )
        for group in rule.or_groups
    )


def matching_keyword_rule(
    text: str,
    rules: Iterable[KeywordRule],
) -> Optional[KeywordRule]:
    """Return the first matching rule, preserving input order."""

    for rule in rules:
        if keyword_rule_matches(text, rule):
            return rule
    return None
