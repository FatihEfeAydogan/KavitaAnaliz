import cv2
import numpy as np
import os
import time
import torch
import base64
from segment_anything import sam_model_registry, SamPredictor


try:
    from stl_exporter import create_composite_stl, DEFAULT_CAVITY_DEPTH_MM
except ImportError as e:
    print(f">>> UYARI: stl_exporter modülü veya gerekli kütüphaneler (trimesh/skimage/scipy) eksik: {e}")
    create_composite_stl = None
    DEFAULT_CAVITY_DEPTH_MM = 3.16

ARUCO_REAL_SIZE_MM = 10.0

# Çizim Renkleri (BGR formatında)
C_MD = (0, 0, 255)       
C_BL = (255, 0, 0)       
C_ISTHMUS = (0, 255, 0)  
C_MR = (255, 0, 255)     
C_CAVITY = (0, 255, 255) 
C_TOOTH = (0, 165, 255)  

T_LINE = 1  
T_CONT = 1

CURRENT_DIR = os.path.abspath(os.getcwd())
if "KaviteIRLScale" not in CURRENT_DIR:
    BASE_DIR = os.path.join(CURRENT_DIR, 'KaviteIRLScale')
else:
    BASE_DIR = CURRENT_DIR

sam_checkpoint = os.path.join(BASE_DIR, "sam_vit_b_01ec64.pth")
model_type = "vit_b"
device = "cuda" if torch.cuda.is_available() else "cpu"

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

print(">>> Derinlik: RGB & SFS Hibrit yöntemi aktif.")
print("=========================================")

def grade_metric(metric, value):
    value = round(float(value), 2)
    criteria = {
        "outline_form": [(1.58, 2.00, 10), (1.40, 1.57, 5), (2.01, 3.50, 5)],
        "mesial_isthmus_width": [(1.50, 1.99, 10), (1.00, 1.49, 5), (2.01, 2.50, 5)],
        "distal_isthmus_width": [(1.50, 1.99, 10), (1.00, 1.49, 5), (2.01, 2.50, 5)],
        "buccal_lingual_width": [(2.70, 3.30, 10), (2.50, 2.69, 5), (3.31, 3.50, 5)],
        "mesio_distal_width": [(7.10, 8.29, 10), (6.60, 7.00, 5)],
        "mesial_marginal_ridge_width": [(1.20, 1.60, 10), (1.00, 1.19, 5), (1.61, 2.00, 5)],
        "distal_marginal_ridge_width": [(1.20, 1.60, 10), (1.00, 1.19, 5), (1.61, 2.00, 5)],
        "depth": [(2.50, 3.00, 10), (2.00, 2.49, 5), (3.01, 3.49, 5)] 
    }
    if metric in criteria:
        for rng in criteria[metric]:
            if rng[0] <= value <= rng[1]: return rng[2]
    return 0

