# /// script
# dependencies = [
#   "paramiko",
#   "rich",
#   "python-dotenv",
# ]
# ///

"""H100 학습 진행상황 실시간 TUI 모니터.

사용:
    uv run scripts/monitor_training.py
"""
import os
import re
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

import paramiko
from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, BarColumn, TextColumn
from rich.live import Live
from rich.align import Align

load_dotenv(Path(__file__).parent.parent / ".env")

HOST     = os.getenv("H100_HOST")
USER     = os.getenv("H100_USER")
PASSWORD = os.getenv("H100_PASSWORD")
LOG_PATH = "/home/tta/cheolyoung/output/train_v13.log"
TOTAL_EPOCHS = 50

console = Console()

def connect():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, username=USER, password=PASSWORD)
    return ssh

def get_status(ssh):
    # 1. 로그에서 최근 15개 에포크 결과 파싱
    _, out, _ = ssh.exec_command(
        f'cat {LOG_PATH} | tr "\\r" "\\n" | grep -E "Epoch[[:space:]]+[0-9]+/" | tail -15'
    )
    epoch_lines = out.read().decode().strip().splitlines()

    # 2. 현재 진행 중인 세부 단계
    _, out, _ = ssh.exec_command(
        f'tail -10 {LOG_PATH} | tr "\\r" "\\n" | grep -E "train 시작|val 시작" | tail -1'
    )
    current = out.read().decode().strip()

    # 3. GPU 정보
    _, out, _ = ssh.exec_command(
        'nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,name '
        '--format=csv,noheader,nounits'
    )
    gpu_info = out.read().decode().strip()

    # 4. 프로세스 생존 상태
    _, out, _ = ssh.exec_command('pgrep -a python3 | grep train_real | wc -l')
    alive = out.read().decode().strip()

    return epoch_lines, current, gpu_info, alive

def parse_epoch(line):
    """  Epoch   1/50 | train=0.3121 | val=0.4914 | lr=1.00e-04 | 1217.0s"""
    m = re.search(r'Epoch\s+(\d+)/(\d+).*train=([\d.]+).*val=([\d.]+).*lr=([\d.e-]+).*\|\s+([\d.]+)s', line)
    if m:
        return {
            "epoch": int(m.group(1)),
            "total": int(m.group(2)),
            "train": float(m.group(3)),
            "val":   float(m.group(4)),
            "lr":    m.group(5),
            "secs":  float(m.group(6)),
        }
    return None

def build_layout() -> Layout:
    layout = Layout()
    layout.split(
        Layout(name="header", size=3),
        Layout(name="main", ratio=1),
        Layout(name="footer", size=3)
    )
    layout["main"].split_row(
        Layout(name="left", ratio=1),
        Layout(name="right", ratio=2)
    )
    return layout

