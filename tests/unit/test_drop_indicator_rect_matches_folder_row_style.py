#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for drop indicator rect matching FolderRowWidget styled geometry.

Bug: during multi-select note drag, the pale-yellow drop-target overlay drawn
in FolderListWidget.paintEvent() uses the full visualItemRect() width. But
FolderRowWidget has stylesheet rules:
    margin-left: 8px; margin-right: 8px; border-radius: 6px
so the actual selection/hover highlight is inset and rounded. The drag overlay
appears wider and sharp-cornered — inconsistent with the real selection style.

Root cause: paintEvent draws `painter.fillRect(self._drop_indicator_rect, ...)`
which is a full-width solid rectangle. It should be an inset (8px left/right)
rounded rectangle (radius 6px) to match FolderRowWidget's visual appearance.

Fix: replace `painter.fillRect` with QPainterPath + addRoundedRect using an
adjusted rect: self._drop_indicator_rect.adjusted(8, 0, -8, 0), radius=6.
"""

import sys
import os
import types
import inspect
import pytest
from unittest.mock import MagicMock, patch, call, ANY
from PyQt6.QtCore import QRect, QRectF


def _import_folder_list_widget():
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    from main_window import FolderListWidget
    return FolderListWidget


# ---------------------------------------------------------------------------
# Core regression tests — these FAIL before the fix
# ---------------------------------------------------------------------------

class TestDropIndicatorRectMatchesFolderRowStyle:
    """
    paintEvent must draw the 'on' drop indicator as an inset rounded rectangle
    matching FolderRowWidget's stylesheet (margin-left/right: 8px, border-radius: 6px).
    """

    def test_paintEvent_source_does_not_use_fillRect_for_on_indicator(self):
        """
        The paintEvent source code must NOT use painter.fillRect() for the
        'on' drop indicator branch. Before the fix, paintEvent calls fillRect
        which draws a full-width sharp rectangle instead of the inset rounded
        shape that matches FolderRowWidget's stylesheet.

        This test inspects the source to assert the old code is gone.
        """
        FolderListWidget = _import_folder_list_widget()
        src = inspect.getsource(FolderListWidget.paintEvent)

        # After the fix, fillRect must not appear inside the 'on' branch.
        # A simple check: the method should use QPainterPath instead.
        assert 'fillRect' not in src, (
            "paintEvent still calls fillRect() for the 'on' drop indicator. "
            "This draws a full-width sharp rectangle that does not match "
            "FolderRowWidget's margin-left/right: 8px + border-radius: 6px style. "
            "Replace with QPainterPath + addRoundedRect using adjusted rect."
        )

    def test_paintEvent_source_uses_qpainterpath_for_on_indicator(self):
        """
        paintEvent must use QPainterPath to draw a rounded fill for 'on'.
        """
        FolderListWidget = _import_folder_list_widget()
        src = inspect.getsource(FolderListWidget.paintEvent)

        assert 'QPainterPath' in src, (
            "paintEvent does not reference QPainterPath. "
            "The 'on' drop indicator must be drawn as a rounded rectangle "
            "using QPainterPath.addRoundedRect() to match FolderRowWidget's "
            "border-radius: 6px style."
        )

    def test_paintEvent_source_uses_adjusted_rect_with_8px_inset(self):
        """
        paintEvent must adjust the indicator rect by 8px left and right.
        Expected: self._drop_indicator_rect.adjusted(8, 0, -8, 0) or equivalent.
        """
        FolderListWidget = _import_folder_list_widget()
        src = inspect.getsource(FolderListWidget.paintEvent)

        # The fix must call .adjusted(8, 0, -8, 0) on the drop indicator rect
        assert 'adjusted(8, 0, -8, 0)' in src, (
            "paintEvent does not call .adjusted(8, 0, -8, 0) on the indicator rect. "
            "FolderRowWidget has margin-left: 8px; margin-right: 8px — the overlay "
            "must be inset by 8px on each side so it matches the actual selection style. "
            "Use: adjusted_rect = self._drop_indicator_rect.adjusted(8, 0, -8, 0)"
        )

    def test_paintEvent_source_uses_radius_6(self):
        """
        paintEvent must use border-radius 6 in addRoundedRect to match the
        FolderRowWidget stylesheet: border-radius: 6px.
        """
        FolderListWidget = _import_folder_list_widget()
        src = inspect.getsource(FolderListWidget.paintEvent)

        # addRoundedRect(rect_or_x, ..., 6, 6) or similar
        assert '6, 6' in src, (
            "paintEvent does not use radius (6, 6) in the rounded rect call. "
            "FolderRowWidget has border-radius: 6px — the overlay must use "
            "the same radius so it visually matches the selection highlight. "
            "Use: path.addRoundedRect(QRectF(adjusted_rect), 6, 6)"
        )


# ---------------------------------------------------------------------------
# Geometry unit tests — independent of Qt rendering
# ---------------------------------------------------------------------------

class TestAdjustedRectGeometry:
    """
    The adjusted QRect geometry used for the rounded overlay must be correct
    given a typical visualItemRect().
    """

    def test_adjusted_rect_x_is_8(self):
        """Left edge of adjusted rect must be 8 px from original left."""
        original = QRect(0, 0, 210, 36)
        adjusted = original.adjusted(8, 0, -8, 0)
        assert adjusted.x() == 8, (
            f"Expected adjusted x=8, got {adjusted.x()}. "
            f"Original rect: {original!r}"
        )

    def test_adjusted_rect_width_is_reduced_by_16(self):
        """Width of adjusted rect must be original width − 16 (8 inset each side)."""
        original = QRect(0, 0, 210, 36)
        adjusted = original.adjusted(8, 0, -8, 0)
        expected_width = 210 - 16  # 194
        assert adjusted.width() == expected_width, (
            f"Expected adjusted width={expected_width}, got {adjusted.width()}. "
            f"Original rect: {original!r}"
        )

    def test_adjusted_rect_y_and_height_unchanged(self):
        """Top and height of adjusted rect must be unchanged."""
        original = QRect(0, 12, 210, 36)
        adjusted = original.adjusted(8, 0, -8, 0)
        assert adjusted.y() == 12, (
            f"Expected y=12 (unchanged), got {adjusted.y()}."
        )
        assert adjusted.height() == 36, (
            f"Expected height=36 (unchanged), got {adjusted.height()}."
        )

    def test_adjusted_rect_right_edge_is_8_from_original_right(self):
        """Right edge of adjusted rect must be 8 px inside original right edge."""
        original = QRect(0, 0, 210, 36)
        adjusted = original.adjusted(8, 0, -8, 0)
        assert adjusted.right() == original.right() - 8, (
            f"Expected right={original.right() - 8}, got {adjusted.right()}."
        )
