"""
================================================================================
 ResQnet — BLE RSSI Localization Model
================================================================================
MLP regressor that maps relay coordinates + RSSI readings to survivor (x, y).
"""

import torch
import torch.nn as nn


class SurvivorLocatorMLP(nn.Module):
    def __init__(self, input_dim: int = 12, dropout: float = 0.2):
        super().__init__()
        self.network = nn.Sequential(
            nn.Linear(input_dim, 128),
            nn.ReLU(),
            nn.BatchNorm1d(128),
            nn.Dropout(p=dropout),
            nn.Linear(128, 256),
            nn.ReLU(),
            nn.BatchNorm1d(256),
            nn.Dropout(p=dropout),
            nn.Linear(256, 128),
            nn.ReLU(),
            nn.BatchNorm1d(128),
            nn.Dropout(p=dropout),
            nn.Linear(128, 2),
        )
        self._init_weights()

    def _init_weights(self) -> None:
        for module in self.modules():
            if isinstance(module, nn.Linear):
                nn.init.kaiming_normal_(module.weight, nonlinearity="relu")
                if module.bias is not None:
                    nn.init.zeros_(module.bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.network(x)
