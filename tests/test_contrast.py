"""Every text colour the window sets reads at WCAG AA, 4.5:1, on what it is drawn on. Disabled controls are exempt."""

import inspect
import re

from PySide6.QtGui import QColor

from lc_helper import app as ui

# (rule, property) of a text colour, and (rule, property) of the background it is drawn on, in the style sheet
SHEET_PAIRS = [
    (("QWidget", "color"), ("QWidget#root", "background")),
    (("QWidget", "color"), ("QFrame#header", "background")),
    (("QWidget", "color"), ("QPushButton", "background")),
    (("QWidget", "color"), ("QPushButton:hover", "background")),
    (("QWidget", "color"), ("QLineEdit", "background")),
    (("QWidget", "color"), ("QComboBox QAbstractItemView", "background")),
    (("QWidget", "color"), ("QComboBox QAbstractItemView", "selection-background-color")),
    (("QWidget", "color"), ("QListWidget::item:selected", "background")),
    (("QLabel#title", "color"), ("QFrame#header", "background")),
    (("QLabel#device", "color"), ("QFrame#header", "background")),
    (("QLabel#section", "color"), ("QWidget#root", "background")),
    (("QLabel#status", "color"), ("QWidget#root", "background")),
    (("QLabel#sectionTitle", "color"), ("QPushButton#sectionHead", "background")),
    (("QLabel#sectionTitle", "color"), ("QPushButton#sectionHead:hover", "background")),
    (("QLabel#summary", "color"), ("QPushButton#sectionHead", "background")),
    (("QLabel#summary", "color"), ("QPushButton#sectionHead:hover", "background")),
    (("QPushButton:checked", "color"), ("QPushButton:checked", "background")),
    (("QPushButton#seg", "color"), ("QPushButton#seg", "background")),
    (("QPushButton#seg", "color"), ("QPushButton#seg:hover", "background")),
    (("QPushButton#seg:checked", "color"), ("QPushButton#seg:checked", "background")),
    (("QPushButton#start", "color"), ("QPushButton#start", "background")),
    (("QPushButton#start", "color"), ("QPushButton#start:hover", "background")),
    (("QPushButton#start", "color"), ('QPushButton#start[running="true"]', "background")),
    (("QPushButton#start", "color"), ('QPushButton#start[running="true"]:hover', "background")),
    (("QPushButton#link", "color"), ("QWidget#root", "background")),
    (("QPushButton#link:hover", "color"), ("QWidget#root", "background")),
    (("QPushButton#pill", "color"), ("QWidget#root", "background")),
    (("QPushButton#pill", "color"), ("QPushButton#pill:hover", "background")),
    (("QPushButton#pill:checked", "color"), ("QPushButton#pill:checked", "background")),
    (("QLineEdit", "placeholder-text-color"), ("QLineEdit", "background")),
    (("QToolTip", "color"), ("QToolTip", "background")),  # the switches' explanations live in tooltips
]


def luminance(colour):
    r, g, b = (c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in QColor(colour).getRgbF()[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(text, background):
    light, dark = sorted((luminance(text), luminance(background)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def sheet():
    """{selector: {property: value}} of the window's style sheet."""
    rules = {}
    for selectors, body in re.findall(r"([^{}]+)\{([^}]*)\}", ui.style(12, 21)):
        props = dict((k.strip(), v.strip()) for k, v in (p.split(":", 1) for p in body.split(";") if ":" in p))
        for selector in selectors.split(","):
            rules.setdefault(selector.strip(), {}).update(props)
    return rules


def test_contrast_matches_the_wcag_figures():
    assert round(contrast("#ffffff", "#000000"), 2) == 21
    assert round(contrast("#777777", "#ffffff"), 2) == 4.48


def test_the_style_sheet_text_reads_on_its_background():
    rules = sheet()
    ratios = {(text, on): contrast(rules[text[0]][text[1]], rules[on[0]][on[1]]) for text, on in SHEET_PAIRS}
    assert {pair: round(r, 2) for pair, r in ratios.items() if r < 4.5} == {}


def test_the_detail_pane_text_reads_on_the_pane():
    """Every colour in an HTML style attribute in the window's code, on that attribute's background or the pane's."""
    pane = sheet()["QTextBrowser"]["background"]
    pairs = set()
    for style in re.findall(r"style='([^']*)'", inspect.getsource(ui)):
        props = dict(p.split(":", 1) for p in style.split(";") if ":" in p)
        if "color" in props:
            assert QColor.isValidColorName(props["color"]), f"a colour the check cannot read: {style}"
            pairs.add((props["color"], props.get("background", pane)))
    assert len(pairs) > 5, f"the scan missed the pane's colours: {pairs}"
    assert {pair: round(contrast(*pair), 2) for pair in pairs if contrast(*pair) < 4.5} == {}
