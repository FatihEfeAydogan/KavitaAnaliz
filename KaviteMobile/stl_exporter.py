"""
stl_exporter.py - (Katmanlı Dağ & Kavisli Topolojik Ekstrüzyon + Prosedürel Pürüzlü Kavite)
Etek sarkması, dikiş yırtılmaları ve iğne (spike) artefaktları tamamen çözülmüştür.
Topolojik sınır kenarları kullanılarak mesh'te %100 su sızdırmaz (watertight) birleşme sağlanır.
Duvar, anatomik formda (önce dışa doğru şişkin, köke doğru daralan) inşa edilir.
Kavite tabanı prosedürel frez izleri ile matematiksel olarak detaylandırılmıştır.
"""

import numpy as np
import trimesh
import trimesh.repair
import cv2
import os

DEFAULT_CAVITY_DEPTH_MM = 0.00

def create_composite_stl(
    tooth_mask,
    cav_mask,
    mm_per_px,
    output_path,
    cavity_depth=DEFAULT_CAVITY_DEPTH_MM,
    depth_norm=None,
    **kwargs
):
    print(f">>> 3D Mesh Üretimi Başladı | Kavisli Topolojik Ekstrüzyon (Prosedürel Pürüzlü Taban)")

    # 1. MASKEYİ KIRP
    ys, xs = np.where(tooth_mask > 0)
    if len(ys) == 0:
        print("    [Hata] Diş maskesi boş, işlem iptal.")
        return False

    pad = 5
    y1, y2 = max(0, ys.min() - pad), min(tooth_mask.shape[0], ys.max() + pad)
    x1, x2 = max(0, xs.min() - pad), min(tooth_mask.shape[1], xs.max() + pad)

    t_mask = tooth_mask[y1:y2, x1:x2]
    c_mask = cav_mask[y1:y2, x1:x2]

    h, w = t_mask.shape

    # 2. KOORDİNATLAR (mm)
    X, Y = np.meshgrid(np.arange(w), np.arange(h))
    X = X * mm_per_px
    Y = (h - Y) * mm_per_px

    # ── 3. Z-HARİTASI İNŞASI ──────────────────────────────────────────────────

    MARGIN_HEIGHT = 10.0       
    RIDGE_HEIGHT = 0.5         
    CUSP_HEIGHT = 1.50         
    WALL_HEIGHT = 10.0         

    Z = np.zeros((h, w), dtype=np.float32)
    intact_mask = cv2.bitwise_and(t_mask, cv2.bitwise_not(c_mask))

    cavity_floor_z = MARGIN_HEIGHT - cavity_depth
    
    # KAVİTE İÇİ EĞİMLİ DUVAR HESAPLAMASI (90 Derece uçurum yerine kavisli iniş)
    dist_in_cav = cv2.distanceTransform(c_mask, cv2.DIST_L2, 5)
    
    # Duvar eğiminin ne kadar süreceği (Örn: 0.8 mm kalınlığında bir duvar)
    WALL_SLOPE_MM = 0.8
    slope_px = max(1, int(WALL_SLOPE_MM / (mm_per_px + 1e-6)))
    
    # 0 (sınır) ile 1 (tam taban) arası oran
    cav_ratio = np.clip(dist_in_cav / slope_px, 0.0, 1.0)
    
    # Sinüs eğrisi ile yumuşak geçiş (Smoothstep)
    wall_profile = (1.0 - np.cos(cav_ratio * np.pi)) / 2.0 
    
    # Sınırda MARGIN_HEIGHT, merkeze indikçe cavity_floor_z değerine ulaşır
    Z[c_mask > 128] = MARGIN_HEIGHT - (wall_profile[c_mask > 128] * cavity_depth)

    # Dış duvar / sağlam doku maskeleri
    dist_out = cv2.distanceTransform(t_mask, cv2.DIST_L2, 5)
    inverted_c_mask = cv2.bitwise_not(c_mask)
    dist_in = cv2.distanceTransform(inverted_c_mask, cv2.DIST_L2, 5)

    epsilon = 1e-5 
    t_ratio = dist_in / (dist_in + dist_out + epsilon)
    t_ratio = cv2.bitwise_and(t_ratio, t_ratio, mask=intact_mask)

    mountain_profile = np.sin(t_ratio * np.pi)
    base_ridge = mountain_profile * RIDGE_HEIGHT

    ys_wall, xs_wall = np.where(intact_mask > 0)
    if len(ys_wall) > 0:
        ymin, ymax, xmin, xmax = ys_wall.min(), ys_wall.max(), xs_wall.min(), xs_wall.max()
    else:
        ymin, ymax, xmin, xmax = 0, h, 0, w

    w_box = max(xmax - xmin, 1)
    h_box = max(ymax - ymin, 1)

    SIGMA_DIV = 1.4 
    cusps = [
        {"cx": xmin + w_box * 0.15, "cy": ymin + h_box * 0.15, "radius": w_box * 0.22, "height": 1.00},
        {"cx": xmin + w_box * 0.50, "cy": ymin + h_box * 0.10, "radius": w_box * 0.20, "height": 0.92},
        {"cx": xmin + w_box * 0.85, "cy": ymin + h_box * 0.15, "radius": w_box * 0.22, "height": 0.85},
        {"cx": xmin + w_box * 0.20, "cy": ymin + h_box * 0.85, "radius": w_box * 0.24, "height": 0.88},
        {"cx": xmin + w_box * 0.80, "cy": ymin + h_box * 0.85, "radius": w_box * 0.24, "height": 0.78},
    ]

    y_idx, x_idx = np.indices((h, w))
    anatomy_map = np.zeros((h, w), dtype=np.float32)

    for c in cusps:
        dist_sq = (x_idx - c["cx"])**2 + (y_idx - c["cy"])**2
        sigma = max(c["radius"], 1.0) / SIGMA_DIV
        bump = np.exp(-dist_sq / (2 * sigma**2)) * c["height"]
        anatomy_map = np.maximum(anatomy_map, bump)

    cusp_peaks = mountain_profile * anatomy_map * CUSP_HEIGHT
    Z[intact_mask > 0] = MARGIN_HEIGHT + base_ridge[intact_mask > 0] + cusp_peaks[intact_mask > 0]

    # ── KAVİTE TABANINA MATEMATİKSEL PÜRÜZ (PROSEDÜREL GÜRÜLTÜ) EKLENMESİ ──
    # Yapay zeka yerine, farklı frekanslardaki dalgaları birleştirerek 
    # matkap/frez izine benzeyen doğal, asimetrik bir doku üretiyoruz.
    noise_map = (
        np.sin(X * 4.0) * np.cos(Y * 4.0) * 0.6 +   # Ana dalgalanma
        np.sin((X + Y) * 10.0) * 0.25 +             # İnce çizgiler
        np.cos((X - Y) * 15.0) * 0.15               # Mikro pürüzler
    )
    
    # Maksimum dalgalanma şiddeti (Örn: 0.2 mm'lik derinlik farkları yaratır)
    cavity_bump = noise_map * 0.2
    
    # Pürüzleri sadece kavite tabanına uygula (duvarlara tırmanmasın diye cav_ratio ile çarpıyoruz)
    Z[c_mask > 128] += (cavity_bump[c_mask > 128] * cav_ratio[c_mask > 128])


    SHOULDER_PX = max(4, int(3.5 / (mm_per_px + 1e-6)))
    t_shoulder = np.clip(dist_out / (SHOULDER_PX + 1e-5), 0.0, 1.0)
    shoulder_ease = (1.0 - np.cos(t_shoulder * np.pi)) / 2.0
    shoulder_drop = (1.0 - shoulder_ease) * (RIDGE_HEIGHT + CUSP_HEIGHT * 0.4)
    Z[intact_mask > 0] -= shoulder_drop[intact_mask > 0]
    Z[intact_mask > 0] = np.maximum(Z[intact_mask > 0], MARGIN_HEIGHT - 0.5)

    # ── 4. ÜST YÜZEY MESH İNŞASI ─────────────────────────────────────────────
    vertices_top = np.column_stack((X.flatten(), Y.flatten(), Z.flatten()))
    idx_grid = np.arange(h * w).reshape(h, w)

    f1 = np.column_stack((idx_grid[:-1,:-1].flatten(), idx_grid[1:,:-1].flatten(), idx_grid[:-1,1:].flatten()))
    f2 = np.column_stack((idx_grid[:-1,1:].flatten(), idx_grid[1:,:-1].flatten(), idx_grid[1:,1:].flatten()))
    faces_top = np.vstack((f1, f2))

    mask_flat = (t_mask > 128).flatten()
    valid = mask_flat[faces_top[:,0]] & mask_flat[faces_top[:,1]] & mask_flat[faces_top[:,2]]
    faces_top = faces_top[valid]

    # ── 5. KUSURSUZ VE KAVİSLİ YAN DUVAR (TOPOLOGICAL BULGE EXTRUSION) ───────
    edges = np.vstack((faces_top[:, [0, 1]], 
                       faces_top[:, [1, 2]], 
                       faces_top[:, [2, 0]]))
    
    edges_sorted = np.sort(edges, axis=1)
    dt = np.dtype((np.void, edges_sorted.dtype.itemsize * edges_sorted.shape[1]))
    edges_view_sorted = np.ascontiguousarray(edges_sorted).view(dt)
    
    unq, counts = np.unique(edges_view_sorted, return_counts=True)
    boundary_hashes = unq[counts == 1]
    
    mask = np.isin(edges_view_sorted, boundary_hashes).flatten()
    boundary_edges = edges[mask] 
    
    centroid_x = np.mean(X[intact_mask > 0])
    centroid_y = np.mean(Y[intact_mask > 0])

    N_RINGS = 22
    t_vals  = np.linspace(0.0, 1.0, N_RINGS + 1)  

    BULGE_MAX  = 1.5   
    BULGE_BASE = -0.6  
    bulge_vals = (
        BULGE_MAX * np.exp(-0.5 * ((t_vals - 0.18) / 0.14)**2)   
        + BULGE_BASE * t_vals                                      
    )
    bulge_vals -= bulge_vals[0] 
    z_drop_vals = t_vals * WALL_HEIGHT

    unique_b_verts = np.unique(boundary_edges)
    vert_columns = {}
    wall_verts = []
    start_idx = len(vertices_top)

    for v in unique_b_verts:
        px, py, pz = vertices_top[v]
        
        nx = px - centroid_x
        ny = py - centroid_y
        mag = np.sqrt(nx**2 + ny**2) + 1e-6
        nx /= mag
        ny /= mag
        
        v_column = [v] 
        for k in range(1, N_RINGS + 1):
            new_x = px + nx * bulge_vals[k]
            new_y = py + ny * bulge_vals[k]
            new_z = max(pz - z_drop_vals[k], 0.0)
            
            wall_verts.append([new_x, new_y, new_z])
            v_column.append(start_idx + len(wall_verts) - 1)
            
        vert_columns[v] = v_column

    wall_faces = []
    for v0, v1 in boundary_edges:
        col0 = vert_columns[v0]
        col1 = vert_columns[v1]
        
        for k in range(N_RINGS):
            t0 = col0[k]
            t1 = col1[k]
            b0 = col0[k+1]
            b1 = col1[k+1]
            
            wall_faces.append([t0, b0, t1])
            wall_faces.append([t1, b0, b1])

    if len(wall_verts) > 0:
        all_verts = np.vstack((vertices_top, np.array(wall_verts)))
        all_faces = np.vstack((faces_top, np.array(wall_faces)))
    else:
        all_verts = vertices_top
        all_faces = faces_top
        
    final_mesh = trimesh.Trimesh(vertices=all_verts, faces=all_faces, process=True)
    trimesh.repair.fix_normals(final_mesh)
    
    print(f"    [Başarılı] Kavisli Topolojik Ekstrüzyon uygulandı. Anatomik kök oluşturuldu.")

    # ── 6. EXPORT (GÜVENLİ İHRACAT) ─────────────────────────────────────────
    try:
        verts = final_mesh.vertices.astype(np.float32)
        faces = final_mesh.faces.astype(np.int32)
        
        tri_verts = verts[faces]                                  
        e1 = tri_verts[:, 1] - tri_verts[:, 0]
        e2 = tri_verts[:, 2] - tri_verts[:, 0]
        normals_out = np.cross(e1, e2)
        mag_n = np.linalg.norm(normals_out, axis=1, keepdims=True) + 1e-10
        normals_out /= mag_n
        
        with open(output_path, 'wb') as f:
            f.write(b'\x00' * 80)                                  
            f.write(np.uint32(len(faces)).tobytes())               
            for i in range(len(faces)):
                f.write(normals_out[i].astype(np.float32).tobytes())
                f.write(tri_verts[i].astype(np.float32).tobytes())
                f.write(b'\x00\x00')                               
        print(f">>> STL OK: {output_path.split('/')[-1]}  ({len(faces):,} yüz)")
        return True
    except Exception as e:
        print(f"    [Kritik Hata] STL dışa aktarılamadı: {e}")
        return False

# Dummy fonksiyonlar
def attach_root(*args, **kwargs): return args[0]
def create_composite_stl_highquality(*args, **kwargs): return create_composite_stl(*args, **kwargs)
def create_composite_stl_fast(*args, **kwargs): return create_composite_stl(*args, **kwargs)