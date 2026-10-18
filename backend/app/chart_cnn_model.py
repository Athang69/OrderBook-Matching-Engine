"""The CNN architecture: 3 conv blocks (32, 64, 128), used by both training and serving."""
import torch
import torch.nn as nn


class ChartCNN(nn.Module):
    """Small CNN for 64x60 candlestick chart images -> P(up in 5 days).

    Architecture from Jiang, Kelly & Xiu (2023), scaled down for 64x60 input:
    3 conv blocks (32, 64, 128 channels), kernel 5x3, BatchNorm, LeakyReLU, MaxPool(2,1), dropout.
    """

    def __init__(self):
        super().__init__()
        self.features = nn.Sequential(
            # Block 1: 1 -> 32 channels
            nn.Conv2d(1, 32, kernel_size=(5, 3), padding=(2, 1)),
            nn.BatchNorm2d(32),
            nn.LeakyReLU(0.1),
            nn.MaxPool2d(kernel_size=(2, 1)),
            nn.Dropout2d(0.25),
            # Block 2: 32 -> 64 channels
            nn.Conv2d(32, 64, kernel_size=(5, 3), padding=(2, 1)),
            nn.BatchNorm2d(64),
            nn.LeakyReLU(0.1),
            nn.MaxPool2d(kernel_size=(2, 1)),
            nn.Dropout2d(0.25),
            # Block 3: 64 -> 128 channels
            nn.Conv2d(64, 128, kernel_size=(5, 3), padding=(2, 1)),
            nn.BatchNorm2d(128),
            nn.LeakyReLU(0.1),
            nn.MaxPool2d(kernel_size=(2, 1)),
            nn.Dropout2d(0.25),
        )
        # After 3x MaxPool(2,1): 64/8=8 height, 60 width -> 8*60*128 = 61440
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Linear(128 * 8 * 60, 64),
            nn.LeakyReLU(0.1),
            nn.Dropout(0.5),
            nn.Linear(64, 2),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.classifier(self.features(x))
