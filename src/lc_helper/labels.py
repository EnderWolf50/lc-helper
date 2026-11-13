"""The words that tell lc-helper which screen it looks at, as OCR reads them: label -> its word in each language.

en is a part of the English label, lower case (maalc's checks). cn is a part of LLC's Simplified Chinese for the same
UI id in the game's text (LLC's whole label in parentheses): the word that names it, without the E.G.O and the
punctuation OCR may read otherwise.
"""

WORDS = {
    "choices": {"en": "choice", "cn": "选项"},  # an event's Choices page header: BattleUIText selection (选项)
    # the gift choice's Refuse Gift button: MirrorDungeonUI_2 mirror_dungeon_give_up_ego_gift (拒绝饰品)
    "refuse": {"en": "refuse", "cn": "拒绝"},
    # the E.G.O Gift GET! window's title: MirrorDungeonUI mirrordungeon_acquire_ego_gift_popup (获得E.G.O饰品！).
    # LLC writes a gift card's Acquire E.G.O Gift tag the same (获得E.G.O饰品), and on the gift choice the tags reach
    # into the title's region: tell the choice by its refuse first.
    "get": {"en": "get", "cn": "获得"},
    # a check's prompt: BattleUIText choice_personality (选择一位罪人来进行判定：)
    "check": {"en": "choose a character", "cn": "选择一位罪人"},
    # The event button's labels, each word the whole label. No LLC text was found for SKIP: the button may be a
    # picture, the same under LLC (inferred; no LLC capture shows it).
    "skip": {"en": "skip"},
    "proceed": {"en": "proceed", "cn": "继续"},  # BattleUIText ab_event_next
    "continue": {"en": "continue", "cn": "继续"},  # BattleUIText choice_event_resume
    "commence": {"en": "commence", "cn": "进行判定"},  # BattleUIText ab_event_decision
}


def shows(lines, label):
    """Whether any of the OCR'd lines holds label's word in some language."""
    return any(word in text.lower() for text in lines for word in WORDS[label].values())
