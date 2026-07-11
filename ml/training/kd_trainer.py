"""Knowledge Distillation Trainer — ST-MMT(Teacher) → TinyTransformer(Student).

KD Loss = α × CE(student, labels) + (1-α) × KL(student_soft || teacher_soft) / T²
"""
import json
from pathlib import Path

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, random_split

from ml.training.eval import evaluate_model


class KDTrainer:
    """Knowledge Distillation 학습기.

    Args:
        teacher:     ST-MMT (frozen)
        student:     TinyTransformer (학습 대상)
        dataset:     학습 데이터셋
        save_dir:    체크포인트 저장 경로
        device:      'cpu' | 'cuda'
        temperature: KD softmax 온도 (기본 4)
        alpha:       Hard label 손실 비중 (기본 0.3)
        lr:          학습률
        batch_size:  배치 크기
        epochs:      최대 에폭
    """

    def __init__(
        self,
        teacher: nn.Module,
        student: nn.Module,
        dataset: torch.utils.data.Dataset,
        save_dir: str = "checkpoints/kd",
        device: str = "cpu",
        temperature: float = 4.0,
        alpha: float = 0.3,
        lr: float = 1e-3,
        batch_size: int = 16,
        epochs: int = 20,
        val_ratio: float = 0.2,
    ):
        self.device = torch.device(device)
        self.temperature = temperature
        self.alpha = alpha
        self.epochs = epochs
        self.save_dir = Path(save_dir)
        self.save_dir.mkdir(parents=True, exist_ok=True)

        self.teacher = teacher.to(self.device).eval()
        # Teacher 파라미터 동결
        for p in self.teacher.parameters():
            p.requires_grad_(False)

        self.student = student.to(self.device)

        n_val = max(1, int(len(dataset) * val_ratio))
        n_train = len(dataset) - n_val
        train_ds, val_ds = random_split(dataset, [n_train, n_val])
        self.train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)
        self.val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False)

        self.optimizer = torch.optim.AdamW(student.parameters(), lr=lr, weight_decay=1e-4)
        self.scheduler = torch.optim.lr_scheduler.OneCycleLR(
            self.optimizer, max_lr=lr,
            steps_per_epoch=len(self.train_loader), epochs=epochs,
        )
        self.ce_loss = nn.CrossEntropyLoss(label_smoothing=0.05)
        self.history: list[dict] = []

    def _kd_loss(
        self,
        student_logits: torch.Tensor,
        teacher_logits: torch.Tensor,
        labels: torch.Tensor,
    ) -> dict[str, torch.Tensor]:
        T = self.temperature
        # Hard label loss
        ce = self.ce_loss(student_logits, labels)
        # Soft label loss (KL divergence)
        s_soft = F.log_softmax(student_logits / T, dim=-1)
        t_soft = F.softmax(teacher_logits / T, dim=-1)
        kl = F.kl_div(s_soft, t_soft, reduction="batchmean") * (T ** 2)
        total = self.alpha * ce + (1 - self.alpha) * kl
        return {"total": total, "ce": ce, "kl": kl}

    def _teacher_logits(self, x_cube: torch.Tensor) -> torch.Tensor:
        """ST-MMT teacher에서 픽셀별 logit을 뽑아 전역 평균으로 압축."""
        with torch.no_grad():
            out = self.teacher(x_cube)
            # (B, n_stages, H, W) → (B, n_stages)
            return out["last_logits"].mean(dim=[-2, -1])

    def _train_step(self, sensor_batch, cube_batch, labels):
        self.student.train()
        self.optimizer.zero_grad()

        teacher_logits = self._teacher_logits(cube_batch)
        student_out = self.student(sensor_batch)
        student_logits = student_out["stage_logits"]

        losses = self._kd_loss(student_logits, teacher_logits, labels)
        losses["total"].backward()
        nn.utils.clip_grad_norm_(self.student.parameters(), 1.0)
        self.optimizer.step()
        self.scheduler.step()
        return losses

    def fit(
        self,
        sensor_loader: DataLoader,
        cube_loader: DataLoader,
        n_stages: int = 5,
    ) -> dict:
        """두 DataLoader를 병렬 순회하며 KD 학습.

        sensor_loader: TinyTransformer 입력 (B, T, C)
        cube_loader:   ST-MMT 입력      (B, T, C, H, W)
        """
        best_val = float("inf")
        best_path = self.save_dir / "student_best.pt"

        for epoch in range(1, self.epochs + 1):
            total_ce = total_kl = 0.0
            n = 0
            for (s_batch, labels), (c_batch, _) in zip(sensor_loader, cube_loader):
                s_batch = s_batch.to(self.device)
                c_batch = c_batch.to(self.device)
                labels = labels.to(self.device)
                losses = self._train_step(s_batch, c_batch, labels)
                total_ce += losses["ce"].item()
                total_kl += losses["kl"].item()
                n += 1

            val_loss = self._val_loss(sensor_loader)
            row = {
                "epoch": epoch,
                "ce": round(total_ce / n, 4),
                "kl": round(total_kl / n, 4),
                "val_loss": round(val_loss, 4),
            }
            self.history.append(row)
            print(f"  KD Epoch {epoch:3d} | CE={row['ce']} KL={row['kl']} val={row['val_loss']}")

            if val_loss < best_val:
                best_val = val_loss
                torch.save(self.student.state_dict(), best_path)

        self.student.load_state_dict(torch.load(best_path, weights_only=True))
        with open(self.save_dir / "kd_history.json", "w") as f:
            json.dump(self.history, f, indent=2)

        return {"history": self.history, "best_path": str(best_path)}

    def _val_loss(self, loader: DataLoader) -> float:
        self.student.eval()
        total = 0.0
        n = 0
        with torch.no_grad():
            for x, y in loader:
                x = x.to(self.device)
                y = y.to(self.device)
                out = self.student(x)
                loss = self.ce_loss(out["stage_logits"], y.view(-1))
                total += loss.item()
                n += 1
        return total / max(n, 1)
