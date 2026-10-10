"""
================================================================================
 ResQnet - Interactive AI Disaster Rescue Navigation Dashboard
================================================================================
 A Tkinter + NetworkX + PyTorch powered 15x15 grid interface for visualizing
 AI-driven route optimization through disaster zones.
================================================================================
"""

import os
import sys
import pickle
import tkinter as tk
from tkinter import ttk, font as tkfont

import numpy as np
import networkx as nx
import torch
import torch.nn as nn

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1: PyTorch Model Definition (must match training architecture)
# ══════════════════════════════════════════════════════════════════════════════

class DisasterRoutePredictor(nn.Module):
    """MLP: Input(5) -> 128 -> 64 -> 32 -> Output(1)"""
    def __init__(self, input_dim: int = 5):
        super().__init__()
        self.network = nn.Sequential(
            nn.Linear(input_dim, 128), nn.ReLU(), nn.BatchNorm1d(128), nn.Dropout(0.3),
            nn.Linear(128, 64),        nn.ReLU(), nn.BatchNorm1d(64),  nn.Dropout(0.2),
            nn.Linear(64, 32),         nn.ReLU(), nn.BatchNorm1d(32),
            nn.Linear(32, 1),          nn.ReLU(),
        )
    def forward(self, x):
        return self.network(x)

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2: Configuration & Asset Loading
# ══════════════════════════════════════════════════════════════════════════════

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
WEIGHTS_PATH = os.path.join(BASE_DIR, "weights", "rescue_ai_weights.pth")
SCALER_PATH  = os.path.join(BASE_DIR, "weights", "scaler.pkl")

GRID_ROWS    = 15
GRID_COLS    = 15
NODE_RADIUS  = 8
CELL_SIZE    = 50           # pixels between nodes

# ── Color Palette (Dark Theme) ───────────────────────────────────────────────
C_BG         = "#0d1117"    # deep dark background
C_PANEL      = "#161b22"    # sidebar panel
C_EDGE_DEF   = "#2d333b"    # default road color
C_EDGE_SEL   = "#ffffff"    # selected edge
C_NODE_DEF   = "#484f58"    # default node fill
C_NODE_HOVER = "#8b949e"    # hovered node
C_START      = "#3fb950"    # start node (green)
C_END        = "#f85149"    # end node (red)
C_PATH       = "#00e5ff"    # optimal path neon cyan
C_FIRE       = "#ff6a33"    # fire-hazard edge tint
C_FLOOD      = "#388bfd"    # flood-hazard edge tint
C_BOTH       = "#d478d0"    # both fire + flood
C_TEXT        = "#c9d1d9"    # text color
C_TEXT_DIM   = "#8b949e"    # dimmed text
C_ACCENT     = "#00e5ff"    # accent / button
C_BTN_HOVER  = "#00b8d4"    # button hover

# ── Device Selection ─────────────────────────────────────────────────────────
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

def load_ai_assets():
    """Load the trained model and fitted scaler."""
    model = DisasterRoutePredictor(input_dim=5)
    model.load_state_dict(torch.load(WEIGHTS_PATH, map_location=DEVICE, weights_only=True))
    model.to(DEVICE)
    model.eval()

    with open(SCALER_PATH, "rb") as f:
        scaler = pickle.load(f)

    return model, scaler

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3: Application Class
# ══════════════════════════════════════════════════════════════════════════════

