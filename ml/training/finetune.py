"""실데이터 파인튜닝 — 공공API 수집 데이터로 TinyTransformer 도메인 적응."""
import json
from pathlib import Path

import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader


class SensorSequenceDataset(Dataset):
    """DB에서 추출한 센서 시계열 피처 + 레이블 Dataset.

    Args:
        features: (N, T, C) float32 — N개 시퀀스
        labels:   (N,)      int64   — 황백화 단계 0~4
    """

    def __init__(self, features: torch.Tensor, labels: torch.Tensor):
        assert len(features) == len(labels)
        self.features = features.float()
        self.labels = labels.long()

    def __len__(self):
        return len(self.features)

    def __getitem__(self, idx):
        return self.features[idx], self.labels[idx]


def finetune(
    model: nn.Module,
    dataset: Dataset,
    pretrained_path: str,
    save_path: str = "checkpoints/finetuned.pt",
    device: str = "cpu",
    lr: float = 5e-5,
    epochs: int = 10,
    batch_size: int = 32,
    freeze_backbone: bool = True,
) -> dict:
    """사전학습 가중치를 로드하고 도메인 데이터로 파인튜닝.

    Args:
        freeze_backbone: True면 embedding + transformer block을 동결하고
                         output head만 학습 (data-efficient fine-tuning)
    """
    dev = torch.device(device)
    state = torch.load(pretrained_path, map_location=dev, weights_only=True)
    model.load_state_dict(state, strict=False)
    model.to(dev)

    if freeze_backbone:
        # sensor_embed, token_scorer, blocks 동결 → head만 학습
        frozen_names = {"sensor_embed", "token_scorer", "blocks", "patch_embed", "cross_modal"}
        for name, param in model.named_parameters():
            if any(name.startswith(fn) for fn in frozen_names):
                param.requires_grad_(False)
        print("  Backbone frozen. Head-only fine-tuning.")

    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"  학습 파라미터: {trainable:,}")

    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True)
    optimizer = torch.optim.AdamW(
        filter(lambda p: p.requires_grad, model.parameters()), lr=lr
    )
    criterion = nn.CrossEntropyLoss(label_smoothing=0.05)
    history = []

    model.train()
    for epoch in range(1, epochs + 1):
        total_loss = 0.0
        for x, y in loader:
            x, y = x.to(dev), y.to(dev)
            optimizer.zero_grad()
            out = model(x)
            loss = criterion(out["stage_logits"], y)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            total_loss += loss.item()
        avg = total_loss / len(loader)
        history.append({"epoch": epoch, "loss": round(avg, 4)})
        print(f"  Finetune Epoch {epoch:2d}/{epochs} | loss={avg:.4f}")

    torch.save(model.state_dict(), save_path)
    with open(Path(save_path).with_suffix(".json"), "w") as f:
        json.dump(history, f, indent=2)

    return {"history": history, "save_path": save_path}
