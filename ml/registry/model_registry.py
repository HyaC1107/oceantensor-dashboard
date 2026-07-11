"""Model Registry — TinyTransformer 버전 관리 & 로드.

파일 기반 레지스트리: checkpoints/registry.json에 메타데이터 저장.
운영 중 무중단 모델 교체(Hot-swap) 지원.
"""
from __future__ import annotations

import json
import hashlib
import shutil
from datetime import datetime, timezone
from pathlib import Path

import torch
import torch.nn as nn


REGISTRY_PATH = Path("checkpoints/registry.json")
MODELS_DIR = Path("checkpoints/models")


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


class ModelRegistry:
    """모델 버전 등록·조회·로드·Hot-swap 관리.

    Usage:
        registry = ModelRegistry()
        registry.register("v1.0", "checkpoints/best_model.pt", metrics={"f1": 0.92})
        model = registry.load("v1.0", TinyTransformer())
        registry.set_active("v1.0")
    """

    def __init__(self, registry_path: str = str(REGISTRY_PATH)):
        self.registry_path = Path(registry_path)
        self.models_dir = self.registry_path.parent / "models"
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self._data: dict = self._load_registry()

    def _load_registry(self) -> dict:
        if self.registry_path.exists():
            with open(self.registry_path, encoding="utf-8") as f:
                return json.load(f)
        return {"active": None, "versions": {}}

    def _save_registry(self):
        with open(self.registry_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def register(
        self,
        version: str,
        checkpoint_path: str,
        metrics: dict | None = None,
        description: str = "",
        promote_active: bool = False,
    ) -> dict:
        """새 버전 등록.

        Args:
            version:         버전 태그 (예: "v1.0", "v1.1-finetune")
            checkpoint_path: .pt 파일 경로
            metrics:         평가 지표 dict (f1, auc, latency_ms 등)
            description:     변경 내용 설명
            promote_active:  True면 등록 즉시 active 버전으로 설정
        """
        src = Path(checkpoint_path)
        if not src.exists():
            raise FileNotFoundError(f"체크포인트 없음: {checkpoint_path}")

        # 레지스트리 저장소로 복사
        dest = self.models_dir / f"{version}.pt"
        shutil.copy2(src, dest)

        entry = {
            "version": version,
            "checkpoint": str(dest),
            "sha256": _sha256(str(dest)),
            "registered_at": datetime.now(timezone.utc).isoformat(),
            "metrics": metrics or {},
            "description": description,
        }
        self._data["versions"][version] = entry

        if promote_active or self._data["active"] is None:
            self._data["active"] = version

        self._save_registry()
        print(f"  [Registry] v{version} 등록 완료 | active={self._data['active']}")
        return entry

    def load(
        self,
        version: str | None,
        model: nn.Module,
        device: str = "cpu",
        strict: bool = True,
    ) -> nn.Module:
        """지정 버전 가중치를 모델에 로드.

        version=None이면 active 버전 사용.
        """
        ver = version or self._data.get("active")
        if not ver:
            raise ValueError("활성 버전이 없습니다. register()를 먼저 실행하세요.")

        entry = self._data["versions"].get(ver)
        if not entry:
            raise KeyError(f"버전 없음: {ver}")

        ckpt_path = entry["checkpoint"]
        state = torch.load(ckpt_path, map_location=device, weights_only=True)
        model.load_state_dict(state, strict=strict)
        model.to(device)
        model.eval()
        print(f"  [Registry] {ver} 로드 완료 ({ckpt_path})")
        return model

    def set_active(self, version: str):
        """Active 버전 변경 (Hot-swap)."""
        if version not in self._data["versions"]:
            raise KeyError(f"버전 없음: {version}")
        old = self._data["active"]
        self._data["active"] = version
        self._save_registry()
        print(f"  [Registry] Active: {old} → {version}")

    def list_versions(self) -> list[dict]:
        """등록된 모든 버전 정보 반환."""
        return [
            {**v, "is_active": v["version"] == self._data["active"]}
            for v in self._data["versions"].values()
        ]

    def get_active_version(self) -> str | None:
        return self._data.get("active")

    def delete(self, version: str, remove_file: bool = False):
        """버전 삭제 (active 버전은 삭제 불가)."""
        if version == self._data["active"]:
            raise ValueError("Active 버전은 삭제할 수 없습니다.")
        entry = self._data["versions"].pop(version, None)
        if entry and remove_file:
            Path(entry["checkpoint"]).unlink(missing_ok=True)
        self._save_registry()
        print(f"  [Registry] {version} 삭제됨")

    def compare(self, v1: str, v2: str) -> dict:
        """두 버전의 메트릭 비교."""
        e1 = self._data["versions"].get(v1, {})
        e2 = self._data["versions"].get(v2, {})
        m1 = e1.get("metrics", {})
        m2 = e2.get("metrics", {})
        diff = {}
        for k in set(m1) | set(m2):
            val1 = m1.get(k, "N/A")
            val2 = m2.get(k, "N/A")
            diff[k] = {"v1": val1, "v2": val2}
            if isinstance(val1, (int, float)) and isinstance(val2, (int, float)):
                diff[k]["delta"] = round(val2 - val1, 4)
        return diff
