"""Standalone demo for selecting bars inside one cluster.

This file is intentionally separate from `Wafer_Map_GUI.py` and
`wafer_map_selector.py`. It demonstrates the next visual layer only: one
cluster split into horizontal bars, with click and drag selection.
"""

from __future__ import annotations

from dataclasses import dataclass
from tkinter import Canvas, Event, StringVar, Tk
from tkinter import ttk
from typing import Iterable, Literal


DragAction = Literal["select", "deselect"]
Point = tuple[float, float]
CanvasRect = tuple[float, float, float, float]


@dataclass(frozen=True)
class DemoBar:
    """One demo bar rectangle in cluster-local coordinates."""

    label: str
    top_left: Point
    width: float
    height: float


def _build_demo_bars(
        cluster_width: float,
        bar_height: float,
        bar_count: int,
) -> list[DemoBar]:
    """Build a top-to-bottom stack of demo bars for one cluster."""
    bars: list[DemoBar] = []
    cluster_top_y = bar_height * bar_count / 2
    cluster_left_x = -cluster_width / 2

    for bar_index in range(bar_count):
        bars.append(DemoBar(
            label=str(bar_index + 1),
            top_left=(
                cluster_left_x,
                cluster_top_y - bar_index * bar_height,
            ),
            width=cluster_width,
            height=bar_height,
        ))

    return bars


