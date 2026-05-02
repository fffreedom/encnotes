#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests verifying that the 'on' drop indicator uses row_widget.geometry()
instead of visualItemRect() as its base rectangle.

Root cause (confirmed via runtime log on 2026-05-02):
  visualItemRect  = (x=0, y=84, w=212, h=28)
  row_widget.geometry() = (x=10, y=90, w=192, h=28)

The CSS yellow background (selected/hovered state) is drawn on the row_widget
with margin-left: 8px; margin-right: 8px, so its actual painted area is:
  x = 10+8 = 18,  width = 192-16 = 176,  y=90, h=28

Using visualItemRect.adjusted(8, 0, -8, 0) gives:
  x = 0+8 = 8, width = 212-16 = 196  ← wrong, does not match the CSS yellow

The fix: in paintEvent's 'on' branch, obtain row_widget via
  self.itemWidget(self._drop_target_item).geometry()
then apply .adjusted(8, 0, -8, 0) to that geometry — not to visualItemRect.
"""

import sys
import os
import inspect
import pytest
from PyQt6.QtCore import QRect


def _import_folder_list_widget():
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    from main_window import FolderListWidget
    return FolderListWidget


# ---------------------------------------------------------------------------
# Core regression tests — these FAIL before the fix
# ---------------------------------------------------------------------------

class TestDropIndicatorUsesRowWidgetGeometry:
    """
    paintEvent must use itemWidget(target_item).geometry() as the base rect
    for the 'on' drop indicator, not visualItemRect().

    Runtime measurements confirmed:
      visualItemRect.x=0  vs  row_widget.geometry().x=10  (10px difference)
      visualItemRect.w=212 vs row_widget.geometry().w=192 (20px difference)
      visualItemRect.y=84  vs  row_widget.geometry().y=90 (6px difference)

    After applying margin-left/right: 8px, the visual CSS yellow area is:
      x=18, w=176, y=90, h=28

    Using visualItemRect.adjusted(8,0,-8,0) incorrectly produces:
      x=8, w=196, y=84, h=28 — does not match the CSS yellow background.
    """

    def test_paintEvent_source_calls_itemWidget(self):
        """
        paintEvent must call self.itemWidget() in the 'on' branch to obtain
        the actual widget placed inside the list item. Before the fix, paintEvent
        never calls itemWidget — it uses _drop_indicator_rect (visualItemRect)
        directly, which gives wrong coordinates.
        """
        FolderListWidget = _import_folder_list_widget()
        src = inspect.getsource(FolderListWidget.paintEvent)

        assert 'itemWidget' in src, (
            "paintEvent does not call itemWidget() for the 'on' drop indicator. "
            "visualItemRect() returns wrong coordinates (x=0, w=212) compared to "
            "the actual widget position (x=10, w=192) and CSS yellow area (x=18, w=176). "
            "Fix: use self.itemWidget(self._drop_target_item).geometry() as base rect."
        )

    def test_paintEvent_source_calls_geometry_on_row_widget(self):
        """
        paintEvent must call .geometry() on the row widget to get its actual
        viewport coordinates. Before the fix, no .geometry() call exists in
        paintEvent — it uses _drop_indicator_rect which is visualItemRect().
        """
        FolderListWidget = _import_folder_list_widget()
        src = inspect.getsource(FolderListWidget.paintEvent)

        assert 'geometry()' in src, (
            "paintEvent does not call .geometry() in the 'on' drop indicator branch. "
            "row_widget.geometry() gives x=10, w=192 (matching the widget's actual "
            "viewport position), while visualItemRect gives x=0, w=212 (the full item "
            "bounding rect including padding). The overlay must use geometry() so that "
            "adjusted(8,0,-8,0) aligns with the CSS-rendered yellow background."
        )


# ---------------------------------------------------------------------------
# Geometry unit tests — verify correct rect arithmetic
# ---------------------------------------------------------------------------

class TestWidgetGeometryAdjustedRect:
    """
    Given the runtime-measured row_widget.geometry() = (10, 90, 192, 28),
    adjusted(8, 0, -8, 0) must produce the rect that matches the CSS yellow area.
    """

    WIDGET_GEOMETRY = QRect(10, 90, 192, 28)  # confirmed from runtime log

    def test_adjusted_x_matches_css_left_edge(self):
        """
        x = widget.geometry().x() + 8 = 10 + 8 = 18
        This is where the CSS yellow background starts (margin-left: 8px).
        """
        adjusted = self.WIDGET_GEOMETRY.adjusted(8, 0, -8, 0)
        assert adjusted.x() == 18, (
            f"Expected x=18 (widget x=10 + margin 8), got {adjusted.x()}."
        )

    def test_adjusted_width_matches_css_yellow_width(self):
        """
        width = widget.geometry().width() - 16 = 192 - 16 = 176
        This is the width of the CSS yellow background (8px margin each side).
        """
        adjusted = self.WIDGET_GEOMETRY.adjusted(8, 0, -8, 0)
        assert adjusted.width() == 176, (
            f"Expected width=176 (widget w=192 - 2*8 margin), got {adjusted.width()}."
        )

    def test_adjusted_y_matches_widget_y(self):
        """
        y = widget.geometry().y() = 90 (not visualItemRect.y() = 84)
        The 6px difference is due to QListWidget::item padding: 6px top.
        """
        adjusted = self.WIDGET_GEOMETRY.adjusted(8, 0, -8, 0)
        assert adjusted.y() == 90, (
            f"Expected y=90 (widget top, not visualItemRect.y=84), got {adjusted.y()}."
        )

    def test_adjusted_height_unchanged(self):
        """Height must be unchanged: 28px."""
        adjusted = self.WIDGET_GEOMETRY.adjusted(8, 0, -8, 0)
        assert adjusted.height() == 28, (
            f"Expected height=28 (unchanged), got {adjusted.height()}."
        )

    def test_visual_item_rect_adjusted_gives_wrong_x(self):
        """
        Regression guard: visualItemRect.adjusted(8,0,-8,0) gives x=8 NOT x=18.
        This test documents WHY the old approach was wrong.
        """
        visual_item_rect = QRect(0, 84, 212, 28)  # from runtime log
        old_adjusted = visual_item_rect.adjusted(8, 0, -8, 0)
        assert old_adjusted.x() != 18, (
            "visualItemRect.adjusted(8,0,-8,0).x() == 18 — this is a coincidence, "
            "not a general property. Update this test if widget positions change."
        )
        assert old_adjusted.x() == 8, (
            f"Expected old approach x=8 (wrong), got {old_adjusted.x()}."
        )

    def test_visual_item_rect_adjusted_gives_wrong_width(self):
        """
        Regression guard: visualItemRect.adjusted(8,0,-8,0) gives width=196 NOT 176.
        """
        visual_item_rect = QRect(0, 84, 212, 28)  # from runtime log
        old_adjusted = visual_item_rect.adjusted(8, 0, -8, 0)
        assert old_adjusted.width() == 196, (
            f"Expected old approach width=196 (wrong), got {old_adjusted.width()}."
        )