def find_cavity_with_sam(img, gray, corners):
    if sam_predictor is None: return None, None
    blur = cv2.GaussianBlur(gray, (11, 11), 0)
    _, thresh = cv2.threshold(blur, 130, 255, cv2.THRESH_BINARY)
    kernel = np.ones((9,9), np.uint8)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

    marker_centers = []
    if corners is not None:
        for c in corners:
            M = cv2.moments(c[0])
            if M["m00"] != 0: marker_centers.append((int(M["m10"]/M["m00"]), int(M["m01"]/M["m00"])))

    h_img, w_img = gray.shape
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best_tooth_box = None
    max_area = 0

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 400 or area > (h_img * w_img * 0.35): continue
        tx, ty, tw, th = cv2.boundingRect(cnt)
        is_paper = any(tx-30 <= mx <= tx+tw+30 and ty-30 <= my <= ty+th+30 for mx, my in marker_centers)
        if not is_paper and area > max_area:
            max_area = area
            best_tooth_box = np.array([tx, ty, tx+tw, ty+th])

    if best_tooth_box is None: return None, None

    sam_predictor.set_image(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    t_masks, _, _ = sam_predictor.predict(box=best_tooth_box, multimask_output=False)
    tooth_mask = (t_masks[0]).astype(np.uint8) * 255
    
    masked_gray = gray.copy()
    masked_gray[tooth_mask == 0] = 255 
    min_val, _, min_loc, _ = cv2.minMaxLoc(cv2.GaussianBlur(masked_gray, (15,15), 0), mask=tooth_mask) 
    
    c_masks, _, _ = sam_predictor.predict(point_coords=np.array([[min_loc[0], min_loc[1]]]), point_labels=np.array([1]), multimask_output=False)
    cavity_mask = (c_masks[0]).astype(np.uint8) * 255
    
    cavity_mask = cv2.erode(cavity_mask, np.ones((3,3), np.uint8), iterations=1)
    cavity_mask = cv2.bitwise_and(cavity_mask, tooth_mask)

    return cavity_mask, tooth_mask

def analyze_dental_images(path_90, output_folder, f_90):
    img_90 = cv2.imread(path_90)
    if img_90 is None: return {"error": "90 derece oklüzal görsel okunamadı."}
    
    h, w = img_90.shape[:2]
    if w > 1000:
        scale = 1000.0 / float(w)
        img_90 = cv2.resize(img_90, (1000, int(h * scale)))
    
    gray_90 = cv2.cvtColor(img_90, cv2.COLOR_BGR2GRAY)
    detector = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50), cv2.aruco.DetectorParameters())
    corners, ids, _ = detector.detectMarkers(gray_90)
    
    aruco_90_found = len(corners) > 0
    if aruco_90_found:
        cv2.aruco.drawDetectedMarkers(img_90, corners, ids)
            
    mm_per_px = float(ARUCO_REAL_SIZE_MM / (sum([cv2.arcLength(c[0], True)/4.0 for c in corners])/len(corners))) if aruco_90_found else 0.05

    cav_mask, tooth_mask = find_cavity_with_sam(img_90, gray_90, corners)
    
    unique_timestamp = str(int(time.time()))
    drawn_90_name = f"drawn_90_{unique_timestamp}_{f_90}"
    stl_output_name = f"model_{unique_timestamp}_{f_90.split('.')[0]}.stl"
    stl_path = os.path.join(output_folder, stl_output_name)

    metrics = {k: 0.0 for k in ["mesio_distal_width", "buccal_lingual_width", "mesial_isthmus_width", "distal_isthmus_width", "mesial_marginal_ridge_width", "distal_marginal_ridge_width", "outline_form", "depth"]}
    
    if cav_mask is not None and tooth_mask is not None:
        c_contours, _ = cv2.findContours(cav_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        t_contours, _ = cv2.findContours(tooth_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        cv2.drawContours(img_90, c_contours, -1, C_CAVITY, T_CONT)
        cv2.drawContours(img_90, t_contours, -1, C_TOOTH, T_CONT)

        cx, cy, cw, ch = cv2.boundingRect(cav_mask)
        mid_y, mid_x = cy + ch // 2, cx + cw // 2
        c_row = np.where(cav_mask[mid_y, :] > 0)[0]
        t_row = np.where(tooth_mask[mid_y, :] > 0)[0]
        P = 3 

        # Mesio-Distal ve Ridge Genişlikleri
        if len(c_row) > 0 and len(t_row) > 0:
            c_start, c_end = c_row[0], c_row[-1]
            t_start, t_end = t_row[0], t_row[-1]
            
            if c_end - c_start > 2*P: cv2.line(img_90, (c_start + P, mid_y), (c_end - P, mid_y), C_MD, T_LINE)
            if c_start - t_start > 2*P: cv2.line(img_90, (t_start + P, mid_y), (c_start - P, mid_y), C_MR, T_LINE)
            if t_end - c_end > 2*P: cv2.line(img_90, (c_end + P, mid_y), (t_end - P, mid_y), C_MR, T_LINE)

            metrics["mesio_distal_width"] = (c_end - c_start) * mm_per_px
            metrics["mesial_marginal_ridge_width"] = (c_start - t_start) * mm_per_px
            metrics["distal_marginal_ridge_width"] = (t_end - c_end) * mm_per_px

        widths_px = []
        for x in range(cx, cx + cw):
            y_pixels = np.where(cav_mask[:, x] > 0)[0]
            if len(y_pixels) > 0: widths_px.append((y_pixels[-1] - y_pixels[0], x, y_pixels[0], y_pixels[-1]))

        # Buccal-Lingual ve Isthmus Genişlikleri
        if widths_px:
            max_item = max(widths_px, key=lambda item: item[0])
            metrics["buccal_lingual_width"] = max_item[0] * mm_per_px
            if max_item[3] - max_item[2] > 2*P: cv2.line(img_90, (max_item[1], max_item[2] + P), (max_item[1], max_item[3] - P), C_BL, T_LINE)

            mesial_cands = [item for item in widths_px if (cx + cw*0.25) <= item[1] <= (cx + cw*0.40)]
            distal_cands = [item for item in widths_px if (cx + cw*0.60) <= item[1] <= (cx + cw*0.75)]

            if mesial_cands:
                ist_m_item = min(mesial_cands, key=lambda item: item[0])
                metrics["mesial_isthmus_width"] = ist_m_item[0] * mm_per_px
                if ist_m_item[3] - ist_m_item[2] > 2*P: cv2.line(img_90, (ist_m_item[1], ist_m_item[2] + P), (ist_m_item[1], ist_m_item[3] - P), C_ISTHMUS, T_LINE)

            if distal_cands:
                ist_d_item = min(distal_cands, key=lambda item: item[0])
                metrics["distal_isthmus_width"] = ist_d_item[0] * mm_per_px
                if ist_d_item[3] - ist_d_item[2] > 2*P: cv2.line(img_90, (ist_d_item[1], ist_d_item[2] + P), (ist_d_item[1], ist_d_item[3] - P), C_ISTHMUS, T_LINE)

        if (metrics["mesial_isthmus_width"] + metrics["distal_isthmus_width"]) > 0:
            metrics["outline_form"] = metrics["buccal_lingual_width"] / ((metrics["mesial_isthmus_width"] + metrics["distal_isthmus_width"])/2)

    # ── Dinamik Derinlik Kestirimi (RGB & SFS Hibrit) ───────────────────
    dynamic_depth_mm = DEFAULT_CAVITY_DEPTH_MM

    if cav_mask is not None and tooth_mask is not None:
        try:
            intact_tooth_mask = cv2.subtract(tooth_mask, cav_mask)

            # Gauss bulanıklaştırma → speküler parlama ve gürültü azaltma
            gray_blur = cv2.GaussianBlur(gray_90, (7, 7), 0)

            surface_pixels = gray_blur[intact_tooth_mask > 0].astype(np.float32)
            cavity_pixels  = gray_blur[cav_mask > 0].astype(np.float32)

            if len(surface_pixels) > 50 and len(cavity_pixels) > 50:
                # En parlak %20'yi dışla → speküler parlama etkisini azalt
                surf_thresh  = np.percentile(surface_pixels, 80)
                surface_mean = np.mean(surface_pixels[surface_pixels <= surf_thresh])

                # Kavite içinde en koyu %70'i al → duvar yansımalarını dışla
                cav_thresh  = np.percentile(cavity_pixels, 70)
                cavity_mean = np.mean(cavity_pixels[cavity_pixels <= cav_thresh])

                SCALE = max(0.5, mm_per_px / 0.05)  # referans: 0.05 mm/px

                # 1. Mevcut Yöntem: Doğrusal Parlaklık Farkı
                brightness_diff = max(0.0, float(surface_mean - cavity_mean))
                BRIGHT_PER_MM = 10.0
                rgb_depth = (brightness_diff / BRIGHT_PER_MM) * SCALE

                # 2. Pseudo-SFS (Shape from Shading) Yaklaşımı
                # Lambertian yansıma prensibiyle, yüzey normalleri dikleştikçe 
                # ve derinlik arttıkça parlaklık logaritmik sönümlenir.
                if cavity_mean > 0 and surface_mean > 0:
                    sfs_ratio = surface_mean / cavity_mean
                    # 4.0 ampirik bir katsayıdır, fotoğraflarınızın aydınlatmasına göre 3.5 - 5.0 arası ince ayar yapabilirsiniz.
                    sfs_depth = np.log(sfs_ratio) * 4.0 * SCALE
                else:
                    sfs_depth = rgb_depth

                # 3. Hibrit Birleştirme (Ensemble)
                # SFS derin noktalarda (gölgelerde) daha iyidir, RGB farkı ise sığ çukurlarda.
                calculated_depth = (rgb_depth * 0.4) + (sfs_depth * 0.6)

                # 4.5mm ÜST SINIRINI KALDIRDIK. Sadece eksiye düşmemesi için alt sınır 0.0 yapıldı.
                dynamic_depth_mm = float(max(0.0, calculated_depth))
                
                print(f">>> Derinlik Log: yüzey={surface_mean:.1f} kavite={cavity_mean:.1f}")
                print(f"    rgb_depth={rgb_depth:.2f} sfs_depth={sfs_depth:.2f} final_depth={dynamic_depth_mm:.2f} mm")
            else:
                print(">>> Derinlik: yetersiz piksel, varsayılan kullanılıyor.")
        except Exception as e:
            print(f">>> HATA: Derinlik hesaplanırken sorun: {e}")

    metrics["depth"] = dynamic_depth_mm
    CAVITY_DEPTH_MM = dynamic_depth_mm

    # ── STL Oluşturma ──────────────────────────────────────────────────────
    stl_success = False
    if create_composite_stl and cav_mask is not None and tooth_mask is not None:
        stl_success = create_composite_stl(
            tooth_mask,
            cav_mask,
            mm_per_px,
            stl_path,
            cavity_depth = CAVITY_DEPTH_MM,
            base_depth   = 6.0,               
            root_depth   = 5.0,               
        )

    cv2.imwrite(os.path.join(output_folder, drawn_90_name), img_90)
    _, buffer = cv2.imencode('.jpg', img_90, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
    img_base64 = base64.b64encode(buffer).decode('utf-8')

    res = {
        **metrics, 
        "drawn_90": drawn_90_name, 
        "stl_file": stl_output_name if stl_success else None,
        "base64_image": img_base64, 
        "aruco_90_found": aruco_90_found,
    }
    
    res.update({f"{k}_score": int(grade_metric(k, v)) for k, v in metrics.items()})
    
    fatal_error = None
    if metrics["buccal_lingual_width"] >= 5.0:
        fatal_error = "Kavitenin B-L boyutunun çok geniş olması (>= 5mm)"
    elif metrics["depth"] > 3.5:
        fatal_error = "Okluzal kavite preparasyon derinliğinin çok fazla olması (> 3.5mm)"
        
    res["total_score"] = 0 if fatal_error else int(sum([v for k,v in res.items() if "_score" in k]))
    res["fatal_error"] = fatal_error
    return res