def update_dashboard(layout, epoch_lines, current, gpu_info, alive):
    # ── [HEADER] ──
    status_str = "[bold green]🟢 ACTIVE (훈련 중)[/]" if alive == "1" else "[bold red]🔴 INACTIVE (종료됨)[/]"
    header_table = Table.grid(expand=True)
    header_table.add_column(justify="left", ratio=1)
    header_table.add_column(justify="right", ratio=1)
    header_table.add_row(
        " 🔬 [bold white]ST-MMT 황백화 조기경보 AI 학습 관제실[/] [dim](v13_cube_v7_3stage)[/]",
        f"서버: [bold yellow]{HOST}[/]  |  상태: {status_str} "
    )
    layout["header"].update(Panel(header_table, style="blue"))

    # ── [LEFT: GPU & System Status] ──
    gpu_panel_content = []
    if gpu_info:
        parts = gpu_info.split(",")
        if len(parts) >= 5:
            util, mem_used, mem_total, temp, gpu_name = [p.strip() for p in parts]
            gpu_panel_content.append(f"[bold cyan]GPU 모델:[/] {gpu_name}")
            
            # Utilization Bar
            util_val = int(util)
            bar_len = int(util_val / 5)
            bar = "█" * bar_len + "░" * (20 - bar_len)
            gpu_panel_content.append(f"[bold cyan]GPU Util:[/] {bar} [bold green]{util_val}%[/]")
            
            # Mem & Temp
            gpu_panel_content.append(f"[bold cyan]메모리:[/] [yellow]{mem_used}[/] / {mem_total} MiB")
            gpu_panel_content.append(f"[bold cyan]코어 온도:[/] [red]{temp}°C[/]")
    else:
        gpu_panel_content.append("[dim]GPU 정보를 불러올 수 없습니다.[/]")
    
    layout["left"].update(Panel("\n".join(gpu_panel_content), title="[bold cyan]🖥️ GPU & System[/]", border_style="cyan"))

    # ── [RIGHT: Training Progress & Epoch History] ──
    parsed = [parse_epoch(l) for l in epoch_lines if parse_epoch(l)]
    
    right_layout = Layout()
    right_layout.split(
        Layout(name="progress", size=6),
        Layout(name="history", ratio=1)
    )
    
    # Progress Section
    progress_table = Table.grid(expand=True)
    progress_table.add_column(ratio=1)
    
    if parsed:
        last = parsed[-1]
        done = last["epoch"]
        total = last["total"]
        
        # Epoch Bar
        bar_len = int(done / total * 30)
        bar = "█" * bar_len + "░" * (30 - bar_len)
        progress_table.add_row(f"[bold magenta]에포크 진행률:[/] {bar} [bold magenta]{done}/{total}[/]")
        
        # ETA 계산
        avg_secs = sum(p["secs"] for p in parsed) / len(parsed)
        remaining = (total - done) * avg_secs
        h, m, s = int(remaining // 3600), int((remaining % 3600) // 60), int(remaining % 60)
        progress_table.add_row(f"[bold white]예상 잔여시간:[/] [bold yellow]{h:02d}시간 {m:02d}분 {s:02d}초[/] [dim](에포크당 평균 {avg_secs:.1f}초)[/]")
    else:
        progress_table.add_row("[bold magenta]에포크 진행률:[/] [dim]░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ 0/50[/]")
        progress_table.add_row("[bold white]예상 잔여시간:[/] [dim]계산 중...[/]")

    step_status = current if current else "데이터 로드 및 모델 초기화 중..."
    progress_table.add_row(f"[bold cyan]현재 동작:[/] [bold green]{step_status}[/]")
    
    right_layout["progress"].update(Panel(progress_table, title="[bold magenta]📈 Training Progress[/]", border_style="magenta"))

    # History Table Section
    history_table = Table(expand=True, show_header=True, header_style="bold cyan")
    history_table.add_column("Epoch", justify="center", style="bold white")
    history_table.add_column("Train Loss", justify="right", style="green")
    history_table.add_column("Val Loss", justify="right", style="red")
    history_table.add_column("Learning Rate", justify="center", style="yellow")
    history_table.add_column("Duration", justify="right", style="dim white")
    
    # 최근 7개 에포크만 하단에 렌더링
    for p in parsed[-7:]:
        history_table.add_row(
            str(p["epoch"]),
            f"{p['train']:.4f}",
            f"{p['val']:.4f}",
            p["lr"],
            f"{p['secs']:.0f}s"
        )
    
    right_layout["history"].update(history_table)
    layout["right"].update(right_layout)

    # ── [FOOTER] ──
    footer_text = Align.center(
        "[bold white]W&B 실시간 대시보드:[/] [underline cyan]https://wandb.ai/ikoweas-attention-plz/hwangbaek[/]  |  [dim]30초마다 갱신 (종료: Ctrl+C)[/]"
    )
    layout["footer"].update(Panel(footer_text, border_style="dim"))

def main():
    console.print("[bold yellow]H100 GPU 서버 연결 대기 중...[/]")
    try:
        ssh = connect()
        console.print("[bold green]Connected successfully![/] 모니터링 TUI 렌더링을 시작합니다.")
        time.sleep(1)
    except Exception as e:
        console.print(f"[bold red]Failed to connect to H100 server: {e}[/]")
        sys.exit(1)

    layout = build_layout()
    
    try:
        with Live(layout, refresh_per_second=1, screen=True) as live:
            while True:
                try:
                    epoch_lines, current, gpu_info, alive = get_status(ssh)
                    update_dashboard(layout, epoch_lines, current, gpu_info, alive)
                except Exception as e:
                    # SSH 연결 재시도
                    try:
                        ssh.close()
                    except:
                        pass
                    time.sleep(5)
                    ssh = connect()
                time.sleep(30)
    except KeyboardInterrupt:
        pass
    finally:
        ssh.close()
        console.clear()
        console.print("[bold yellow]모니터가 정상적으로 종료되었습니다.[/]")

if __name__ == "__main__":
    main()
