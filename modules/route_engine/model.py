"""
================================================================================
 ResQnet — Block 2: PyTorch MLP Model Definition
================================================================================
 Author : ResQnet AI/ML Engineering Team
 Purpose: Defines the DisasterRoutePredictor — a Multi‑Layer Perceptron (MLP)
          neural network for tabular regression.  Given 5 disaster‑condition
          inputs for a road segment, the model outputs a single scalar:
          the "Dynamic Traversal Penalty Score" (cost).

 Architecture
 ────────────
   Input(5) ─→ Linear(128) ─→ ReLU ─→ BatchNorm ─→ Dropout(0.3)
            ─→ Linear(64)  ─→ ReLU ─→ BatchNorm ─→ Dropout(0.2)
            ─→ Linear(32)  ─→ ReLU ─→ BatchNorm
            ─→ Linear(1)   ─→ ReLU (output ≥ 0)

 Design Decisions
 ────────────────
 • BatchNorm after activation stabilises training on noisy disaster data.
 • Dropout rates decay deeper into the network — heavier regularisation in
   early (wider) layers prevents co‑adaptation of many neurons; lighter
   regularisation in narrow layers preserves capacity.
 • Final ReLU guarantees non‑negative traversal cost (physical constraint).
================================================================================
"""

import torch
import torch.nn as nn


class DisasterRoutePredictor(nn.Module):
    """
    Multi‑Layer Perceptron that maps 5 road‑segment disaster features
    to a scalar traversal penalty cost.

    Parameters
    ----------
    input_dim : int, default 5
        Number of input features (fire_risk, flood_level, structural_damage,
        survivor_urgency, distance_km).
    """

    def __init__(self, input_dim: int = 5):
        super(DisasterRoutePredictor, self).__init__()

        # ── Layer Stack ──────────────────────────────────────────────────
        self.network = nn.Sequential(
            # --- Hidden Layer 1: 5 → 128 ---
            nn.Linear(input_dim, 128),
            nn.ReLU(),
            nn.BatchNorm1d(128),
            nn.Dropout(p=0.3),

            # --- Hidden Layer 2: 128 → 64 ---
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.BatchNorm1d(64),
            nn.Dropout(p=0.2),

            # --- Hidden Layer 3: 64 → 32 ---
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.BatchNorm1d(32),

            # --- Output Layer: 32 → 1 ---
            nn.Linear(32, 1),
            nn.ReLU(),          # Enforce non‑negative cost output
        )

        # ── Weight Initialisation (Kaiming / He) ────────────────────────
        # Kaiming init is optimal for ReLU activations — prevents vanishing
        # or exploding gradients in deep networks.
        self._init_weights()

    def _init_weights(self):
        """Apply Kaiming Normal initialisation to all Linear layers."""
        for module in self.modules():
            if isinstance(module, nn.Linear):
                nn.init.kaiming_normal_(module.weight, nonlinearity="relu")
                if module.bias is not None:
                    nn.init.zeros_(module.bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Forward pass.

        Parameters
        ----------
        x : torch.Tensor, shape (batch_size, 5)
            Batch of road‑segment feature vectors.

        Returns
        -------
        torch.Tensor, shape (batch_size, 1)
            Predicted traversal penalty cost for each segment.
        """
        return self.network(x)


# ──────────────────────────────────────────────────────────────────────────────
# Quick sanity check when run standalone
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    model = DisasterRoutePredictor(input_dim=5)
    print(model)

    # Count trainable parameters
    total_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"\nTrainable parameters: {total_params:,}")

    # Dummy forward pass
    dummy_input = torch.randn(8, 5)       # batch of 8 road segments
    output = model(dummy_input)
    print(f"Input shape : {dummy_input.shape}")
    print(f"Output shape: {output.shape}")
    print(f"Sample output: {output.detach().numpy().flatten()[:4]}")
