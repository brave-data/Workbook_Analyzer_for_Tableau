"""
Tableau Cloud クライアント — ワークブック分析特化版
取得するのはワークブック一覧のみ。差分・フィールド分析はオンデマンド。
"""
from __future__ import annotations

import logging
import os
import re
import tempfile
import zipfile
from datetime import datetime
from typing import Any

import defusedxml.ElementTree as ET
import tableauserverclient as TSC
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# ─── 接続設定 ──────────────────────────────────────────────
_SERVER_URL   = os.getenv("TABLEAU_SERVER_URL", "")
_SITE_NAME    = os.getenv("TABLEAU_SITE_NAME", "")
_TOKEN_NAME   = os.getenv("TABLEAU_TOKEN_NAME", "")
_TOKEN_SECRET = os.getenv("TABLEAU_TOKEN_SECRET", "")
_HTTP_TIMEOUT = 120


def _make_server() -> TSC.Server:
    auth = TSC.PersonalAccessTokenAuth(_TOKEN_NAME, _TOKEN_SECRET, site_id=_SITE_NAME)
    server = TSC.Server(_SERVER_URL, use_server_version=True)
    server.session.verify = os.getenv("REQUESTS_CA_BUNDLE", True)
    opts = TSC.RequestOptions()
    opts.page_size = 200
    server.auth.sign_in(auth)
    return server