class BarSelectorDemo(Tk):
    """Standalone bar-level visual selector demo."""

    cluster_width: float
    cluster_height: float
    bar_height: float

    selected_labels: set[str]  # Bar labels selected for inclusion in this demo.

    item_to_label: dict[int, str]  # Canvas item ID -> bar label for mouse events.

    bar_rect_items: dict[str, int]  # Bar label -> rectangle item ID.

    bar_text_items: dict[str, int]  # Bar label -> text item ID.

    cluster_outline_item: int | None  # Canvas item ID for the cluster border.

    legend_item: int | None  # Canvas item ID for the legend text.

    drag_start: Point | None  # Canvas coordinate where the current gesture started.

    drag_rect_id: int | None  # Canvas item ID for the temporary drag rectangle.

    drag_action: DragAction  # Whether the active drag box selects or deselects.

    drag_moved: bool  # False for click gestures; true after drag threshold.

    status: StringVar
    bars: list[DemoBar]
    canvas: Canvas

    def __init__(
            self,
            cluster_width: float = 10.5,
            bar_height: float = 0.25,
            bar_count: int = 42,
    ) -> None:
        """Initialize the standalone bar selector demo."""
        super().__init__()
        self.title("Bar selector demo")
        self.geometry("680x820")
        self.minsize(520, 620)

        self.cluster_width = cluster_width
        self.bar_height = bar_height
        self.cluster_height = bar_height * bar_count
        self.selected_labels: set[str] = set()
        self.item_to_label: dict[int, str] = {}
        self.bar_rect_items: dict[str, int] = {}
        self.bar_text_items: dict[str, int] = {}
        self.cluster_outline_item: int | None = None
        self.legend_item: int | None = None
        self.drag_start: Point | None = None
        self.drag_rect_id: int | None = None
        self.drag_action: DragAction = "select"
        self.drag_moved = False
        self.status = StringVar()

        self.bars = _build_demo_bars(
            cluster_width=self.cluster_width,
            bar_height=self.bar_height,
            bar_count=bar_count,
        )

        self._build_layout()
        self._create_canvas_items()
        self._layout_canvas_items()
        self._update_status()

    def _build_layout(self) -> None:
        """Create toolbar, canvas, and status footer."""
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(self, padding=(12, 10))
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.columnconfigure(0, weight=1)

        ttk.Label(
            toolbar,
            text=(
                "Bar demo: click to toggle. Drag from an unselected bar to select; "
                "drag from a selected bar to deselect."
            ),
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(toolbar, text="Clear", command=self._clear_selection).grid(
            row=0,
            column=1,
            padx=(12, 0),
        )

        self.canvas = Canvas(self, background="#f7f7f7", highlightthickness=0)
        self.canvas.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 8))
        self.canvas.bind("<Configure>", self._layout_canvas_items)
        self.canvas.bind("<ButtonPress-1>", self._start_drag)
        self.canvas.bind("<B1-Motion>", self._drag_selection_box)
        self.canvas.bind("<ButtonRelease-1>", self._finish_drag)

        footer = ttk.Frame(self, padding=(12, 0, 12, 10))
        footer.grid(row=2, column=0, sticky="ew")
        ttk.Label(footer, textvariable=self.status).grid(row=0, column=0, sticky="w")

    def _scale(self) -> float:
        """Return the current millimeter-to-canvas-pixel scale."""
        canvas_width = max(self.canvas.winfo_width(), 1)
        canvas_height = max(self.canvas.winfo_height(), 1)
        padding = 56
        return min(
            (canvas_width - padding * 2) / self.cluster_width,
            (canvas_height - padding * 2) / self.cluster_height,
        )

    def _to_canvas(self, point: Point) -> Point:
        """Convert cluster-local coordinates to canvas coordinates."""
        scale = self._scale()
        center_x = self.canvas.winfo_width() / 2
        center_y = self.canvas.winfo_height() / 2
        x, y = point
        return center_x + x * scale, center_y - y * scale

    def _bar_rect(self, bar: DemoBar) -> CanvasRect:
        """Return the bar rectangle in canvas coordinates."""
        left_x, top_y = bar.top_left
        x1, y1 = self._to_canvas((left_x, top_y))
        x2, y2 = self._to_canvas((left_x + bar.width, top_y - bar.height))
        return x1, y1, x2, y2

    def _create_canvas_items(self) -> None:
        """Create persistent canvas items for the bar layer."""
        self.item_to_label.clear()
        self.bar_rect_items.clear()
        self.bar_text_items.clear()

        self.cluster_outline_item = self.canvas.create_rectangle(
            0,
            0,
            0,
            0,
            fill="#ffffff",
            outline="#333333",
            width=2,
        )

        for bar in self.bars:
            rect_id = self.canvas.create_rectangle(0, 0, 0, 0)
            text_id = self.canvas.create_text(
                0,
                0,
                text=bar.label,
                fill="#333333",
                font=("TkDefaultFont", 8),
            )
            self.bar_rect_items[bar.label] = rect_id
            self.bar_text_items[bar.label] = text_id
            self.item_to_label[rect_id] = bar.label

        self.legend_item = self.canvas.create_text(
            16,
            16,
            text="gray=excluded by default  blue=selected for inclusion",
            anchor="nw",
            fill="#333333",
        )

    def _layout_canvas_items(self, _event: Event | None = None) -> None:
        """Move existing canvas items to match the current canvas size."""
        cluster_left = -self.cluster_width / 2
        cluster_top = self.cluster_height / 2
        x1, y1 = self._to_canvas((cluster_left, cluster_top))
        x2, y2 = self._to_canvas((
            cluster_left + self.cluster_width,
            cluster_top - self.cluster_height,
        ))

        if self.cluster_outline_item is not None:
            self.canvas.coords(self.cluster_outline_item, x1, y1, x2, y2)

        for bar in self.bars:
            bx1, by1, bx2, by2 = self._bar_rect(bar)
            rect_id = self.bar_rect_items[bar.label]
            text_id = self.bar_text_items[bar.label]
            self.canvas.coords(rect_id, bx1, by1, bx2, by2)
            self.canvas.coords(text_id, bx1 + 18, (by1 + by2) / 2)

            if abs(by2 - by1) >= 12:
                self.canvas.itemconfigure(text_id, state="normal")
            else:
                self.canvas.itemconfigure(text_id, state="hidden")
            self._update_bar_style(bar.label)

        if self.legend_item is not None:
            self.canvas.coords(self.legend_item, 16, 16)

    def _update_bar_style(self, label: str) -> None:
        """Update one bar's color and outline."""
        rect_id = self.bar_rect_items[label]
        selected = label in self.selected_labels
        self.canvas.itemconfigure(
            rect_id,
            fill="#6ea8fe" if selected else "#d9d9d9",
            outline="#222222" if selected else "#b5b5b5",
            width=2 if selected else 1,
        )

    def _update_bar_styles(self, labels: Iterable[str]) -> None:
        """Update multiple bar styles without rebuilding canvas items."""
        for label in labels:
            self._update_bar_style(label)

    def _start_drag(self, event: Event) -> None:
        """Begin a click or drag gesture."""
        self.drag_start = (event.x, event.y)
        self.drag_moved = False
        start_label = self._label_at(event.x, event.y)
        self.drag_action = (
            "deselect"
            if start_label is not None and start_label in self.selected_labels
            else "select"
        )
        if self.drag_rect_id is not None:
            self.canvas.delete(self.drag_rect_id)
            self.drag_rect_id = None

    def _drag_selection_box(self, event: Event) -> None:
        """Update the temporary drag-selection rectangle."""
        if self.drag_start is None:
            return

        start_x, start_y = self.drag_start
        if abs(event.x - start_x) > 3 or abs(event.y - start_y) > 3:
            self.drag_moved = True

        if not self.drag_moved:
            return

        if self.drag_rect_id is None:
            self.drag_rect_id = self.canvas.create_rectangle(
                start_x,
                start_y,
                event.x,
                event.y,
                outline="#1f6feb",
                dash=(4, 3),
                width=2,
            )
            return

        self.canvas.coords(self.drag_rect_id, start_x, start_y, event.x, event.y)

    def _finish_drag(self, event: Event) -> None:
        """Finish a gesture as either a click toggle or drag-box action."""
        if self.drag_start is None:
            return

        start_x, start_y = self.drag_start
        if self.drag_rect_id is not None:
            self.canvas.delete(self.drag_rect_id)
            self.drag_rect_id = None

        if self.drag_moved:
            self._apply_drag_box(start_x, start_y, event.x, event.y)
        else:
            self._toggle_bar_at(event.x, event.y)

        self.drag_start = None
        self.drag_action = "select"
        self.drag_moved = False

    def _label_at(self, x: float, y: float) -> str | None:
        """Return the topmost bar label at a canvas point, if any."""
        items = self.canvas.find_overlapping(x, y, x, y)
        for item_id in reversed(items):
            label = self.item_to_label.get(item_id)
            if label is not None:
                return label
        return None

    def _toggle_bar_at(self, x: float, y: float) -> None:
        """Handle a single-click selection change at a canvas point."""
        items = self.canvas.find_overlapping(x, y, x, y)
        for item_id in reversed(items):
            label = self.item_to_label.get(item_id)
            if label is None:
                continue
            if label in self.selected_labels:
                self.selected_labels.remove(label)
            else:
                self.selected_labels.add(label)
            self._update_bar_style(label)
            self._update_status()
            return

    def _apply_drag_box(
            self,
            start_x: float,
            start_y: float,
            end_x: float,
            end_y: float,
    ) -> None:
        """Apply the active drag action to all bars touched by the box."""
        left = min(start_x, end_x)
        right = max(start_x, end_x)
        top = min(start_y, end_y)
        bottom = max(start_y, end_y)

        changed_any = False
        changed_labels: list[str] = []
        for bar in self.bars:
            bar_left, bar_top, bar_right, bar_bottom = self._bar_rect(bar)
            if (
                    bar_right < left
                    or bar_left > right
                    or bar_bottom < top
                    or bar_top > bottom
            ):
                continue
            if self.drag_action == "select":
                if bar.label not in self.selected_labels:
                    self.selected_labels.add(bar.label)
                    changed_labels.append(bar.label)
                    changed_any = True
            elif bar.label in self.selected_labels:
                self.selected_labels.remove(bar.label)
                changed_labels.append(bar.label)
                changed_any = True

        if changed_any:
            self._update_bar_styles(changed_labels)
            self._update_status()

    def _clear_selection(self) -> None:
        """Clear all demo bar inclusions."""
        cleared_labels = list(self.selected_labels)
        self.selected_labels.clear()
        self._update_bar_styles(cleared_labels)
        self._update_status()

    def _update_status(self) -> None:
        """Refresh the footer summary counts."""
        self.status.set(
            f"Selected {len(self.selected_labels)} of {len(self.bars)} bars."
        )


if __name__ == "__main__":
    BarSelectorDemo().mainloop()
