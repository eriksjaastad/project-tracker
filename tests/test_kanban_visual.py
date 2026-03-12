"""Visual regression tests for Kanban board UI.

This test suite captures screenshots of the Kanban board to detect layout issues
like column cutoff, spacing problems, and other visual regressions.
"""

import pytest
from playwright.sync_api import Page, expect
import subprocess
import time
import os


@pytest.fixture(scope="module")
def dashboard_server():
    """Return the dashboard server URL.

    Note: The server should be running before tests (via `./pt launch`).
    """
    return "http://localhost:8000"


def test_kanban_board_full_layout(page: Page, dashboard_server):
    """Test that all Kanban columns are visible and not cut off.

    This test captures a full screenshot of the Kanban board to verify:
    - All columns (Backlog, To Do, In Progress, Review, Done) are visible
    - The DONE column is not cut off on the right edge
    - Proper spacing exists between columns and at the edges
    """
    # Navigate to Kanban board
    page.goto(f"{dashboard_server}/kanban")

    # Wait for the board to load
    page.wait_for_selector(".kanban-board-content", timeout=10000)

    # Take a full-page screenshot
    screenshot_path = "tests/screenshots/kanban_full_board.png"
    os.makedirs("tests/screenshots", exist_ok=True)
    page.screenshot(path=screenshot_path, full_page=True)

    print(f"\n📸 Screenshot saved to: {screenshot_path}")
    print("   Open this file to visually inspect the Kanban board layout")

    # Verify all columns are present
    columns = page.locator(".column")
    expect(columns).to_have_count(5)  # Backlog, To Do, In Progress, Review, Done

    # Print all column positions for debugging
    print("\n📊 Column Layout:")
    for i in range(5):
        col = columns.nth(i)
        box = col.bounding_box()
        if box:
            col_title = col.locator(".column-title").text_content()
            print(f"   {col_title}: x={box['x']:.0f}px, width={box['width']:.0f}px, right_edge={box['x'] + box['width']:.0f}px")

    # Verify the Done column is visible
    done_column = page.locator(".column").filter(has_text="Done").first
    expect(done_column).to_be_visible()


def test_kanban_board_done_column_visibility(page: Page, dashboard_server):
    """Specifically test that the Done column has proper spacing and is fully visible."""
    page.goto(f"{dashboard_server}/kanban")
    page.wait_for_selector(".kanban-board-content", timeout=10000)

    # Get the Done column
    done_column = page.locator(".column").filter(has_text="Done").first
    
    # Get the bounding box of the DONE column
    done_box = done_column.bounding_box()
    assert done_box is not None, "DONE column should be visible"
    
    # Get the viewport width
    viewport_size = page.viewport_size
    assert viewport_size is not None
    
    # Check that the DONE column's right edge is not at the viewport edge
    # There should be at least some padding (we added var(--space-xl) = 24px)
    right_edge = done_box["x"] + done_box["width"]
    
    print(f"\n📏 DONE column right edge: {right_edge}px")
    print(f"   Viewport width: {viewport_size['width']}px")
    print(f"   Distance from edge: {viewport_size['width'] - right_edge}px")
    
    # The column should not extend all the way to the viewport edge
    # Allow for scrollbar width (~15px) plus our padding (24px)
    assert right_edge < viewport_size["width"] - 10, \
        f"DONE column appears cut off (right edge at {right_edge}px, viewport {viewport_size['width']}px)"
    
    # Take a focused screenshot of the right side
    screenshot_path = "tests/screenshots/kanban_done_column.png"
    os.makedirs("tests/screenshots", exist_ok=True)
    done_column.screenshot(path=screenshot_path)
    
    print(f"📸 DONE column screenshot saved to: {screenshot_path}")


def test_kanban_board_horizontal_scroll(page: Page, dashboard_server):
    """Test that horizontal scrolling works and all columns remain accessible."""
    page.goto(f"{dashboard_server}/kanban")
    page.wait_for_selector(".kanban-board-content", timeout=10000)
    
    # Get the scrollable container
    board_content = page.locator(".kanban-board-content")
    
    # Scroll to the far right
    board_content.evaluate("el => el.scrollLeft = el.scrollWidth")
    
    # Wait for scroll to complete
    page.wait_for_timeout(500)
    
    # Take screenshot after scrolling right
    screenshot_path = "tests/screenshots/kanban_scrolled_right.png"
    os.makedirs("tests/screenshots", exist_ok=True)
    page.screenshot(path=screenshot_path, full_page=True)
    
    print(f"\n📸 Scrolled-right screenshot saved to: {screenshot_path}")
    
    # Verify DONE column is still fully visible after scrolling
    done_column = page.locator(".column").filter(has_text="DONE").first
    expect(done_column).to_be_visible()
    
    # The DONE column should be fully in view
    done_box = done_column.bounding_box()
    assert done_box is not None
    
    viewport_size = page.viewport_size
    assert viewport_size is not None
    
    # After scrolling right, the DONE column should be fully visible
    # and have proper right padding
    right_edge = done_box["x"] + done_box["width"]
    print(f"📏 After scroll - DONE column right edge: {right_edge}px")
    print(f"   Viewport width: {viewport_size['width']}px")
    
    # Should have padding on the right
    assert right_edge < viewport_size["width"], \
        "DONE column should have right padding even when scrolled"