def _fmt(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


# ─── ワークブック一覧 ──────────────────────────────────────
def fetch_workbooks() -> list[dict]:
    """ワークブック一覧を取得して返す（軽量: 一覧のみ）"""
    server = _make_server()
    try:
        opts = TSC.RequestOptions(pagesize=200)
        all_wbs, _ = server.workbooks.get(req_options=opts)
        # ページネーション
        total = server.workbooks.get(req_options=opts)[1].total_available
        page = 1
        while len(all_wbs) < total:
            page += 1
            opts2 = TSC.RequestOptions(pagesize=200, pagenumber=page)
            chunk, _ = server.workbooks.get(req_options=opts2)
            if not chunk:
                break
            all_wbs.extend(chunk)

        return [
            {
                "id":           wb.id,
                "name":         wb.name,
                "project":      wb.project_name or "",
                "owner_id":     wb.owner_id or "",
                "updated_at":   _fmt(wb.updated_at),
                "webpage_url":  wb.webpage_url or "",
            }
            for wb in all_wbs
        ]
    finally:
        server.auth.sign_out()


# ─── TWB/TWBX パース ──────────────────────────────────────
def _read_twb_content(workbook_id: str) -> str:
    """ワークブックをダウンロードして TWB の XML 文字列を返す"""
    server = _make_server()
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = server.workbooks.download(
                workbook_id, filepath=tmpdir, include_extract=False
            )
            import pathlib
            fp = pathlib.Path(file_path)
            if fp.suffix.lower() == ".twbx":
                with zipfile.ZipFile(fp, "r") as zf:
                    twb_name = next(n for n in zf.namelist() if n.endswith(".twb"))
                    return zf.read(twb_name).decode("utf-8", errors="replace")
            else:
                return fp.read_text(encoding="utf-8", errors="replace")
    finally:
        server.auth.sign_out()


def _parse_twb_fields(content: str) -> dict:
    """計算フィールドを解析して返す"""
    try:
        root = ET.fromstring(content.encode("utf-8"))
    except Exception:
        return {"datasources": [], "calculated_fields": []}

    datasources = []
    calc_fields = []
    seen_ds = set()

    for ds in root.iter("datasource"):
        ds_name = ds.get("name", "") or ds.get("caption", "")
        if not ds_name or ds_name in ("[Parameters]", "Parameters"):
            continue
        caption = ds.get("caption", ds_name)
        if ds_name not in seen_ds:
            datasources.append({"name": ds_name, "caption": caption})
            seen_ds.add(ds_name)

        # 内部名 → 論理名(caption) のマッピングを構築
        name_to_caption: dict[str, str] = {}
        for col in ds.iter("column"):
            internal = col.get("name", "")
            cap = col.get("caption", "")
            if internal and cap:
                name_to_caption[internal] = cap

        def _resolve_formula(formula: str) -> str:
            """フォーミュラ内の内部名 [Calculation_xxx] を論理名に変換"""
            def _replace(m: re.Match) -> str:
                key = m.group(0)          # e.g. [Calculation_3376503514920759299]
                inner = m.group(1)        # e.g. Calculation_3376503514920759299
                display = name_to_caption.get(key) or name_to_caption.get(f"[{inner}]")
                return f"[{display}]" if display else key
            return re.sub(r'\[([^\]]+)\]', _replace, formula)

        for col in ds.iter("column"):
            formula_el = col.find("calculation")
            if formula_el is None:
                continue
            formula = formula_el.get("formula", "")
            if not formula:
                continue
            field_name = col.get("caption") or col.get("name", "")
            calc_fields.append({
                "datasource": caption or ds_name,
                "field":      field_name,
                "formula":    _resolve_formula(formula),
                "datatype":   col.get("datatype", ""),
            })

    return {"datasources": datasources, "calculated_fields": calc_fields}


def _parse_twb_filters(content: str) -> list[dict]:
    """フィルター情報を解析して返す"""
    try:
        root = ET.fromstring(content.encode("utf-8"))
    except Exception:
        return []

    filters = []
    for ws in root.iter("worksheet"):
        ws_name = ws.get("name", "")
        for f in ws.iter("filter"):
            field = f.get("column", f.get("field", ""))
            ftype = f.get("class", "")
            if not field:
                continue
            entry: dict[str, Any] = {"sheet": ws_name, "field": field, "type": ftype}
            if ftype == "categorical":
                vals = [m.get("value", "") for m in f.findall(".//member[@member]") or f.findall(".//member")]
                entry["values"] = [v for v in vals if v]
            elif ftype == "quantitative":
                entry["min"] = f.get("min")
                entry["max"] = f.get("max")
            elif ftype == "relative-date":
                entry["period"] = f.get("period-type")
                entry["range"]  = f.get("range-n")
            elif ftype == "top":
                entry["top_n"] = f.get("count")
            filters.append(entry)
    return filters


def _parse_twb_sheets(content: str) -> list[dict]:
    """シート（ワークシート / ダッシュボード / ストーリー）を返す"""
    try:
        root = ET.fromstring(content.encode("utf-8"))
    except Exception:
        return []

    sheets = []
    for ws in root.iter("worksheet"):
        sheets.append({"name": ws.get("name", ""), "type": "worksheet"})
    for db in root.iter("dashboard"):
        sheets.append({"name": db.get("name", ""), "type": "dashboard"})
    for st in root.iter("story"):
        sheets.append({"name": st.get("name", ""), "type": "story"})
    return sheets


def _parse_twb_all(content: str) -> dict:
    base = _parse_twb_fields(content)
    return {
        **base,
        "filters": _parse_twb_filters(content),
        "sheets":  _parse_twb_sheets(content),
    }


# ─── 計算フィールド分析 ────────────────────────────────────
def fetch_workbook_fields(workbook_id: str) -> dict:
    content = _read_twb_content(workbook_id)
    return _parse_twb_fields(content)


# ─── リビジョン差分 ────────────────────────────────────────
def fetch_workbook_revisions(workbook_id: str) -> dict:
    server = _make_server()
    try:
        wb = server.workbooks.get_by_id(workbook_id)
        server.workbooks.populate_revisions(wb)
        # 新しい順にソート（UIのデフォルト選択: revs[0]=最新, revs[1]=1つ前）
        revs = sorted(
            wb.revisions,
            key=lambda r: getattr(r, "revision_number", 0),
            reverse=True,
        )
        return {
            "workbook_id":   workbook_id,
            "workbook_name": wb.name,
            "revisions": [
                {
                    "revision_number": getattr(r, "revision_number", None),
                    "created_at":      _fmt(getattr(r, "_created_at", None)),
                    "publisher":       getattr(r, "_user_name", None),
                    "is_current":      getattr(r, "_current", False),
                }
                for r in revs
            ],
        }
    finally:
        server.auth.sign_out()


def _compute_revision_diff(base: dict, head: dict) -> dict:
    def _field_key(f):
        return (f["datasource"], f["field"])

    def _filter_key(f):
        return (f.get("sheet", ""), f.get("field", ""), f.get("type", ""))

    def _sheet_key(s):
        return (s["name"], s["type"])

    def _ds_key(d):
        return d["name"]

    # 計算フィールド
    base_cf = {_field_key(f): f for f in base.get("calculated_fields", [])}
    head_cf = {_field_key(f): f for f in head.get("calculated_fields", [])}
    cf_added   = [head_cf[k] for k in head_cf if k not in base_cf]
    cf_deleted = [base_cf[k] for k in base_cf if k not in head_cf]
    cf_changed = [
        {
            "datasource":  head_cf[k]["datasource"],
            "field":       head_cf[k]["field"],
            "old_formula": base_cf[k]["formula"],
            "new_formula": head_cf[k]["formula"],
        }
        for k in head_cf
        if k in base_cf and base_cf[k]["formula"] != head_cf[k]["formula"]
    ]

    # フィルター
    base_fl = {_filter_key(f): f for f in base.get("filters", [])}
    head_fl = {_filter_key(f): f for f in head.get("filters", [])}
    fl_added   = [head_fl[k] for k in head_fl if k not in base_fl]
    fl_deleted = [base_fl[k] for k in base_fl if k not in head_fl]
    fl_changed = [
        {"field": head_fl[k]["field"], "sheet": head_fl[k].get("sheet", ""),
         "old": base_fl[k], "new": head_fl[k]}
        for k in head_fl
        if k in base_fl and base_fl[k] != head_fl[k]
    ]

    # データソース
    base_ds = {_ds_key(d): d for d in base.get("datasources", [])}
    head_ds = {_ds_key(d): d for d in head.get("datasources", [])}
    ds_added   = [head_ds[k] for k in head_ds if k not in base_ds]
    ds_deleted = [base_ds[k] for k in base_ds if k not in head_ds]

    # シート
    base_sh = {_sheet_key(s): s for s in base.get("sheets", [])}
    head_sh = {_sheet_key(s): s for s in head.get("sheets", [])}
    sh_added   = [head_sh[k] for k in head_sh if k not in base_sh]
    sh_deleted = [base_sh[k] for k in base_sh if k not in head_sh]

    return {
        "calculated_fields": {"added": cf_added, "deleted": cf_deleted, "changed": cf_changed},
        "filters":           {"added": fl_added, "deleted": fl_deleted, "changed": fl_changed},
        "datasources":       {"added": ds_added, "deleted": ds_deleted},
        "sheets":            {"added": sh_added, "deleted": sh_deleted},
    }


def fetch_workbook_revision_diff(workbook_id: str, base_rev=None, head_rev=None) -> dict:
    server = _make_server()
    try:
        wb = server.workbooks.get_by_id(workbook_id)
        server.workbooks.populate_revisions(wb)
        revs = sorted(
            wb.revisions,
            key=lambda r: getattr(r, "revision_number", 0),
            reverse=True,
        )
        if len(revs) < 2:
            raise ValueError("比較できるリビジョンが2件以上ありません")

        current_rev_num = next(
            (getattr(r, "revision_number", None) for r in revs if getattr(r, "_current", False)),
            getattr(revs[0], "revision_number", None),
        )

        if head_rev is None:
            head_rev = getattr(revs[0], "revision_number", None)
        if base_rev is None:
            base_rev = getattr(revs[1], "revision_number", None)

        rev_meta = {getattr(r, "revision_number", None): r for r in revs}

        def _download_rev(rev_num: int) -> str:
            with tempfile.TemporaryDirectory() as tmpdir:
                if str(rev_num) == str(current_rev_num):
                    file_path = server.workbooks.download(
                        workbook_id, filepath=tmpdir, include_extract=False
                    )
                else:
                    url = f"{server.workbooks.baseurl}/{workbook_id}/revisions/{rev_num}/content"
                    resp = server.workbooks.get_request(url)
                    import pathlib
                    # Content-Type ではなくマジックバイトで ZIP 判定（octet-stream 対策）
                    content_bytes = resp.content
                    ext = ".twbx" if content_bytes[:2] == b"PK" else ".twb"
                    out = pathlib.Path(tmpdir) / f"rev{rev_num}{ext}"
                    out.write_bytes(content_bytes)
                    file_path = str(out)

                import pathlib
                fp = pathlib.Path(file_path)
                if fp.suffix.lower() == ".twbx":
                    with zipfile.ZipFile(fp, "r") as zf:
                        twb_name = next(n for n in zf.namelist() if n.endswith(".twb"))
                        return zf.read(twb_name).decode("utf-8", errors="replace")
                return fp.read_text(encoding="utf-8", errors="replace")

        base_content = _download_rev(base_rev)
        head_content = _download_rev(head_rev)

        base_parsed = _parse_twb_all(base_content)
        head_parsed = _parse_twb_all(head_content)

        def _rev_info(rnum):
            r = rev_meta.get(rnum)
            if not r:
                return {"revision_number": str(rnum)}
            return {
                "revision_number": str(getattr(r, "revision_number", rnum)),
                "created_at":      _fmt(getattr(r, "_created_at", None)),
                "publisher":       getattr(r, "_user_name", None),
            }

        return {
            "workbook_id":    workbook_id,
            "workbook_name":  wb.name,
            "base_revision":  _rev_info(base_rev),
            "head_revision":  _rev_info(head_rev),
            "diff":           _compute_revision_diff(base_parsed, head_parsed),
        }
    finally:
        server.auth.sign_out()
