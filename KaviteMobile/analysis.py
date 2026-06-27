"""
analysis.py — (Kutu Tabanlı Damak Modu & Tam Kalibre Genişlik Analizi)
- Çürük algılama mantıkları temizlendi ve Tam Görüntü + İzolasyon Moduna geçirildi.
- Derinlik (SFS) hesaplaması sistemden tamamen çıkarıldı.
"""

import cv2
import numpy as np
import os
import time
import torch
import base64
from segment_anything import sam_model_registry, SamPredictor

try:
    from stl_exporter import create_composite_stl
except ImportError as e:
    print(f">>> UYARI: stl_exporter modülü eksik: {e}")
    create_composite_stl = None

ARUCO_REAL_SIZE_MM = 10.0

# Çizim Renkleri (BGR)
C_MD      = (0, 0, 255)
C_BL      = (255, 0, 0)
C_ISTHMUS = (0, 255, 0)
C_MR      = (255, 0, 255)
C_CAVITY  = (0, 255, 255)
C_TOOTH   = (0, 165, 255)

T_LINE = 4
T_CONT = 4

# Dizin Yolu Düzeltmesi: Betiğin bulunduğu klasör ana dizin kabul edilecek
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

sam_checkpoint = os.path.join(BASE_DIR, "sam_vit_b_01ec64.pth")
model_type     = "vit_b"
device         = "cuda" if torch.cuda.is_available() else "cpu"

# ── Model Yükleme ─────────────────────────────────────────────────────────────
print("=========================================")
print("Yapay Zeka Modelleri Yükleniyor...")

try:
    sam = sam_model_registry[model_type](checkpoint=sam_checkpoint)
    sam.to(device=device)
    sam_predictor = SamPredictor(sam)
    print(">>> SAM AI Modeli Aktif!")
except Exception as e:
    print(f">>> HATA: SAM Yüklenemedi! ({e})")
    sam_predictor = None

print(">>> Analiz Modu: Sadece Genişlik/Alan Metrikleri (Derinlik kapalı).")
print("=========================================")

# ── Metrik Puanlama ───────────────────────────────────────────────────────────

def grade_metric(metric, value):
    value = round(float(value), 2)
    criteria = {
        "outline_form":                 [(1.58, 2.00, 10), (1.40, 1.57, 5), (2.01, 3.50, 5)],
        "mesial_isthmus_width":         [(1.50, 1.99, 10), (1.00, 1.49, 5), (2.01, 2.50, 5)],
        "distal_isthmus_width":         [(1.50, 1.99, 10), (1.00, 1.49, 5), (2.01, 2.50, 5)],
        "buccal_lingual_width":         [(2.70, 3.30, 10), (2.50, 2.69, 5), (3.31, 3.50, 5)],
        "mesio_distal_width":           [(7.10, 8.29, 10), (6.60, 7.00, 5)],
        "mesial_marginal_ridge_width":  [(1.20, 1.60, 10), (1.00, 1.19, 5), (1.61, 2.00, 5)],
        "distal_marginal_ridge_width":  [(1.20, 1.60, 10), (1.00, 1.19, 5), (1.61, 2.00, 5)]
    }
    if metric in criteria:
        for rng in criteria[metric]:
            if rng[0] <= value <= rng[1]:
                return rng[2]
    return 0

def _tooth_bbox_from_mask(mask, pad_px=20):
    ys, xs = np.where(mask > 128)
    if len(ys) == 0:
        return None
    x1 = max(0, int(xs.min()) - pad_px)
    y1 = max(0, int(ys.min()) - pad_px)
    x2 = min(mask.shape[1] - 1, int(xs.max()) + pad_px)
    y2 = min(mask.shape[0] - 1, int(ys.max()) + pad_px)
    return (x1, y1, x2, y2)

# ── SAM ile Diş + Kavite Tespiti (TAM GÖRÜNTÜ + KUTU İZOLASYONU) ──────────────

