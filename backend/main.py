"""
IntelliDoc Backend — FastAPI
============================
Endpoints:
  POST /api/process        Upload PDF or image, run OCR pipeline
  GET  /api/jobs/{id}      Poll job status + streaming progress
  GET  /api/download/{id}  Download DOCX result
  GET  /api/overlay/{id}   Get overlay image (bounding box viz)
  GET  /api/json/{id}      Get raw JSON result
  DELETE /api/jobs/{id}    Clean up job files
"""

import os, uuid, time, json, shutil, asyncio, traceback
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import fitz          # PyMuPDF — PDF → image
from PIL import Image

# ── PATHS ─────────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent
JOBS_DIR    = BASE_DIR / "jobs"
JOBS_DIR.mkdir(exist_ok=True)

# ── LAZY MODEL CACHE ──────────────────────────────────────────────────────────
_models = {}

def get_models():
    """Load OCR models once, reuse across requests."""
    if "ready" in _models:
        return _models["layout"], _models["ocr"]

    from paddleocr import PPStructure, PaddleOCR
    import warnings; warnings.filterwarnings("ignore")

    layout = None
    for kw in [dict(layout=True, table=False, ocr=False, show_log=False),
               dict(layout=True, table=False, ocr=False),
               dict(layout=True, table=False),
               dict(layout=True)]:
        try:
            layout = PPStructure(**kw); break
        except TypeError:
            continue

    try:    ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
    except TypeError: ocr = PaddleOCR(use_angle_cls=True, lang="en")

    _models["layout"] = layout
    _models["ocr"]    = ocr
    _models["ready"]  = True
    return layout, ocr


# ── JOB STATE ─────────────────────────────────────────────────────────────────
# In-memory job store. For production replace with Redis.
jobs: dict[str, dict] = {}

def new_job(job_id: str, filename: str):
    jobs[job_id] = {
        "id":       job_id,
        "filename": filename,
        "status":   "queued",   # queued | processing | done | error
        "progress": 0,
        "stage":    "Waiting...",
        "error":    None,
        "created":  time.time(),
    }

def update_job(job_id, **kw):
    if job_id in jobs:
        jobs[job_id].update(kw)


# ── PDF → IMAGE ───────────────────────────────────────────────────────────────
def pdf_to_images(pdf_path: Path, out_dir: Path, dpi: int = 150) -> list[Path]:
    doc   = fitz.open(str(pdf_path))
    paths = []
    for i, page in enumerate(doc):
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
        img_path = out_dir / f"page_{i+1:04d}.png"
        pix.save(str(img_path))
        paths.append(img_path)
    doc.close()
    return paths


