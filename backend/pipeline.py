"""
pipeline.py — IntelliDoc core pipeline functions
=================================================
Extracted from intellidoc_v9.py so FastAPI can import them cleanly.
All functions are pure (no global state) except get_models() which caches.
"""

import cv2
import numpy as np

# ── CONSTANTS ─────────────────────────────────────────────────────────────────
BORDER_FRAC     = 0.60
BORDER_MIN_DARK = 80
DATA_ROW_SKIP   = 2
COL_GAP_DIVISOR = 60
COL_EDGE_MARGIN = 25
CELL_UPSCALE    = 4
CELL_TARGET_H   = 60
CELL_PAD        = 3
TEXT_MIN_H      = 40
TEXT_UPSCALE    = 2
KDE_BW          = 18
KDE_RANGE       = (0.30, 0.70)
KDE_MIN_WORDS   = 40
LINE_Y_MERGE    = 14
BLOCK_GAP_MAX   = 32
BLOCK_X_OV      = 0.15
DEDUP_IOU       = 0.80


# ── UTILS ─────────────────────────────────────────────────────────────────────

def clamp(x1, y1, x2, y2, W, H):
    return (max(0, min(int(x1), W-1)), max(0, min(int(y1), H-1)),
            max(0, min(int(x2), W)),   max(0, min(int(y2), H)))

def quad_to_bbox(q):
    xs = [p[0] for p in q]; ys = [p[1] for p in q]
    return int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))