def find_cavity_with_sam(img, gray, corners, box_coords):
    if sam_predictor is None:
        return None, None

    if box_coords is None:
        print(">>> HATA: box_coords gerekli.")
        return None, None

    x1, y1, x2, y2 = [int(v) for v in box_coords]
    
    sam_predictor.set_image(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2

    masks, _, _ = sam_predictor.predict(
        box=np.array([x1, y1, x2, y2]),
        point_coords=np.array([[cx, cy]]),
        point_labels=np.array([1]),
        multimask_output=False,
    )

    raw_tooth_mask = masks[0].astype(np.uint8) * 255

    isolation_mask = np.zeros(img.shape[:2], dtype=np.uint8)
    isolation_mask[y1:y2, x1:x2] = 255
    tooth_mask = cv2.bitwise_and(raw_tooth_mask, isolation_mask)

    search_mask = tooth_mask.copy()
    if corners is not None and len(corners) > 0:
        for c in corners:
            pts = c[0].astype(np.int32)
            bx, by, bw, bh = cv2.boundingRect(pts)
            PAD = 30
            search_mask[max(0, by - PAD):min(search_mask.shape[0], by + bh + PAD),
                        max(0, bx - PAD):min(search_mask.shape[1], bx + bw + PAD)] = 0

    tooth_mask_clean = tooth_mask
    if cv2.countNonZero(search_mask) < 100:
        search_mask = tooth_mask_clean.copy()

    blurred     = gray.copy()
    masked_gray = blurred.copy()
    masked_gray[search_mask == 0] = 255

    dark_pixels = masked_gray[search_mask > 0]
    if len(dark_pixels) == 0:
        return None, tooth_mask

    threshold_val = np.percentile(dark_pixels, 5)
    dark_region   = ((masked_gray <= threshold_val) & (search_mask > 0)).astype(np.uint8) * 255

    M = cv2.moments(dark_region)
    if M["m00"] > 0:
        cav_cx = int(M["m10"] / M["m00"])
        cav_cy = int(M["m01"] / M["m00"])
    else:
        _, _, min_loc, _ = cv2.minMaxLoc(masked_gray, mask=search_mask)
        cav_cx, cav_cy   = min_loc[0], min_loc[1]

    point_coords_list = [[cav_cx, cav_cy]]
    point_labels_list = [1]

    if corners is not None:
        for c in corners:
            M2 = cv2.moments(c[0])
            if M2["m00"] != 0:
                point_coords_list.append([int(M2["m10"] / M2["m00"]), int(M2["m01"] / M2["m00"])])
                point_labels_list.append(0)

    c_masks, _, _ = sam_predictor.predict(
        point_coords=np.array(point_coords_list),
        point_labels=np.array(point_labels_list),
        multimask_output=False,
    )

    best_cavity = c_masks[0].astype(np.uint8) * 255
    cavity_mask = cv2.bitwise_and(best_cavity, tooth_mask_clean)

    return cavity_mask, tooth_mask

# ── Ana Analiz Fonksiyonu ─────────────────────────────────────────────────────

def analyze_dental_images(path_90, output_folder, f_90, box_coords):
    img_90 = cv2.imread(path_90)
    if img_90 is None:
        return {"error": "Fotoğraf okunamadı."}

    h, w = img_90.shape[:2]
    scale = 1.0
    if w > 1000:
        scale  = 1000.0 / float(w)
        img_90 = cv2.resize(img_90, (1000, int(h * scale)))
        if box_coords is not None:
            box_coords = [v * scale for v in box_coords]

    gray_90  = cv2.cvtColor(img_90, cv2.COLOR_BGR2GRAY)
    detector = cv2.aruco.ArucoDetector(
        cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50),
        cv2.aruco.DetectorParameters()
    )
    corners, ids, _ = detector.detectMarkers(gray_90)
    aruco_90_found = len(corners) > 0

    if aruco_90_found:
        cv2.aruco.drawDetectedMarkers(img_90, corners, ids)

    mm_per_px = float(
        ARUCO_REAL_SIZE_MM / (sum([cv2.arcLength(c[0], True) / 4.0 for c in corners]) / len(corners))
    ) if aruco_90_found else 0.05

    result_tuple = find_cavity_with_sam(img_90, gray_90, corners, box_coords=box_coords)
    if result_tuple is None or len(result_tuple) < 2:
        cav_mask = tooth_mask = None
    else:
        cav_mask, tooth_mask = result_tuple

    if box_coords is not None:
        bx1, by1, bx2, by2 = [int(v) for v in box_coords]
        cv2.rectangle(img_90, (bx1, by1), (bx2, by2), (255, 200, 0), 2, cv2.LINE_AA)

    if tooth_mask is not None:
        bbox = _tooth_bbox_from_mask(tooth_mask, pad_px=6)
        if bbox:
            cv2.rectangle(img_90, (bbox[0], bbox[1]), (bbox[2], bbox[3]), (0, 200, 255), 2, cv2.LINE_AA)

    unique_timestamp = str(int(time.time()))
    drawn_90_name    = f"drawn_90_{unique_timestamp}_{f_90}"
    stl_output_name  = f"model_{unique_timestamp}_{f_90.split('.')[0]}.stl"
    stl_path         = os.path.join(output_folder, stl_output_name)

    metrics = {k: 0.0 for k in [
        "mesio_distal_width", "buccal_lingual_width",
        "mesial_isthmus_width", "distal_isthmus_width",
        "mesial_marginal_ridge_width", "distal_marginal_ridge_width",
        "outline_form"
    ]}

    if cav_mask is not None and tooth_mask is not None:
        measurement_mask = cav_mask

        c_contours, _ = cv2.findContours(measurement_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        t_contours, _ = cv2.findContours(tooth_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(img_90, c_contours, -1, C_CAVITY, T_CONT)
        cv2.drawContours(img_90, t_contours, -1, C_TOOTH,  T_CONT)

        cx_m, cy_m, cw_m, ch_m = cv2.boundingRect(measurement_mask)
        mid_y = cy_m + ch_m // 2
        P = 3

        c_row = np.where(measurement_mask[mid_y, :] > 0)[0]
        t_row = np.where(tooth_mask[mid_y, :] > 0)[0]

        if len(c_row) > 0 and len(t_row) > 0:
            c_start, c_end = c_row[0],  c_row[-1]
            t_start, t_end = t_row[0],  t_row[-1]

            if c_end - c_start > 2 * P:
                cv2.line(img_90, (c_start + P, mid_y), (c_end - P, mid_y), C_MD, T_LINE)
            if c_start - t_start > 2 * P:
                cv2.line(img_90, (t_start + P, mid_y), (c_start - P, mid_y), C_MR, T_LINE)
            if t_end - c_end > 2 * P:
                cv2.line(img_90, (c_end + P, mid_y), (t_end - P, mid_y), C_MR, T_LINE)

            metrics["mesio_distal_width"]          = (c_end - c_start) * mm_per_px
            metrics["mesial_marginal_ridge_width"] = (c_start - t_start) * mm_per_px
            metrics["distal_marginal_ridge_width"] = (t_end - c_end) * mm_per_px

        widths_px = []
        for x in range(cx_m, cx_m + cw_m):
            y_pixels = np.where(measurement_mask[:, x] > 0)[0]
            if len(y_pixels) > 0:
                widths_px.append((y_pixels[-1] - y_pixels[0], x, y_pixels[0], y_pixels[-1]))

        if widths_px:
            max_item = max(widths_px, key=lambda item: item[0])
            metrics["buccal_lingual_width"] = max_item[0] * mm_per_px
            if max_item[3] - max_item[2] > 2 * P:
                cv2.line(img_90, (max_item[1], max_item[2] + P), (max_item[1], max_item[3] - P), C_BL, T_LINE)

            mesial_cands = [it for it in widths_px if (cx_m + cw_m * 0.25) <= it[1] <= (cx_m + cw_m * 0.40)]
            distal_cands = [it for it in widths_px if (cx_m + cw_m * 0.60) <= it[1] <= (cx_m + cw_m * 0.75)]

            if mesial_cands:
                ist_m = min(mesial_cands, key=lambda it: it[0])
                metrics["mesial_isthmus_width"] = ist_m[0] * mm_per_px
                if ist_m[3] - ist_m[2] > 2 * P:
                    cv2.line(img_90, (ist_m[1], ist_m[2] + P), (ist_m[1], ist_m[3] - P), C_ISTHMUS, T_LINE)

            if distal_cands:
                ist_d = min(distal_cands, key=lambda it: it[0])
                metrics["distal_isthmus_width"] = ist_d[0] * mm_per_px
                if ist_d[3] - ist_d[2] > 2 * P:
                    cv2.line(img_90, (ist_d[1], ist_d[2] + P), (ist_d[1], ist_d[3] - P), C_ISTHMUS, T_LINE)

        if (metrics["mesial_isthmus_width"] + metrics["distal_isthmus_width"]) > 0:
            metrics["outline_form"] = metrics["buccal_lingual_width"] / ((metrics["mesial_isthmus_width"] + metrics["distal_isthmus_width"]) / 2)

    stl_success = False
    if create_composite_stl is not None and cav_mask is not None and tooth_mask is not None:
        stl_success = create_composite_stl(
            tooth_mask=tooth_mask,
            cav_mask=cav_mask,
            mm_per_px=mm_per_px,
            output_path=stl_path,
            cavity_depth=1.50 # STL için sabit görsel derinlik
        )

    cv2.imwrite(os.path.join(output_folder, drawn_90_name), img_90)
    _, buffer  = cv2.imencode('.jpg', img_90, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
    img_base64 = base64.b64encode(buffer).decode('utf-8')

    res = {
        **metrics,
        "drawn_90":       drawn_90_name,
        "stl_file":       stl_output_name if stl_success else None,
        "base64_image":   img_base64,
        "aruco_90_found": aruco_90_found,
    }

    res.update({f"{k}_score": int(grade_metric(k, v)) for k, v in metrics.items()})

    fatal_error = None
    if metrics["buccal_lingual_width"] > 3.50:
        fatal_error = "Kavitenin B-L boyutunun çok geniş olması (> 3.50mm)"

    res["total_score"] = 0 if fatal_error else int(sum([v for k, v in res.items() if "_score" in k]))
    res["fatal_error"] = fatal_error
    return res