# ── CORE PIPELINE ─────────────────────────────────────────────────────────────
def run_pipeline(job_id: str, image_path: Path, job_dir: Path):
    """Run the full intellidoc_v9 pipeline on one page image."""
    import cv2, numpy as np

    # Import pipeline functions from intellidoc_v9
    # We import here to avoid loading at server startup
    import sys
    sys.path.insert(0, str(BASE_DIR))
    from pipeline import (
        preprocess, get_ppstruct_scale, scale_bbox, clamp,
        detect_rows, detect_cols, ocr_cell, extract_table,
        ocr_region, words_to_lines, lines_to_blocks,
        estimate_cols_kde, classify, reading_order, dedup,
        draw_overlay, quad_to_bbox, bcx, bcy, in_table_check,
    )

    update_job(job_id, stage="Loading image", progress=5)
    raw  = cv2.imread(str(image_path))
    page = preprocess(raw)
    H, W = page.shape[:2]
    gray = cv2.cvtColor(page, cv2.COLOR_BGR2GRAY)

    update_job(job_id, stage="Layout detection", progress=15)
    layout, ocr = get_models()
    layout_result = layout(page)

    sx, sy = get_ppstruct_scale(page.shape, layout_result)

    tbl_bboxes = []
    for blk in layout_result:
        if str(blk.get("type","")).lower() == "table":
            bb = scale_bbox(list(map(int, blk["bbox"])), sx, sy)
            bb = list(clamp(*bb, W, H))
            tbl_bboxes.append(bb)

    update_job(job_id, stage="Full-page OCR", progress=25)
    page_masked = page.copy()
    for tx1,ty1,tx2,ty2 in tbl_bboxes:
        page_masked[ty1:ty2, tx1:tx2] = 255

    page_words = []
    res = ocr.ocr(page_masked, cls=True)
    if res and res[0]:
        for it in res[0]:
            txt = it[1][0].strip()
            if txt:
                bx1,by1,bx2,by2 = quad_to_bbox(it[0])
                page_words.append({"text":txt,"conf":float(it[1][1]),
                                   "bbox":[bx1,by1,bx2,by2]})

    cols_est = estimate_cols_kde(page_words, W)

    def in_tbl(wb):
        return in_table_check(wb, tbl_bboxes)

    update_job(job_id, stage="Extracting blocks", progress=40)
    layout_blocks = []
    order_units   = []
    n_blks = len(layout_result)

    for bi, blk in enumerate(layout_result):
        btype = str(blk.get("type","")).lower()
        bb    = scale_bbox(list(map(int, blk["bbox"])), sx, sy)
        bx1,by1,bx2,by2 = clamp(*bb, W, H)
        prog  = 40 + int(45 * (bi+1) / max(n_blks,1))
        update_job(job_id, progress=prog,
                   stage=f"Block {bi+1}/{n_blks}: {btype}")

        if btype == "table":
            tbl  = extract_table(ocr, gray, page, [bx1,by1,bx2,by2])
            rb   = tbl["real_bbox"]
            kind = classify(rb, cols_est, W)
            layout_blocks.append({"type":"table","bbox":rb,"table":tbl})
            order_units.append({"type":"table","bbox":rb,"kind":kind,
                                 "table":{"matrix":tbl["matrix"],
                                          "rows":tbl["rows"],"cols":tbl["cols"],
                                          "cells":tbl["cells"]}})
        else:
            words  = ocr_region(ocr, page, bx1,by1,bx2,by2)
            words  = [w for w in words if not in_tbl(w["bbox"])]
            lines  = words_to_lines(words)
            blocks = lines_to_blocks(lines)
            sub_blocks = []
            for b in blocks:
                text = "\n".join(ln["text"] for ln in b["lines"]).strip()
                if not text: continue
                k = classify(b["bbox"], cols_est, W)
                sub_blocks.append({"bbox":b["bbox"],"text":text,"kind":k})
                order_units.append({"type":btype,"bbox":b["bbox"],"kind":k,"text":text})
            layout_blocks.append({"type":btype,"bbox":[bx1,by1,bx2,by2],
                                   "sub_blocks":sub_blocks,
                                   "text":"\n\n".join(sb["text"] for sb in sub_blocks).strip()})

    update_job(job_id, stage="Building reading order", progress=88)
    order_units = dedup(order_units)
    ordered     = reading_order(order_units, H)

    update_job(job_id, stage="Saving overlay image", progress=91)
    overlay = draw_overlay(page, ordered, cols_est)
    cv2.imwrite(str(job_dir / "overlay.png"), overlay)

    update_job(job_id, stage="Saving JSON", progress=93)
    result = {
        "image":            str(image_path),
        "page_size":        {"w": W, "h": H},
        "columns_estimate": cols_est,
        "layout_blocks":    layout_blocks,
        "reading_order":    ordered,
    }
    json_path = job_dir / "result.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    from exporters import export_markdown, export_html
    import subprocess, sys

    # ── DOCX via Node/build_doc.js ───────────────────────────────────────────
    update_job(job_id, stage="Generating DOCX", progress=94)
    try:
        build_doc_js = BASE_DIR / "build_doc.js"
        node_modules = BASE_DIR / "node_modules"
        if not build_doc_js.exists():
            raise FileNotFoundError("build_doc.js not found in backend/")
        if not node_modules.exists():
            raise FileNotFoundError("node_modules not found — run: cd backend && npm install")
        node_cmd = shutil.which("node") or "node"
        proc = subprocess.run(
            [node_cmd, str(build_doc_js), str(json_path), str(job_dir / "result.docx")],
            capture_output=True, text=True, timeout=120,
            cwd=str(BASE_DIR)      # so require("docx") finds node_modules
        )
        if proc.returncode != 0:
            raise RuntimeError(f"build_doc.js failed:\n{proc.stderr}")
        print(f"[DOCX] {proc.stdout.strip()}", file=sys.stderr)
    except Exception as e:
        print(f"[DOCX ERROR] {e}", file=sys.stderr)
        jobs[job_id]["docx_error"] = str(e)

    # ── Markdown ─────────────────────────────────────────────────────────────
    update_job(job_id, stage="Generating Markdown", progress=96)
    try:
        export_markdown(result, job_dir / "result.md")
    except Exception as e:
        print(f"[MD ERROR] {e}", file=sys.stderr)

    # ── HTML ──────────────────────────────────────────────────────────────────
    update_job(job_id, stage="Generating HTML", progress=98)
    try:
        export_html(result, job_dir / "result.html")
    except Exception as e:
        print(f"[HTML ERROR] {e}", file=sys.stderr)

    update_job(job_id, stage="Done", progress=100, status="done")
    return result


