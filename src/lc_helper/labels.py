"""The words that tell lc-helper which screen it looks at, as OCR reads them: label -> its word in each language.

en is a part of the English label, lower case (maalc's checks). cn is LLC's Simplified Chinese for the same UI id
in the game's text, the part least likely to be misread; LLC_zh-CN in parentheses.
"""

WORDS = {
    "choices": {"en": "choice", "cn": "选项"},  # an event's Choices page header: BattleUIText selection (选项)
}


def shows(lines, label):
    """Whether any of the OCR'd lines holds label's word in some language."""
    return any(word in text.lower() for text in lines for word in WORDS[label].values())
