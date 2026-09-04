"""What a screen shows instead of its table when there is nothing to show.

One widget with four constructors, replacing per-screen invention. The rule
every variant obeys: name the cause, name the file or filter that caused it,
and offer the action that resolves it. No apologies, no exclamation marks.

"No data · Nothing to display" is the thing none of them may be -- that
sentence cannot tell "you have not loaded anything" from "your filter is too
tight" from "the server is unreachable".

It *holds* a Card rather than subclassing one: QSS type selectors match
className() exactly (see build_stylesheet's own note), so a subclass would
need its own selector in shared/theme.py -- a packing-tool PR for a plane this
widget can have for free by composing.

Spec: docs/superpowers/specs/2026-09-04-phase9-bundle3-components-design.md §5
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget

from gui.components.card import Card
from gui.theme_manager import get_theme_manager
from shared.theme import set_button_role


class StatePanel(QWidget):
    """A centred card explaining why a screen is empty, and what to do next.

    Attributes:
        card: the Card holding the text and the action.
        button: the single action, or None when the state has none.
    """

    def __init__(
        self,
        title: str,
        cause: str,
        *,
        detail: str = "",
        action_text: str = "",
        action_role: str = "primary",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.card = Card(min_width=360, margins=(24, 20, 24, 20), spacing=8)
        self.card.add_text(title, "heading", wrap=True)
        self.card.add_text(cause, "body", wrap=True)

        if detail:
            theme = get_theme_manager().get_current_theme()
            # 9.11 gives this line the one mono face; until then it is caption
            # in the secondary colour. The Qt tier has no mono family and
            # adding one is a token, which belongs to shared/ and to 9.11.
            self.card.add_text(
                detail, "caption", wrap=True, css=f"color: {theme.text_secondary};"
            )

        self.button = None
        if action_text:
            self.button = QPushButton(action_text)
            set_button_role(self.button, action_role)
            self.card.layout().addWidget(self.button, 0, Qt.AlignCenter)

        # Centring is stretches, not margins -- a margin has to be recomputed
        # for every page size the card lands on.
        outer = QVBoxLayout(self)
        outer.addStretch(1)
        outer.addWidget(self.card, 0, Qt.AlignCenter)
        outer.addStretch(1)

    @classmethod
    def nothing_loaded(cls, title, cause, action_text, parent=None):
        """Nothing has been loaded yet. One accent-filled way to load it."""
        return cls(title, cause, action_text=action_text, parent=parent)

    @classmethod
    def working(cls, title, step, parent=None):
        """Work is in flight. A named step beats a shimmer for a supervisor
        watching a network share, and Qt has no animation to shimmer with."""
        return cls(title, step, parent=parent)

    @classmethod
    def no_results(cls, title, cause, action_text="Clear all filters", parent=None):
        """A filter emptied the list. Secondary, because the operator may
        actually want the empty answer."""
        return cls(title, cause, action_text=action_text,
                   action_role="secondary", parent=parent)

    @classmethod
    def failed(cls, title, cause, detail, action_text, parent=None):
        """Something broke. State the consequence, then the cause in the
        file's own words, then the way out."""
        return cls(title, cause, detail=detail, action_text=action_text,
                   parent=parent)