# ── BACKGROUND TASK ───────────────────────────────────────────────────────────

def process_job(job_id: str, file_path: Path, job_dir: Path, is_pdf: bool):
    try:
        update_job(job_id, status="processing", stage="Starting", progress=1)

        if is_pdf:
            update_job(job_id, stage="Converting PDF to images", progress=3)
            img_dir   = job_dir / "pages"
            img_dir.mkdir(exist_ok=True)
            pages     = pdf_to_images(file_path, img_dir)
            # For now process page 1 only; multi-page can be added later
            image_path = pages[0]
        else:
            image_path = file_path

        run_pipeline(job_id, image_path, job_dir)

    except Exception as e:
        tb = traceback.format_exc()
        update_job(job_id, status="error", error=str(e) + "\n\n" + tb,
                   stage="Error")


# ── APP ───────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Pre-warm models in background so first request isn't slow
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, get_models)
    yield

app = FastAPI(title="IntelliDoc API", version="1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten for production
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/process")
async def process_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
):
    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp"}:
        raise HTTPException(400, "Unsupported file type")

    job_id  = uuid.uuid4().hex
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir()

    # Save upload
    file_path = job_dir / f"input{suffix}"
    contents  = await file.read()
    with open(file_path, "wb") as f:
        f.write(contents)

    new_job(job_id, file.filename)
    background_tasks.add_task(
        process_job, job_id, file_path, job_dir, suffix == ".pdf"
    )

    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")
    return jobs[job_id]


@app.get("/api/download/{job_id}")
async def download_docx(job_id: str):
    _require_done(job_id)
    docx_path = JOBS_DIR / job_id / "result.docx"
    if not docx_path.exists():
        raise HTTPException(404, "DOCX not ready")
    job = jobs[job_id]
    stem = Path(job["filename"]).stem
    return FileResponse(
        str(docx_path),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"{stem}_extracted.docx",
    )


@app.get("/api/download/{job_id}/md")
async def download_md(job_id: str):
    _require_done(job_id)
    md_path = JOBS_DIR / job_id / "result.md"
    if not md_path.exists():
        raise HTTPException(404, "Markdown not ready")
    stem = Path(jobs[job_id]["filename"]).stem
    return FileResponse(str(md_path), media_type="text/markdown",
                        filename=f"{stem}_extracted.md")


@app.get("/api/download/{job_id}/html")
async def download_html(job_id: str):
    _require_done(job_id)
    html_path = JOBS_DIR / job_id / "result.html"
    if not html_path.exists():
        raise HTTPException(404, "HTML not ready")
    stem = Path(jobs[job_id]["filename"]).stem
    return FileResponse(str(html_path), media_type="text/html",
                        filename=f"{stem}_extracted.html")


@app.get("/api/overlay/{job_id}")
async def get_overlay(job_id: str):
    _require_done(job_id)
    img_path = JOBS_DIR / job_id / "overlay.png"
    if not img_path.exists():
        raise HTTPException(404, "Overlay not ready")
    return FileResponse(str(img_path), media_type="image/png")


@app.get("/api/json/{job_id}")
async def get_json(job_id: str):
    _require_done(job_id)
    json_path = JOBS_DIR / job_id / "result.json"
    if not json_path.exists():
        raise HTTPException(404, "JSON not ready")
    return JSONResponse(json.loads(json_path.read_text("utf-8")))


@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: str):
    job_dir = JOBS_DIR / job_id
    if job_dir.exists():
        shutil.rmtree(job_dir)
    jobs.pop(job_id, None)
    return {"deleted": job_id}


@app.get("/health")
async def health():
    """Used by Docker healthcheck and load balancers."""
    return {
        "status": "ok",
        "models_loaded": "ready" in _models,
        "active_jobs": sum(1 for j in jobs.values() if j["status"] == "processing"),
    }


def _require_done(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")
    if jobs[job_id]["status"] != "done":
        raise HTTPException(409, f"Job not complete (status={jobs[job_id]['status']})")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)