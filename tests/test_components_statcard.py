from gui.components.card import Card
from gui.components.statcard import KpiStrip, StatCard
from gui.theme_manager import type_style


def test_statcard_is_a_card_not_a_new_frame(qapp):
    assert issubclass(StatCard, Card)


def test_statcard_shows_the_value_and_label(qapp):
    card = StatCard("128", "Orders packed")
    assert card.value_label.text() == "128"
    assert card.sub_label.text() == "Orders packed"


def test_the_numeral_uses_display_xl(qapp):
    card = StatCard("128", "Orders packed")
    assert f"{type_style('display_xl').size_pt}pt" in card.value_label.styleSheet()


def test_the_sublabel_uses_caption(qapp):
    card = StatCard("128", "Orders packed")
    assert f"{type_style('caption').size_pt}pt" in card.sub_label.styleSheet()


def test_set_value_updates_live(qapp):
    card = StatCard("0", "Orders packed")
    card.set_value("41")
    assert card.value_label.text() == "41"


def test_kpistrip_collects_cards_in_order(qapp):
    strip = KpiStrip()
    first = strip.add("12", "Waves")
    second = strip.add("340", "Units")
    assert strip.cards() == [first, second]
    assert strip.layout().count() == 2
