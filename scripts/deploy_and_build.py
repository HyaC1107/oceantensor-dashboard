"""H100 코드 동기화 + 빌드 실행.

로컬 ml/ + scripts/ 전체 .py 파일을 H100에 업로드하고 hash 검증 후 빌드.
H100 빌드는 반드시 이 스크립트로만 실행할 것 — 코드 불일치 방지.

사용:
    uv run python scripts/deploy_and_build.py --version v5
    uv run python scripts/deploy_and_build.py --version v5 --dry-run    # 업로드 목록만 확인
    uv run python scripts/deploy_and_build.py --version v5 --deploy-only # 배포만, 빌드 생략
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

# 배포 대상 디렉토리 — 하위 .py 파일 전체 자동 탐색
DEPLOY_DIRS  = ["scripts", "ml"]
DEPLOY_EXTRA = ["pyproject.toml"]   # 개별 파일
EXCLUDE_DIRS = {"__pycache__", ".venv", ".git", "node_modules"}


_CHUNK = 32 * 1024 * 1024  # 32MB — 대용량 파일 sftp 안정성


def _sftp_put_chunked(sftp, local: Path, remote: str) -> None:
    """큰 파일을 32MB 청크로 쪼개 업로드 — sftp.put은 대용량에서 소켓 끊김 발생."""
    with open(local, "rb") as src, sftp.open(remote, "wb") as dst:
        while True:
            data = src.read(_CHUNK)
            if not data:
                break
            dst.write(data)


def _collect_files() -> list[tuple[Path, str]]:
    """로컬 파일 → (local_path, relative_str) 목록."""
    result = []
    for d in DEPLOY_DIRS:
        for p in (ROOT / d).rglob("*.py"):
            if any(ex in p.parts for ex in EXCLUDE_DIRS):
                continue
            result.append((p, str(p.relative_to(ROOT))))
    for extra in DEPLOY_EXTRA:
        p = ROOT / extra
        if p.exists():
            result.append((p, extra))
    return sorted(result, key=lambda x: x[1])


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description="H100 코드 동기화 + 빌드")
    p.add_argument("--version",        type=str, default="v6",                    help="큐브 버전 태그")
    p.add_argument("--checkpoint-dir", type=str, default="output/cube_v3_parquet", help="H100 parquet 경로")
    p.add_argument("--start-date",     type=str, default="2021-11-01")
    p.add_argument("--end-date",       type=str, default="2026-05-26")
    p.add_argument("--grid-h",         type=int, default=512, help="격자 H (기본 512)")
    p.add_argument("--grid-w",         type=int, default=512, help="격자 W (기본 512)")
    p.add_argument("--output-dir",     type=str, default="output", help="H100 Zarr 저장 상위 경로")
    p.add_argument("--dry-run",          action="store_true", help="업로드 목록만 출력, 실제 전송 없음")
    p.add_argument("--deploy-only",      action="store_true", help="배포만 수행, 빌드 생략")
    p.add_argument("--upload-checkpoints", type=str, default=None,
                   help="로컬 parquet 폴더 경로 — H100 checkpoint-dir로 함께 업로드")
    args = p.parse_args()

    HOST     = os.getenv("H100_HOST",       "123.41.22.216")
    USER     = os.getenv("H100_USER",       "tta")
    PASSWORD = os.getenv("H100_PASSWORD",   "")
    REMOTE   = os.getenv("H100_REMOTE_DIR", "/home/tta/cheolyoung")

    if not PASSWORD:
        print("❌ H100_PASSWORD 없음 — .env 확인")
        sys.exit(1)

    files = _collect_files()

    print("=" * 60)
    print(f"H100 배포 + 빌드 — cube_{args.version} ({args.grid_h}×{args.grid_w})")
    print(f"  서버      : {USER}@{HOST}")
    print(f"  원격 경로 : {REMOTE}")
    print(f"  배포 파일 : {len(files)}개")
    print(f"  격자 크기 : {args.grid_h} × {args.grid_w}")
    print("=" * 60)

    print(f"\n[1/3] 배포 대상 파일:")
    for local, rel in files:
        print(f"  {rel}  [{_md5(local)[:8]}]")

    if args.dry_run:
        print("\n--dry-run: 실제 전송하지 않음")
        return

    # ── SSH 연결 ──────────────────────────────────────────────────
    import paramiko

    def _new_ssh():
        """SSH + SFTP 새 연결 반환. parquet 업로드 전 재연결에도 사용."""
        c = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        c.connect(HOST, username=USER, password=PASSWORD)
        c.get_transport().set_keepalive(30)
        s = c.open_sftp()
        s.get_channel().settimeout(None)  # 타임아웃 없음 — 대용량 파일 대응
        return c, s

    print(f"\n[2/3] H100 연결 중...")
    ssh, sftp = _new_ssh()

    # 원격 디렉토리 사전 생성
    remote_dirs: set[str] = set()
    for _, rel in files:
        rd = REMOTE + "/" + "/".join(rel.split("/")[:-1])
        remote_dirs.add(rd)
    for rd in sorted(remote_dirs):
        if rd.endswith("/"):
            continue
        ssh.exec_command(f"mkdir -p {rd}")
    time.sleep(0.5)

    # 업로드 + hash 검증
    print("파일 업로드 + 검증 중...")
    fail_count = 0
    for local, rel in files:
        remote_path = f"{REMOTE}/{rel}"
        sftp.put(str(local), remote_path)

        _, stdout, _ = ssh.exec_command(f"md5sum {remote_path} 2>/dev/null")
        out = stdout.read().decode().strip()
        remote_hash = out.split()[0] if out else ""
        local_hash  = _md5(local)

        if remote_hash == local_hash:
            print(f"  ✅ {rel}  [{local_hash[:8]}]")
        else:
            print(f"  ❌ {rel}  hash 불일치! local={local_hash[:8]} remote={remote_hash[:8]}")
            fail_count += 1

    sftp.close()

    if fail_count:
        print(f"\n❌ {fail_count}개 파일 검증 실패 — 빌드 중단")
        ssh.close()
        sys.exit(1)

    print(f"\n✅ 전체 {len(files)}개 동기화 완료")

    # ── parquet 업로드 전 SSH 완전 재연결 (코드 업로드 중 세션 끊김 대응) ──
    sftp.close()
    ssh.close()
    ssh, sftp = _new_ssh()

    # ── parquet 업로드 (--upload-checkpoints 지정 시) ────────────────────
    if args.upload_checkpoints:
        ckpt_local = Path(args.upload_checkpoints)
        parquets = sorted(ckpt_local.glob("*.parquet"))
        if parquets:
            remote_ckpt = f"{REMOTE}/{args.checkpoint_dir}"
            ssh.exec_command(f"mkdir -p {remote_ckpt}")
            time.sleep(0.3)
            print(f"\n[checkpoints] parquet {len(parquets)}개 → {remote_ckpt}/")
            for pq in parquets:
                remote_pq = f"{remote_ckpt}/{pq.name}"
                size_mb = pq.stat().st_size / 1024 / 1024
                print(f"  → {pq.name} ({size_mb:.0f}MB) ...", end="", flush=True)
                _sftp_put_chunked(sftp, pq, remote_pq)
                print(f" ✅")
        else:
            print(f"⚠️ --upload-checkpoints: {ckpt_local}에 parquet 없음")

    if args.deploy_only:
        print("--deploy-only: 빌드 생략")
        ssh.close()
        return

    # ── 빌드 실행 (nohup 백그라운드 — 512×512는 8~10시간 소요) ──────────
    log_path = f"{REMOTE}/output/build_{args.version}.log"
    build_cmd = (
        f"cd {REMOTE} && "
        f"nohup env PYTHONUNBUFFERED=1 uv run python scripts/build_from_parquet.py "
        f"--checkpoint-dir {args.checkpoint_dir} "
        f"--output-dir {args.output_dir} "
        f"--version {args.version} "
        f"--start-date {args.start_date} "
        f"--end-date {args.end_date} "
        f"--grid-h {args.grid_h} "
        f"--grid-w {args.grid_w} "
        f"> {log_path} 2>&1 & echo $!"
    )

    print(f"\n[3/3] H100 빌드 시작 (cube_{args.version}, {args.grid_h}×{args.grid_w})...")
    print(f"  로그: {log_path}")
    print("-" * 60)

    _, stdout, _ = ssh.exec_command(build_cmd)
    pid = stdout.read().decode().strip()
    print(f"  PID: {pid}")
    print(f"\n✅ 백그라운드 빌드 시작됨 — SSH 연결 끊겨도 빌드 유지")
    print(f"\n진행 확인 명령 (H100에서):")
    print(f"  tail -f {log_path}")
    print(f"  ps aux | grep {pid}")
    print(f"\n완료 확인:")
    print(f"  cat {REMOTE}/output/cube_{args.version}/meta.json")

    ssh.close()


if __name__ == "__main__":
    main()
