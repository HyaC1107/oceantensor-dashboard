"""RAG 코퍼스 빌드 — 실제 프로젝트 문서·연구자료를 청크 단위로 정제해 rag/docs/corpus.json 생성.

소스는 이 레포 밖(어텐션 프로젝트 docs/)에 있음 — 원본 대용량 PDF는 git에 안 넣고,
이 스크립트로 뽑아낸 정제된 corpus.json만 커밋한다.

실행: uv run python rag/build_corpus.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from pypdf import PdfReader

# 어텐션 프로젝트 루트 — seaweed-hwangbaek의 조상 폴더
PROJECT_DOCS = Path("/mnt/c/Users/Administrator/Desktop/어텐션/docs")

# 1) 시스템 자기설명 — SSOT 기술 문서 (docs/active/)
MD_SOURCES = [
    "active/ADI_라벨링_근거.md",
    "active/API_및_데이터구조_정의서.md",
    "active/cube_v7_data_specification.md",
    "active/대시보드_사용매뉴얼.md",
    "active/데이터구조_종합보고서.md",
    "active/모델개발_종합보고서.md",
    "active/문헌_카탈로그.md",
]

# 2) 도메인 과학 — 황백화 직결 연구자료만 선별 (60여개 중 무관한 정책보고서 제외)
PDF_SOURCES = [
    "황백화관련연구자료(pdf)/금강 하구역 인근 김 황백화 원인 분석.pdf",
    "황백화관련연구자료(pdf)/비인만 김 양식장 황백화  발생 시기 에다른 물질수지 비교 산정.pdf",
    "황백화관련연구자료(pdf)/화력발전소 주변 김 황백화 피해 대응 연구용역(최종보고서).pdf",
    "황백화관련연구자료(pdf)/화력발전소 주변 김 황백화 피해대응 기술 고도화 연구용역_2.pdf",
    "황백화관련연구자료(pdf)/수온 조도 영양염이 방사무늬김과 잇바디 돌김의 사상체 생장 및 성숙에 미치는 영향.pdf",
    "황백화관련연구자료(pdf)/서해안 김 황백화 관리를 위한 하수종말처리장 방류수 활용 방안 연구.pdf",
]

MAX_CHUNK_CHARS = 1200
MIN_CHUNK_CHARS = 40

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")  # NUL 등 — Postgres text 컬럼 저장 불가


def _sanitize(text: str) -> str:
    """제어문자(NUL 등) 제거 — PDF/문서 추출 과정에서 섞여 들어오면 DB insert가 깨짐."""
    return _CONTROL_CHARS_RE.sub("", text)


def _split_long(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """문단(빈 줄) 경계로 우선 분할, 그래도 길면 문장 경계로 추가 분할."""
    if len(text) <= max_chars:
        return [text]
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    buf = ""
    for p in paras:
        if len(buf) + len(p) + 1 <= max_chars:
            buf = f"{buf}\n{p}".strip()
        else:
            if buf:
                chunks.append(buf)
            if len(p) <= max_chars:
                buf = p
            else:
                sentences = re.split(r"(?<=[.!?다])\s+", p)
                sbuf = ""
                for s in sentences:
                    if len(sbuf) + len(s) + 1 <= max_chars:
                        sbuf = f"{sbuf} {s}".strip()
                    else:
                        if sbuf:
                            chunks.append(sbuf)
                        sbuf = s
                if sbuf:
                    chunks.append(sbuf)
                buf = ""
    if buf:
        chunks.append(buf)
    return chunks


def chunk_markdown(path: Path) -> list[dict]:
    """헤딩(#/##/###) 경계로 섹션 분할."""
    text = _sanitize(path.read_text(encoding="utf-8"))
    lines = text.split("\n")

    sections: list[tuple[str, list[str]]] = []
    cur_title = path.stem
    cur_body: list[str] = []
    for line in lines:
        m = re.match(r"^(#{1,3})\s+(.+)$", line)
        if m:
            if cur_body:
                sections.append((cur_title, cur_body))
            cur_title = m.group(2).strip().lstrip("#").strip()
            cur_body = []
        else:
            cur_body.append(line)
    if cur_body:
        sections.append((cur_title, cur_body))

    docs = []
    for sec_title, body_lines in sections:
        body = "\n".join(body_lines).strip()
        body = re.sub(r"```.*?```", "", body, flags=re.DOTALL)  # 코드블록 제거(표/설명 위주로)
        body = re.sub(r"\n{3,}", "\n\n", body).strip()
        if len(body) < MIN_CHUNK_CHARS:
            continue
        for i, chunk in enumerate(_split_long(body)):
            if len(chunk) < MIN_CHUNK_CHARS:
                continue
            docs.append({
                "title": f"{path.stem} — {sec_title}" if sec_title != path.stem else path.stem,
                "content": chunk,
                "source": f"docs/active/{path.name}",
                "source_type": "system_doc",
            })
    return docs


def chunk_pdf(path: Path) -> list[dict]:
    """페이지 단위 청크(페이지가 너무 길면 추가 분할)."""
    reader = PdfReader(str(path))
    docs = []
    for page_no, page in enumerate(reader.pages, start=1):
        text = _sanitize((page.extract_text() or "").strip())
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]{2,}", " ", text)
        if len(text) < MIN_CHUNK_CHARS:
            continue
        for chunk in _split_long(text):
            if len(chunk) < MIN_CHUNK_CHARS:
                continue
            docs.append({
                "title": f"{path.stem} (p.{page_no})",
                "content": chunk,
                "source": f"research/{path.name}",
                "source_type": "research_paper",
            })
    return docs


def main():
    all_docs: list[dict] = []

    print("[1/2] 시스템 문서(docs/active/) 청크 중...")
    for rel in MD_SOURCES:
        p = PROJECT_DOCS / rel
        if not p.exists():
            print(f"  ⚠️ 없음: {p}")
            continue
        docs = chunk_markdown(p)
        print(f"  {p.name} → {len(docs)}청크")
        all_docs.extend(docs)

    print("\n[2/2] 연구 PDF 청크 중...")
    for rel in PDF_SOURCES:
        p = PROJECT_DOCS / rel
        if not p.exists():
            print(f"  ⚠️ 없음: {p}")
            continue
        docs = chunk_pdf(p)
        print(f"  {p.name} → {len(docs)}청크")
        all_docs.extend(docs)

    for i, d in enumerate(all_docs):
        d["id"] = f"doc_{i:04d}"
        d.setdefault("tags", [])

    out_path = Path(__file__).parent / "docs" / "corpus.json"
    out_path.write_text(
        json.dumps(all_docs, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n총 {len(all_docs)}청크 → {out_path}")


if __name__ == "__main__":
    main()
