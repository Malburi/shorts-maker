"""RAG — Whisper 세그먼트를 ChromaDB에 인덱싱하고 질의응답."""
import asyncio
from pathlib import Path
from openai import OpenAI
import chromadb

_CHROMA_PATH = Path(__file__).parent.parent.parent / "chroma_db"
_chroma: chromadb.ClientAPI | None = None


def _client() -> chromadb.ClientAPI:
    global _chroma
    if _chroma is None:
        _chroma = chromadb.PersistentClient(path=str(_CHROMA_PATH))
    return _chroma


def _col_name(job_id: str) -> str:
    return f"j{job_id.replace('-', '')}"


def _fmt_time(seconds: float) -> str:
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m}:{s:02d}"


def _chunk_segments(segments: list, window: float = 30.0) -> list[dict]:
    """Whisper 세그먼트를 ~window초 단위 청크로 묶기."""
    chunks, buf, buf_start = [], [], None
    for seg in segments:
        text = seg.get("text", "").strip()
        if not text:
            continue
        if buf_start is None:
            buf_start = seg["start"]
        buf.append(text)
        if seg["end"] - buf_start >= window:
            chunks.append({"text": " ".join(buf), "start": buf_start, "end": seg["end"]})
            buf, buf_start = [], None
    if buf and buf_start is not None:
        chunks.append({"text": " ".join(buf), "start": buf_start, "end": segments[-1]["end"]})
    return chunks


def _index_sync(job_id: str, segments: list) -> int:
    chunks = _chunk_segments(segments)
    if not chunks:
        return 0

    oai = OpenAI()
    texts = [c["text"] for c in chunks]
    resp = oai.embeddings.create(model="text-embedding-3-small", input=texts)
    embeddings = [e.embedding for e in resp.data]

    col = _client().get_or_create_collection(
        name=_col_name(job_id),
        metadata={"hnsw:space": "cosine"},
    )
    col.add(
        ids=[f"{job_id}_{i}" for i in range(len(chunks))],
        embeddings=embeddings,
        documents=texts,
        metadatas=[{"start": c["start"], "end": c["end"]} for c in chunks],
    )
    return len(chunks)


def _query_sync(job_id: str, question: str) -> dict:
    oai = OpenAI()

    q_emb = oai.embeddings.create(
        model="text-embedding-3-small", input=[question]
    ).data[0].embedding

    col = _client().get_collection(_col_name(job_id))
    res = col.query(query_embeddings=[q_emb], n_results=3)

    docs = res["documents"][0]
    metas = res["metadatas"][0]
    if not docs:
        return {"answer": "관련 내용을 찾을 수 없습니다.", "sources": []}

    context = "\n\n".join(
        f"[{_fmt_time(m['start'])} ~ {_fmt_time(m['end'])}]\n{d}"
        for d, m in zip(docs, metas)
    )

    answer = oai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": (
                "당신은 영상 내용 전문가입니다. "
                "아래 전사 내용만을 근거로 질문에 한국어로 답하세요. "
                "답변 마지막에 '📍 X분 Y초' 형식으로 출처 시간을 반드시 표기하세요. "
                "전사 내용에 없는 내용은 '영상에서 확인되지 않습니다'라고 답하세요."
            )},
            {"role": "user", "content": f"전사 내용:\n{context}\n\n질문: {question}"},
        ],
        temperature=0.3,
    ).choices[0].message.content

    sources = [
        {"start": m["start"], "end": m["end"], "preview": d[:60] + ("..." if len(d) > 60 else "")}
        for d, m in zip(docs, metas)
    ]
    return {"answer": answer, "sources": sources}


async def index_segments(job_id: str, segments: list) -> int:
    return await asyncio.to_thread(_index_sync, job_id, segments)


async def query(job_id: str, question: str) -> dict:
    return await asyncio.to_thread(_query_sync, job_id, question)


def has_index(job_id: str) -> bool:
    try:
        _client().get_collection(_col_name(job_id))
        return True
    except Exception:
        return False