def iou(a, b):
    ix1=max(a[0],b[0]); iy1=max(a[1],b[1])
    ix2=min(a[2],b[2]); iy2=min(a[3],b[3])
    inter = max(0,ix2-ix1)*max(0,iy2-iy1)
    if inter == 0: return 0.0
    return inter / max(1,(a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-inter)

def x_ov(a, b):
    ov = max(0, min(a[2],b[2]) - max(a[0],b[0]))
    return ov / max(1, min(a[2]-a[0], b[2]-b[0]))

def union_bb(a, b):
    return [min(a[0],b[0]), min(a[1],b[1]), max(a[2],b[2]), max(a[3],b[3])]

def bcx(b): return (b[0]+b[2]) / 2.0
def bcy(b): return (b[1]+b[3]) / 2.0

def in_table_check(word_bbox, tbl_bboxes):
    wcx = bcx(word_bbox); wcy = bcy(word_bbox)
    for tx1,ty1,tx2,ty2 in tbl_bboxes:
        if tx1 <= wcx <= tx2 and ty1 <= wcy <= ty2:
            return True
    return False


# ── PREPROCESSING ─────────────────────────────────────────────────────────────

def preprocess(bgr):
    gray  = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    noise = float(cv2.absdiff(gray, cv2.GaussianBlur(gray,(3,3),0)).mean())
    if noise > 15.0:
        return cv2.fastNlMeansDenoisingColored(bgr, None, 5, 5, 7, 21)
    return bgr.copy()

def upscale_crop(crop, target_h=CELL_TARGET_H, factor=CELL_UPSCALE):
    h, w = crop.shape[:2]
    if h == 0 or w == 0: return crop
    s = max(factor, int(np.ceil(target_h / max(h,1))))
    return cv2.resize(crop, (w*s, h*s), interpolation=cv2.INTER_LANCZOS4)


# ── PPSTRUCTURE SCALE FIX ─────────────────────────────────────────────────────

def get_ppstruct_scale(page_shape, ppstruct_result):
    """Detect if PPStructure internally rescaled. Returns (sx, sy) to correct coords."""
    H_orig, W_orig = page_shape[:2]
    all_x2 = [int(blk["bbox"][2]) for blk in ppstruct_result if blk.get("bbox")]
    all_y2 = [int(blk["bbox"][3]) for blk in ppstruct_result if blk.get("bbox")]
    if not all_x2: return 1.0, 1.0
    max_x = max(all_x2); max_y = max(all_y2)
    sx = W_orig / max_x if max_x > W_orig else 1.0
    sy = H_orig / max_y if max_y > H_orig else 1.0
    if abs(sx-1.0) < 0.05: sx = 1.0
    if abs(sy-1.0) < 0.05: sy = 1.0
    return sx, sy

def scale_bbox(bbox, sx, sy):
    x1,y1,x2,y2 = bbox
    return [int(x1*sx), int(y1*sy), int(x2*sx), int(y2*sy)]


# ── TABLE: ROW DETECTION ──────────────────────────────────────────────────────

def detect_rows(gray, bbox):
    x1, y1, x2, y2 = bbox
    table_w = x2 - x1
    H = gray.shape[0]
    search_y2 = min(H, y2 + 300)
    region = gray[y1:search_y2, x1:x2]
    _, bw  = cv2.threshold(region, 180, 255, cv2.THRESH_BINARY_INV)
    h_proj = bw.sum(axis=1).astype(np.int64)
    border_min = int(table_w * 255 * BORDER_FRAC)

    is_border = [int(h_proj[i]) >= border_min for i in range(len(h_proj))]
    border_groups = []
    in_b = False; bs = 0
    for i, b in enumerate(is_border):
        if b and not in_b:     bs=i; in_b=True
        elif not b and in_b:   border_groups.append((bs, i-1)); in_b=False
    if in_b: border_groups.append((bs, len(is_border)-1))

    border_ys = [y1 + (g[0]+g[1])//2 for g in border_groups]

    if len(border_ys) < 2:
        return _detect_rows_fallback(gray, bbox), [], y2

    row_bands = []
    for bi in range(len(border_groups)-1):
        seg_start = border_groups[bi][1] + 1
        seg_end   = border_groups[bi+1][0] - 1
        if seg_end <= seg_start: continue
        seg_proj = h_proj[seg_start:seg_end+1]
        text_thresh = max(50, table_w // 8)
        in_band=False; ts=0
        for i in range(len(seg_proj)):
            has = int(seg_proj[i]) > text_thresh
            if has and not in_band: ts=i; in_band=True
            elif not has and in_band:
                if i-ts > 3:
                    row_bands.append((y1+seg_start+ts, y1+seg_start+i-1))
                in_band=False
        if in_band and (len(seg_proj)-ts) > 3:
            row_bands.append((y1+seg_start+ts, y1+seg_start+len(seg_proj)-1))

    real_y2 = y1 + border_groups[-1][1] + 1
    return row_bands, border_ys, real_y2

def _detect_rows_fallback(gray, bbox):
    x1,y1,x2,y2 = bbox
    region = gray[y1:y2, x1:x2]
    _, bw  = cv2.threshold(region, 180, 255, cv2.THRESH_BINARY_INV)
    h_proj = bw.sum(axis=1).astype(np.int64)
    thresh = max(200, (x2-x1)//8)
    bands=[]; in_b=False; s=0
    for i in range(len(h_proj)):
        has = int(h_proj[i]) > thresh
        if has and not in_b: s=i; in_b=True
        elif not has and in_b:
            if i-s > 3: bands.append((y1+s, y1+i-1))
            in_b=False
    if in_b and len(h_proj)-s > 3: bands.append((y1+s, y1+len(h_proj)-1))
    return bands


# ── TABLE: COLUMN DETECTION ───────────────────────────────────────────────────

def detect_cols(gray, bbox, row_bands):
    x1,y1,x2,y2 = bbox
    W = x2 - x1
    data_rows = row_bands[DATA_ROW_SKIP:] if len(row_bands) > DATA_ROW_SKIP else row_bands
    if not data_rows: data_rows = row_bands

    combined = np.zeros(W, dtype=np.int64)
    for ry1,ry2 in data_rows:
        row = gray[ry1:ry2, x1:x2]
        if row.shape[0] == 0: continue
        _, bw = cv2.threshold(row, 180, 255, cv2.THRESH_BINARY_INV)
        combined += bw.sum(axis=0).astype(np.int64)

    gap_min = max(8, W // COL_GAP_DIVISOR)
    all_gaps = []
    in_g=False; gs=0
    for i in range(W):
        iz = int(combined[i]) == 0
        if iz and not in_g: gs=i; in_g=True
        elif not iz and in_g:
            gw=i-gs
            if gw >= gap_min: all_gaps.append((gs,i-1,gw))
            in_g=False
    if in_g and W-gs >= gap_min: all_gaps.append((gs,W-1,W-gs))

    inner = [(gs,ge,gw) for gs,ge,gw in all_gaps
             if gs > COL_EDGE_MARGIN and ge < W - COL_EDGE_MARGIN]
    inner.sort(key=lambda x: x[0])

    boundaries = [0] + [(gs+ge)//2 for gs,ge,gw in inner] + [W]
    return [(x1+boundaries[i], x1+boundaries[i+1]) for i in range(len(boundaries)-1)]


# ── TABLE: CELL OCR ───────────────────────────────────────────────────────────

def ocr_cell(ocr_engine, bgr, ax1, ay1, ax2, ay2):
    H,W = bgr.shape[:2]
    crop = bgr[max(0,ay1-CELL_PAD):min(H,ay2+CELL_PAD),
               max(0,ax1-CELL_PAD):min(W,ax2+CELL_PAD)]
    if crop.shape[0] < 2 or crop.shape[1] < 2: return ""
    crop_up = upscale_crop(crop)
    res = ocr_engine.ocr(crop_up, cls=True)
    if res and res[0]:
        return " ".join(it[1][0] for it in res[0] if it[1][0].strip()).strip()
    return ""


# ── TABLE: FULL EXTRACTION ────────────────────────────────────────────────────

def extract_table(ocr_engine, gray, bgr, ppstruct_bbox):
    H_page, W_page = bgr.shape[:2]
    x1,y1,x2,y2   = ppstruct_bbox

    row_bands, border_ys, real_y2 = detect_rows(gray, [x1,y1,x2,y2])
    real_bbox  = [x1, y1, x2, real_y2]
    col_ranges = detect_cols(gray, [x1,y1,x2,y2], row_bands)

    if not row_bands or not col_ranges:
        return {"matrix":[],"rows":[],"cols":[],"cells":[],"real_bbox":real_bbox}

    matrix=[]; cells=[]
    for ri,(ry1,ry2) in enumerate(row_bands):
        row_texts=[]
        for ci,(cx1,cx2) in enumerate(col_ranges):
            txt = ocr_cell(ocr_engine, bgr, cx1, ry1, cx2, ry2)
            row_texts.append(txt)
            cells.append({"label":"table cell","score":1.0,
                          "bbox":[cx1,ry1,cx2,ry2],
                          "text":txt,"row":ri,"col":ci})
        matrix.append(row_texts)

    return {
        "matrix":    matrix,
        "rows":      [(ry1+ry2)//2 for ry1,ry2 in row_bands],
        "cols":      [(cx1+cx2)//2 for cx1,cx2 in col_ranges],
        "cells":     cells,
        "real_bbox": real_bbox,
    }


# ── TEXT OCR ──────────────────────────────────────────────────────────────────

def ocr_region(ocr_engine, bgr, x1, y1, x2, y2):
    H,W = bgr.shape[:2]
    x1,y1,x2,y2 = clamp(x1,y1,x2,y2,W,H)
    crop = bgr[y1:y2, x1:x2]; h,w = crop.shape[:2]
    if h < 4 or w < 4: return []
    if h < TEXT_MIN_H:
        s = max(TEXT_UPSCALE, int(np.ceil(TEXT_MIN_H/max(h,1))))
        crop = cv2.resize(crop,(w*s,h*s),interpolation=cv2.INTER_LANCZOS4)
        sx=w*s/max(w,1); sy=h*s/max(h,1)
    else:
        sx=sy=1.0
    res = ocr_engine.ocr(crop, cls=True)
    if not (res and res[0]): return []
    words=[]
    for it in res[0]:
        txt=it[1][0].strip(); conf=float(it[1][1])
        if not txt: continue
        bx1,by1,bx2,by2 = quad_to_bbox(it[0])
        words.append({"text":txt,"conf":conf,
                      "bbox":[int(bx1/sx)+x1,int(by1/sy)+y1,
                               int(bx2/sx)+x1,int(by2/sy)+y1]})
    return words

def words_to_lines(words):
    if not words: return []
    lines=[]; cur=[words[0]]; yc=bcy(words[0]["bbox"])
    for w in words[1:]:
        wy=bcy(w["bbox"])
        if abs(wy-yc)<=LINE_Y_MERGE: cur.append(w); yc=sum(bcy(x["bbox"]) for x in cur)/len(cur)
        else: lines.append(cur); cur=[w]; yc=wy
    lines.append(cur)
    out=[]
    for ws in lines:
        ws=sorted(ws,key=lambda x:x["bbox"][0])
        bb=ws[0]["bbox"][:]
        for x in ws[1:]: bb=union_bb(bb,x["bbox"])
        out.append({"bbox":bb,"conf":float(np.mean([x["conf"] for x in ws])),
                    "text":" ".join(x["text"] for x in ws).strip()})
    return sorted(out,key=lambda ln:(ln["bbox"][1],ln["bbox"][0]))

def lines_to_blocks(lines):
    if not lines: return []
    blocks=[]; cur=[lines[0]]; cur_bb=lines[0]["bbox"][:]
    for ln in lines[1:]:
        last=cur[-1]; gap=ln["bbox"][1]-last["bbox"][3]; ov=x_ov(cur_bb,ln["bbox"])
        if -2<=gap<=BLOCK_GAP_MAX and (ov>=BLOCK_X_OV or last["text"].rstrip().endswith("-")):
            cur.append(ln); cur_bb=union_bb(cur_bb,ln["bbox"])
        else: blocks.append({"bbox":cur_bb,"lines":cur}); cur=[ln]; cur_bb=ln["bbox"][:]
    blocks.append({"bbox":cur_bb,"lines":cur})
    return blocks


# ── KDE COLUMN INFERENCE ──────────────────────────────────────────────────────

def _kde(xs, grid, bw):
    d = np.zeros(len(grid))
    for x in xs: d += np.exp(-0.5*((grid-x)/bw)**2)
    return d / (len(xs)*bw*np.sqrt(2*np.pi))

def estimate_cols_kde(words, page_w):
    if len(words) < KDE_MIN_WORDS: return None
    xs = np.array([bcx(w["bbox"]) for w in words])
    grid = np.linspace(0, page_w, 800); density = _kde(xs, grid, KDE_BW)
    lo=int(KDE_RANGE[0]*800); hi=int(KDE_RANGE[1]*800)
    vl=int(np.argmin(density[lo:hi]))+lo
    vx=float(grid[vl]); vd=float(density[vl])
    lp=float(density[:vl].max()) if vl>0 else 0
    rp=float(density[vl:].max()) if vl<800 else 0
    mp=(lp+rp)/2.0
    if mp==0: return None
    conf=float(max(0,min(1,1-vd/mp)))
    if conf<0.35: return None
    lxs=xs[xs<vx]; rxs=xs[xs>=vx]
    if len(lxs)<10 or len(rxs)<10: return None
    return {"gutter":[float(max(0,vx-KDE_BW)),float(min(page_w,vx+KDE_BW))],
            "left_range":[float(np.percentile(lxs,5)),float(np.percentile(lxs,95))],
            "right_range":[float(np.percentile(rxs,5)),float(np.percentile(rxs,95))],
            "conf":conf}

def classify(bbox, cols, page_w):
    x1,_,x2,__=bbox
    if cols and cols.get("conf",0)>=0.35:
        L1,L2=cols["left_range"]; R1,R2=cols["right_range"]
        ovL=max(0,min(x2,L2)-max(x1,L1))/max(1,L2-L1)
        ovR=max(0,min(x2,R2)-max(x1,R1))/max(1,R2-R1)
        if ovL>=0.30 and ovR>=0.30: return "full"
        return "left" if ovL>=ovR else "right"
    return "left" if bcx(bbox)<page_w/2.0 else "right"


# ── READING ORDER ─────────────────────────────────────────────────────────────

def is_footnote(u, page_h):
    if u.get("type")=="reference": return True
    if u["bbox"][1]>page_h*0.88 and len(u.get("text","").strip().split("\n"))<=5: return True
    return False

def reading_order(units, page_h):
    sk=lambda u:(u["bbox"][1],u["bbox"][0])
    fulls=sorted([u for u in units if u["kind"]=="full"],key=sk)
    lefts=sorted([u for u in units if u["kind"]=="left"],key=sk)
    rights=sorted([u for u in units if u["kind"]=="right"],key=sk)
    ordered=[]; prev_y=-1
    for f in fulls:
        fy1=f["bbox"][1]
        pre_l=[u for u in lefts  if prev_y<=u["bbox"][1]<fy1]
        pre_r=[u for u in rights if prev_y<=u["bbox"][1]<fy1]
        lefts =[u for u in lefts  if u not in pre_l]
        rights=[u for u in rights if u not in pre_r]
        ordered.extend(sorted(pre_l,key=sk)); ordered.extend(sorted(pre_r,key=sk))
        ordered.append(f); prev_y=f["bbox"][3]
    ordered.extend(sorted(lefts+rights,key=sk))
    body=[u for u in ordered if not is_footnote(u,page_h)]
    feet=[u for u in ordered if     is_footnote(u,page_h)]
    final=body+feet
    for i,u in enumerate(final,1): u["order"]=i
    return final

def dedup(units):
    keep=[True]*len(units)
    for i in range(len(units)):
        if not keep[i]: continue
        for j in range(i+1,len(units)):
            if not keep[j]: continue
            if iou(units[i]["bbox"],units[j]["bbox"])>=DEDUP_IOU:
                li=len(units[i].get("text","")); lj=len(units[j].get("text",""))
                if li>=lj: keep[j]=False
                else: keep[i]=False; break
    return [u for u,k in zip(units,keep) if k]


# ── OVERLAY ───────────────────────────────────────────────────────────────────

def draw_overlay(page, units, cols_est):
    ov=page.copy()
    if cols_est:
        gL,gR=int(cols_est["gutter"][0]),int(cols_est["gutter"][1])
        cv2.rectangle(ov,(gL,0),(gR,page.shape[0]),(180,180,180),1)
    C={"full":(0,165,255),"left":(0,200,0),"right":(200,0,0)}
    for u in units:
        kind=u.get("kind","full"); col=C.get(kind,(128,128,128))
        bx1,by1,bx2,by2=map(int,u["bbox"])
        cv2.rectangle(ov,(bx1,by1),(bx2,by2),col,2)
        cv2.putText(ov,f"{u.get('order',0)}:{u.get('type','?')[:4]}:{kind[0]}",
                    (bx1,max(14,by1-4)),cv2.FONT_HERSHEY_SIMPLEX,0.42,col,1,cv2.LINE_AA)
    return ov
