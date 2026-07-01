"""Pure text processing for screen-based OCR keyword detection."""

from dataclasses import dataclass
import re
import unicodedata
from typing import Iterable, List, Optional, Sequence, Tuple


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
class KeywordRule:
    """One parsed keyword expression represented as OR-ed AND groups."""

    source: str
    or_groups: Tuple[Tuple[str, ...], ...]


class KeywordRuleSyntaxError(ValueError):
    """Raised when a keyword rule string does not match the supported grammar."""


def _rule_error(message: str, position: int) -> KeywordRuleSyntaxError:
    return KeywordRuleSyntaxError(f"{message}（位置 {position + 1}）")


def parse_keyword_rules(value: str) -> List[KeywordRule]:
    """Parse semicolon-separated quoted keyword rules with AND precedence."""

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

    index = skip_whitespace(index)
    if index >= length:
        return []

    rules = []
    while index < length:
        if text[index] == ';':
            raise _rule_error('分号之间不能存在空规则', index)

        groups = []
        current_group = []
        keyword, index = parse_quoted_keyword(index)
        current_group.append(keyword)

        while True:
            whitespace_start = index
            index = skip_whitespace(index)
            had_whitespace = index > whitespace_start

            if index >= length:
                groups.append(tuple(current_group))
                source = ' or '.join(
                    ' and '.join(f'"{item}"' for item in group)
                    for group in groups
                )
                rules.append(KeywordRule(source, tuple(groups)))
                return rules

            if text[index] == ';':
                groups.append(tuple(current_group))
                source = ' or '.join(
                    ' and '.join(f'"{item}"' for item in group)
                    for group in groups
                )
                rules.append(KeywordRule(source, tuple(groups)))
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
                end = index + len(candidate)
                if text[index:end].lower() == candidate and (
                    end == length or text[end].isspace()
                ):
                    operator = candidate
                    index = end
                    break
            if operator is None:
                raise _rule_error('仅支持 and、or 或分号连接关键词', index)

            index = skip_whitespace(index)
            if index >= length or text[index] != '"':
                raise _rule_error(f'{operator} 后缺少带英文双引号的关键词', index)

            if operator == 'or':
                groups.append(tuple(current_group))
                current_group = []
            keyword, index = parse_quoted_keyword(index)
            current_group.append(keyword)

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
        all(normalize_text(keyword) in normalized_text for keyword in group)
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