class ResQnetDashboard:
    """Main application controller."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("ResQnet - AI Disaster Rescue Navigation")
        self.root.configure(bg=C_BG)
        self.root.resizable(True, True)

        # ── State ────────────────────────────────────────────────────────
        self.start_node    = None
        self.end_node      = None
        self.selected_edges = set()    # set of (u, v) tuples for multi-select
        self.path_lines    = []        # canvas IDs for path overlay

        # ── Load AI ──────────────────────────────────────────────────────
        self.model, self.scaler = load_ai_assets()

        # ── Build Graph ──────────────────────────────────────────────────
        self._build_graph()

        # ── Build UI ─────────────────────────────────────────────────────
        self._build_fonts()
        self._build_layout()
        self._draw_grid()

    # ──────────────────────────────────────────────────────────────────────
    # Graph Construction
    # ──────────────────────────────────────────────────────────────────────
    def _build_graph(self):
        """Create a 15x15 grid graph with default edge attributes."""
        self.G = nx.grid_2d_graph(GRID_ROWS, GRID_COLS)
        # Attach default hazard data to every edge
        for u, v in self.G.edges():
            self.G[u][v]["fire_risk"]         = 0.0
            self.G[u][v]["flood_level"]       = 0.0
            self.G[u][v]["structural_damage"] = 0.0
            self.G[u][v]["survivor_urgency"]  = 0.0
            self.G[u][v]["distance_km"]       = 1.0
            self.G[u][v]["ai_cost"]           = 1.0   # will be overwritten

    # ──────────────────────────────────────────────────────────────────────
    # UI Construction
    # ──────────────────────────────────────────────────────────────────────
    def _build_fonts(self):
        self.font_title  = tkfont.Font(family="Segoe UI", size=14, weight="bold")
        self.font_label  = tkfont.Font(family="Segoe UI", size=10)
        self.font_small  = tkfont.Font(family="Segoe UI", size=9)
        self.font_btn    = tkfont.Font(family="Segoe UI", size=12, weight="bold")
        self.font_status = tkfont.Font(family="Consolas",  size=9)

    def _build_layout(self):
        """Construct left canvas + right control sidebar."""
        # ── Left: Map Canvas ─────────────────────────────────────────────
        canvas_w = CELL_SIZE * (GRID_COLS - 1) + 80
        canvas_h = CELL_SIZE * (GRID_ROWS - 1) + 80

        self.canvas = tk.Canvas(
            self.root, width=canvas_w, height=canvas_h,
            bg=C_BG, highlightthickness=0
        )
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.canvas.bind("<Button-1>", self._on_canvas_click)
        self.canvas.bind("<Control-Button-1>", self._on_canvas_ctrl_click)

        # ── Right: Command Center ────────────────────────────────────────
        sidebar = tk.Frame(self.root, bg=C_PANEL, width=300)
        sidebar.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 10), pady=10)
        sidebar.pack_propagate(False)

        pad = {"padx": 15, "pady": (4, 0)}

        # Title
        tk.Label(sidebar, text="COMMAND CENTER", font=self.font_title,
                 bg=C_PANEL, fg=C_ACCENT).pack(pady=(18, 4))
        ttk.Separator(sidebar).pack(fill=tk.X, padx=15, pady=6)

        # Instructions
        instr = (
            "1. Click a NODE to set Start/End.\n"
            "2. Click an EDGE to select it.\n"
            "3. Ctrl+Click edges for MULTI-SELECT.\n"
            "4. Adjust sliders (applies to all\n"
            "   selected edges at once).\n"
            "5. Press RUN AI ROUTING."
        )
        tk.Label(sidebar, text=instr, font=self.font_small, bg=C_PANEL,
                 fg=C_TEXT_DIM, justify=tk.LEFT, anchor="w").pack(**pad)
        ttk.Separator(sidebar).pack(fill=tk.X, padx=15, pady=8)

        # Selected edge status (shows count + list)
        tk.Label(sidebar, text="SELECTED EDGES", font=self.font_label,
                 bg=C_PANEL, fg=C_TEXT).pack(**pad)
        self.lbl_edge = tk.Label(sidebar, text="None (Ctrl+Click for multi)",
                                 font=self.font_status,
                                 bg=C_BG, fg=C_ACCENT, anchor="w",
                                 relief="flat", padx=8, pady=4,
                                 wraplength=260, justify=tk.LEFT)
        self.lbl_edge.pack(fill=tk.X, padx=15, pady=(2, 2))

        # Deselect All button
        self.btn_deselect = tk.Button(
            sidebar, text="DESELECT ALL EDGES", font=self.font_small,
            bg="#30363d", fg=C_TEXT_DIM, activebackground="#484f58",
            relief="flat", cursor="hand2", command=self._deselect_all_edges
        )
        self.btn_deselect.pack(fill=tk.X, padx=15, pady=(0, 8))

        # ── Sliders ─────────────────────────────────────────────────────
        slider_defs = [
            ("Fire Risk",         "fire_risk",         0, 10,  0.1),
            ("Flood Level",       "flood_level",       0, 10,  0.1),
            ("Structural Damage", "structural_damage", 0, 100, 1.0),
            ("Survivor Urgency",  "survivor_urgency",  0, 10,  0.1),
        ]
        self.sliders = {}
        for label_text, key, lo, hi, res in slider_defs:
            tk.Label(sidebar, text=label_text, font=self.font_small,
                     bg=C_PANEL, fg=C_TEXT).pack(anchor="w", padx=15, pady=(6, 0))
            var = tk.DoubleVar(value=0.0)
            sl = tk.Scale(
                sidebar, from_=lo, to=hi, resolution=res, orient=tk.HORIZONTAL,
                variable=var, bg=C_PANEL, fg=C_TEXT, troughcolor=C_BG,
                highlightthickness=0, sliderrelief="flat", length=250,
                activebackground=C_ACCENT,
                command=lambda val, k=key: self._on_slider_change(k, val)
            )
            sl.pack(padx=15)
            self.sliders[key] = var

        ttk.Separator(sidebar).pack(fill=tk.X, padx=15, pady=10)

        # ── RUN Button ───────────────────────────────────────────────────
        self.btn_run = tk.Button(
            sidebar, text="RUN AI ROUTING", font=self.font_btn,
            bg=C_ACCENT, fg=C_BG, activebackground=C_BTN_HOVER,
            activeforeground=C_BG, relief="flat", cursor="hand2",
            command=self._run_ai_routing, height=2
        )
        self.btn_run.pack(fill=tk.X, padx=15, pady=(4, 8))

        # ── Status / Warning Label ───────────────────────────────────────
        self.lbl_status = tk.Label(
            sidebar, text="Ready.", font=self.font_small,
            bg=C_PANEL, fg=C_TEXT_DIM, wraplength=260, justify=tk.LEFT
        )
        self.lbl_status.pack(fill=tk.X, padx=15, pady=(4, 12))

        # ── Reset Button ────────────────────────────────────────────────
        self.btn_reset = tk.Button(
            sidebar, text="RESET ALL", font=self.font_label,
            bg="#30363d", fg=C_TEXT, activebackground="#484f58",
            relief="flat", cursor="hand2", command=self._reset_all
        )
        self.btn_reset.pack(fill=tk.X, padx=15, pady=(0, 15))

    # ──────────────────────────────────────────────────────────────────────
    # Canvas Drawing
    # ──────────────────────────────────────────────────────────────────────
    def _node_pos(self, node):
        """Return canvas (x, y) for a grid node (row, col)."""
        r, c = node
        return (40 + c * CELL_SIZE, 40 + r * CELL_SIZE)

    def _draw_grid(self):
        """Render all edges and nodes on the canvas."""
        self.canvas.delete("all")
        self.edge_ids = {}   # (u,v) -> canvas line id
        self.node_ids = {}   # node  -> canvas oval id
        self.path_lines = []

        # Draw edges first (underneath nodes)
        for u, v in self.G.edges():
            x1, y1 = self._node_pos(u)
            x2, y2 = self._node_pos(v)
            color = self._edge_color(u, v)
            line_id = self.canvas.create_line(
                x1, y1, x2, y2, fill=color, width=3, tags="edge"
            )
            self.edge_ids[(u, v)] = line_id
            self.edge_ids[(v, u)] = line_id  # bidirectional lookup

        # Draw nodes on top
        for node in self.G.nodes():
            x, y = self._node_pos(node)
            r = NODE_RADIUS
            fill = self._node_color(node)
            oid = self.canvas.create_oval(
                x - r, y - r, x + r, y + r,
                fill=fill, outline="#0d1117", width=2, tags="node"
            )
            self.node_ids[node] = oid

    def _edge_color(self, u, v):
        """Determine edge color based on hazard data."""
        d = self.G[u][v]
        fire  = d.get("fire_risk", 0) > 5
        flood = d.get("flood_level", 0) > 5
        if fire and flood:
            return C_BOTH
        if fire:
            return C_FIRE
        if flood:
            return C_FLOOD
        return C_EDGE_DEF

    def _node_color(self, node):
        if node == self.start_node:
            return C_START
        if node == self.end_node:
            return C_END
        return C_NODE_DEF

    def _refresh_edge_visuals(self, u, v):
        """Redraw a single edge's color without full redraw."""
        line_id = self.edge_ids.get((u, v))
        if line_id:
            is_selected = (u, v) in self.selected_edges or (v, u) in self.selected_edges
            color = C_EDGE_SEL if is_selected else self._edge_color(u, v)
            width = 4 if is_selected else 3
            self.canvas.itemconfigure(line_id, fill=color, width=width)

    def _refresh_node_visuals(self, node):
        oid = self.node_ids.get(node)
        if oid:
            self.canvas.itemconfigure(oid, fill=self._node_color(node))

    # ──────────────────────────────────────────────────────────────────────
    # Hit Detection
    # ──────────────────────────────────────────────────────────────────────
    def _closest_node(self, cx, cy, threshold=14):
        """Return the nearest grid node if within threshold pixels."""
        best, best_d = None, threshold + 1
        for node in self.G.nodes():
            nx_, ny_ = self._node_pos(node)
            d = ((cx - nx_) ** 2 + (cy - ny_) ** 2) ** 0.5
            if d < best_d:
                best, best_d = node, d
        return best if best_d <= threshold else None

    def _closest_edge(self, cx, cy, threshold=10):
        """Return the nearest edge if click is within threshold of its midpoint."""
        best, best_d = None, threshold + 1
        for u, v in self.G.edges():
            x1, y1 = self._node_pos(u)
            x2, y2 = self._node_pos(v)
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            d = ((cx - mx) ** 2 + (cy - my) ** 2) ** 0.5
            if d < best_d:
                best, best_d = (u, v), d
        return best if best_d <= threshold else None

    # ──────────────────────────────────────────────────────────────────────
    # Event Handlers
    # ──────────────────────────────────────────────────────────────────────
    def _on_canvas_click(self, event):
        """Plain click: select single node or replace edge selection."""
        cx, cy = event.x, event.y
        self._clear_path_overlay()

        # Priority 1: Check if a node was clicked
        node = self._closest_node(cx, cy)
        if node is not None:
            self._handle_node_click(node)
            return

        # Priority 2: Check if an edge was clicked (replaces selection)
        edge = self._closest_edge(cx, cy)
        if edge is not None:
            self._handle_edge_click(edge, multi=False)

    def _on_canvas_ctrl_click(self, event):
        """Ctrl+Click: toggle edge in/out of multi-selection."""
        cx, cy = event.x, event.y
        self._clear_path_overlay()

        # Only edges respond to Ctrl+Click (not nodes)
        edge = self._closest_edge(cx, cy)
        if edge is not None:
            self._handle_edge_click(edge, multi=True)

    def _handle_node_click(self, node):
        """Toggle node as Start or End."""
        prev_start = self.start_node
        prev_end   = self.end_node

        if node == self.start_node:
            self.start_node = None
        elif node == self.end_node:
            self.end_node = None
        elif self.start_node is None:
            self.start_node = node
        elif self.end_node is None:
            self.end_node = node
        else:
            # Both set: replace end
            self.end_node = node

        # Refresh changed nodes
        for n in {prev_start, prev_end, self.start_node, self.end_node}:
            if n is not None:
                self._refresh_node_visuals(n)

        s = f"Start: {self.start_node}  End: {self.end_node}"
        self.lbl_status.config(text=s, fg=C_TEXT_DIM)

    def _handle_edge_click(self, edge, multi=False):
        """Select/toggle edge(s). multi=True for Ctrl+Click additive mode."""
        u, v = edge

        # Normalize edge key (NetworkX stores undirected edges one way)
        if not self.G.has_edge(u, v):
            u, v = v, u
        key = (u, v)

        if multi:
            # ── Ctrl+Click: toggle this edge in the selection set ─────
            if key in self.selected_edges:
                self.selected_edges.discard(key)
            else:
                self.selected_edges.add(key)
        else:
            # ── Plain click: clear previous selection, select only this ─
            prev_edges = set(self.selected_edges)
            self.selected_edges = {key}
            # De-highlight all previously selected edges
            for pu, pv in prev_edges:
                self._refresh_edge_visuals(pu, pv)

        # Refresh visual for the clicked edge
        self._refresh_edge_visuals(u, v)

        # ── Update sliders to reflect the clicked edge's data ────────
        d = self.G[u][v]
        self.sliders["fire_risk"].set(d["fire_risk"])
        self.sliders["flood_level"].set(d["flood_level"])
        self.sliders["structural_damage"].set(d["structural_damage"])
        self.sliders["survivor_urgency"].set(d["survivor_urgency"])

        # ── Update label with selection count ─────────────────────────
        self._update_edge_label()

    def _on_slider_change(self, key, val):
        """Write slider value to ALL selected edges simultaneously."""
        if not self.selected_edges:
            return
        fval = float(val)
        for u, v in self.selected_edges:
            self.G[u][v][key] = fval
            # Update visual tint if fire/flood changed
            if key in ("fire_risk", "flood_level"):
                self._refresh_edge_visuals(u, v)

    def _update_edge_label(self):
        """Refresh the sidebar label showing selected edge(s)."""
        n = len(self.selected_edges)
        if n == 0:
            self.lbl_edge.config(text="None (Ctrl+Click for multi)")
        elif n == 1:
            (u, v), = self.selected_edges
            self.lbl_edge.config(text=f"1 edge: ({u[0]},{u[1]})<->({v[0]},{v[1]})")
        elif n <= 5:
            lines = [f"({u[0]},{u[1]})<->({v[0]},{v[1]})" for u, v in self.selected_edges]
            self.lbl_edge.config(text=f"{n} edges: " + ", ".join(lines))
        else:
            self.lbl_edge.config(text=f"{n} edges selected")

    def _deselect_all_edges(self):
        """Clear the entire edge selection."""
        prev = set(self.selected_edges)
        self.selected_edges.clear()
        for u, v in prev:
            self._refresh_edge_visuals(u, v)
        for key, var in self.sliders.items():
            var.set(0.0)
        self._update_edge_label()
        self.lbl_status.config(text="All edges deselected.", fg=C_TEXT_DIM)

    # ──────────────────────────────────────────────────────────────────────
    # AI Routing
    # ──────────────────────────────────────────────────────────────────────
    def _run_ai_routing(self):
        """Score every edge with the AI model, then run Dijkstra."""
        if self.start_node is None or self.end_node is None:
            self.lbl_status.config(text="Set both Start and End nodes first!", fg=C_FIRE)
            return

        self._clear_path_overlay()
        self.lbl_status.config(text="Running AI inference on all edges...", fg=C_ACCENT)
        self.root.update_idletasks()

        # ── Batch inference on all edges ─────────────────────────────────
        edges_list = list(self.G.edges())
        features = []
        for u, v in edges_list:
            d = self.G[u][v]
            features.append([
                d["fire_risk"],
                d["flood_level"],
                d["structural_damage"],
                d["survivor_urgency"],
                d["distance_km"],
            ])

        features_np = np.array(features, dtype=np.float32)
        features_scaled = self.scaler.transform(features_np).astype(np.float32)
        tensor_in = torch.tensor(features_scaled).to(DEVICE)

        self.model.eval()
        with torch.no_grad():
            costs = self.model(tensor_in).cpu().numpy().flatten()

        # Write AI costs back and determine which edges are IMPASSABLE.
        # An edge is blocked if any of these hard-block conditions are met:
        #   - Fire Risk >= 8      (inferno — no team can pass)
        #   - Structural Damage >= 90  (near-total collapse)
        #   - AI predicted cost > 100  (model deems it extreme danger)
        FIRE_BLOCK      = 8.0
        DAMAGE_BLOCK    = 90.0
        AI_COST_BLOCK   = 100.0

        blocked_edges = set()

        for idx, (u, v) in enumerate(edges_list):
            cost = float(max(costs[idx], 0.01))
            self.G[u][v]["ai_cost"] = cost

            d = self.G[u][v]
            if (d["fire_risk"] >= FIRE_BLOCK or
                    d["structural_damage"] >= DAMAGE_BLOCK or
                    cost >= AI_COST_BLOCK):
                blocked_edges.add((u, v))

        # ── Build a filtered graph excluding blocked edges ────────────────
        G_safe = self.G.copy()
        G_safe.remove_edges_from(blocked_edges)

        # ── Draw red X markers on blocked edges ──────────────────────────
        for u, v in blocked_edges:
            mx = (self._node_pos(u)[0] + self._node_pos(v)[0]) / 2
            my = (self._node_pos(u)[1] + self._node_pos(v)[1]) / 2
            s = 6  # half-size of the X marker
            self.canvas.create_line(mx-s, my-s, mx+s, my+s,
                                    fill=C_END, width=2, tags="path")
            self.canvas.create_line(mx-s, my+s, mx+s, my-s,
                                    fill=C_END, width=2, tags="path")

        # ── Dijkstra on the safe sub-graph ───────────────────────────────
        try:
            path = nx.dijkstra_path(
                G_safe, self.start_node, self.end_node, weight="ai_cost"
            )
            total_cost = nx.dijkstra_path_length(
                G_safe, self.start_node, self.end_node, weight="ai_cost"
            )
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            blk = len(blocked_edges)
            self.lbl_status.config(
                text=(f"NO POSSIBLE ROUTE!  {blk} road(s) blocked by "
                      f"extreme hazards. All paths to the target are "
                      f"impassable. Reduce fire/damage or find alternate nodes."),
                fg=C_END
            )
            return

        # ── Draw path overlay ────────────────────────────────────────────
        for i in range(len(path) - 1):
            x1, y1 = self._node_pos(path[i])
            x2, y2 = self._node_pos(path[i + 1])
            # Glow layer (wider, semi-transparent)
            glow = self.canvas.create_line(
                x1, y1, x2, y2, fill="#004d5e", width=12, tags="path"
            )
            # Core neon line
            core = self.canvas.create_line(
                x1, y1, x2, y2, fill=C_PATH, width=5, tags="path"
            )
            self.path_lines.extend([glow, core])

        # Redraw start/end nodes on top of path
        for node in [self.start_node, self.end_node]:
            x, y = self._node_pos(node)
            r = NODE_RADIUS + 2
            oid = self.canvas.create_oval(
                x - r, y - r, x + r, y + r,
                fill=self._node_color(node), outline=C_PATH, width=2, tags="path"
            )
            self.path_lines.append(oid)

        hops = len(path) - 1
        blk = len(blocked_edges)
        status = f"Route found!  {hops} hops | Cost: {total_cost:.2f}"
        if blk > 0:
            status += f" | {blk} road(s) blocked"
        self.lbl_status.config(text=status, fg=C_START)

    def _clear_path_overlay(self):
        """Remove previous path drawing."""
        self.canvas.delete("path")
        self.path_lines = []

    def _reset_all(self):
        """Reset all state to defaults."""
        self.start_node = None
        self.end_node = None
        self.selected_edges = set()
        self._build_graph()
        for key, var in self.sliders.items():
            var.set(0.0)
        self.lbl_edge.config(text="None (Ctrl+Click for multi)")
        self.lbl_status.config(text="Reset complete.", fg=C_TEXT_DIM)
        self._draw_grid()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4: Entry Point
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    root = tk.Tk()
    root.geometry("1200x820")
    root.minsize(1000, 700)
    app = ResQnetDashboard(root)
    root.mainloop()
