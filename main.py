"""
Workbook Analyzer for Tableau — FastAPI サーバー
起動時にワークブック一覧のみ取得。差分・フィールド分析はオンデマンド。
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ─── キャッシュ ────────────────────────────────────────────
_lock  = threading.Lock()
_cache: dict = {"status": "idle", "workbooks": [], "error": None, "fetched_at": None}
_field_cache: dict = {}   # workbook_id → fields
_rev_cache:   dict = {}   # workbook_id → revisions
_diff_cache:  dict = {}   # "wb_id:base:head" → diff


# ─── データ取得 ────────────────────────────────────────────
def _do_fetch():
    with _lock:
        if _cache["status"] == "loading":
            return
        _cache["status"] = "loading"
        _cache["error"]  = None

    logger.info("ワークブック一覧を取得中...")
    try:
        from tableau_client import fetch_workbooks
        wbs = fetch_workbooks()
        from datetime import datetime, timezone
        with _lock:
            _cache["workbooks"]  = wbs
            _cache["status"]     = "ok"
            _cache["fetched_at"] = datetime.now(timezone.utc).isoformat()
        logger.info("取得完了: %d件", len(wbs))
    except Exception as exc:
        logger.error("取得失敗: %s", exc)
        with _lock:
            _cache["status"] = "error"
            _cache["error"]  = str(exc)


# ─── ライフスパン ──────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    t = threading.Thread(target=_do_fetch, daemon=True)
    t.start()
    yield


# ─── FastAPI アプリ ────────────────────────────────────────
app = FastAPI(
    title="Workbook Analyzer for Tableau",
    description="Tableau Cloud ワークブックのリビジョン差分・計算フィールド分析ツール",
    version="1.0.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse("static/index.html")


# ─── ステータス ────────────────────────────────────────────
@app.get("/api/status")
async def get_status():
    with _lock:
        return {
            "status":     _cache["status"],
            "error":      _cache["error"],
            "fetched_at": _cache["fetched_at"],
            "version":    app.version,
            "workbook_count": len(_cache["workbooks"]),
        }


# ─── ワークブック一覧 ──────────────────────────────────────
@app.get("/api/workbooks")
async def get_workbooks():
    with _lock:
        return {"workbooks": _cache["workbooks"]}


@app.post("/api/refresh")
async def refresh():
    t = threading.Thread(target=_do_fetch, daemon=True)
    t.start()
    return {"message": "再取得を開始しました"}


# ─── 計算フィールド分析 ────────────────────────────────────
@app.get("/api/workbooks/{workbook_id}/fields")
async def get_fields(workbook_id: str):
    if workbook_id in _field_cache:
        return _field_cache[workbook_id]
    try:
        from tableau_client import fetch_workbook_fields
        result = await asyncio.to_thread(fetch_workbook_fields, workbook_id)
        _field_cache[workbook_id] = result
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ─── リビジョン一覧 ────────────────────────────────────────
@app.get("/api/workbooks/{workbook_id}/revisions")
async def get_revisions(workbook_id: str):
    if workbook_id in _rev_cache:
        return _rev_cache[workbook_id]
    try:
        from tableau_client import fetch_workbook_revisions
        result = await asyncio.to_thread(fetch_workbook_revisions, workbook_id)
        _rev_cache[workbook_id] = result
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ─── リビジョン差分 ────────────────────────────────────────
@app.get("/api/workbooks/{workbook_id}/revision-diff")
async def get_revision_diff(workbook_id: str, base: int | None = None, head: int | None = None):
    cache_key = f"{workbook_id}:{base}:{head}"
    if cache_key in _diff_cache:
        return _diff_cache[cache_key]
    try:
        from tableau_client import fetch_workbook_revision_diff
        result = await asyncio.to_thread(fetch_workbook_revision_diff, workbook_id, base, head)
        _diff_cache[cache_key] = result
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ─── 起動 ──────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8001"))
    print("\n" + "=" * 55)
    print("  Workbook Analyzer for Tableau")
    print("=" * 55)
    print(f"  ブラウザで開く → http://localhost:{port}")
    print(f"  API ドキュメント → http://localhost:{port}/docs")
    print("  停止: Ctrl+C")
    print("=" * 55 + "\n")
    uvicorn.run("main:app", host="127.0.0.1", port=port, reload=False)
