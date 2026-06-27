import open3d as o3d
import numpy as np
import copy
import os
import logging
import time
from sklearn.cluster import DBSCAN 
from sklearn.decomposition import PCA 
from scipy.spatial import KDTree
import gc 

from cavity_utils import compute_hull_depth

# --- LOGLAMA AYARI ---
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] analysis.py:%(lineno)d - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------
# 1. YARDIMCI FONKSİYONLAR
# ---------------------------------------------------------
def load_and_optimize_mesh(file_path):
    logger.info(f"Yükleniyor: {file_path}")
    if not os.path.exists(file_path): return None
    try:
        mesh = o3d.io.read_triangle_mesh(file_path)
        if mesh.is_empty(): return None
        
        bbox = mesh.get_axis_aligned_bounding_box()
        if bbox.get_max_extent() < 2.0: 
            vertices = np.asarray(mesh.vertices)
            center = np.mean(vertices, axis=0)
            mesh.vertices = o3d.utility.Vector3dVector((vertices - center) * 1000.0 + center)
        
        vertex_count = len(mesh.vertices)
        if vertex_count > 300000:  
            mesh = mesh.simplify_vertex_clustering(voxel_size=0.02)
            logger.info("Mesh çok büyük, noktalar azaltıldı (RAM tasarrufu).")
        
        mesh.remove_duplicated_vertices()
        mesh.compute_vertex_normals()
        return mesh
    except Exception as e:
        logger.error(f"Dosya okuma HATA: {e}", exc_info=True)
        return None

def cached_mesh_load(file_path):
    if not os.path.exists(file_path): return None
    return load_and_optimize_mesh(file_path)

def grade_metric(metric, value):
    # Oranların doğru yakalanması için yuvarlama hassasiyetini 3'e çıkardık
    value = round(value, 3) 
    criteria = {
        "outline_form": [(1.58, 2.00, 10), (1.40, 1.579, 5), (2.001, 3.50, 5)],
        "mesial_isthmus_width": [(1.50, 1.99, 10), (1.00, 1.499, 5), (1.991, 2.50, 5)],
        "distal_isthmus_width": [(1.50, 1.99, 10), (1.00, 1.499, 5), (1.991, 2.50, 5)],
        "buccal_lingual_width": [(2.70, 3.30, 10), (2.50, 2.699, 5), (3.301, 3.50, 5)],
        "mesio_distal_width": [(7.10, 8.29, 10), (6.60, 7.099, 5)],
        "buccal_lingual_width_rate": [(0.35, 0.45, 10), (0.29, 0.349, 5)],
        "mesio_distal_width_rate": [(0.65, 0.75, 10), (0.60, 0.649, 5)],
        "mesial_marginal_ridge_width": [(1.20, 1.60, 10), (1.00, 1.199, 5), (1.601, 2.00, 5)],
        "distal_marginal_ridge_width": [(1.20, 1.60, 10), (1.00, 1.199, 5), (1.601, 2.00, 5)],
        "mesial_marginal_ridge_width_rate": [(0.11, 0.15, 10), (0.09, 0.109, 5), (0.151, 0.18, 5)],
        "distal_marginal_ridge_width_rate": [(0.11, 0.15, 10), (0.09, 0.109, 5), (0.151, 0.18, 5)],
        "cavity_depth": [(2.50, 3.00, 10), (2.00, 2.499, 5), (3.001, 3.49, 5)],
        "smoothness": [(0, 10.0, 10), (10.01, 40.0, 5)]
    }
    if metric in criteria:
        for rng in criteria[metric]:
            if rng[0] <= value <= rng[1]: 
                return rng[2]
    return 0

# ---------------------------------------------------------
# 2. TOPOLOJİ ANALİZİ (DİNAMİK + DBSCAN + GÜVENLİK KİLİDİ)
# ---------------------------------------------------------
def analyze_topology_angular(mesh):
    logger.info("Dinamik Topoloji Analizi Başladı (DBSCAN ve RANSAC Aktif).")
    vertices = np.asarray(mesh.vertices)
    normals = np.asarray(mesh.vertex_normals)
    
    min_y, max_y = np.min(vertices[:, 1]), np.max(vertices[:, 1])
    min_x, max_x = np.min(vertices[:, 0]), np.max(vertices[:, 0])
    min_z, max_z = np.min(vertices[:, 2]), np.max(vertices[:, 2])
    
    height_span = max_y - min_y
    width_x = max_x - min_x
    width_z = max_z - min_z
    
    mesh_center = np.mean(vertices, axis=0)
    center_x, center_z = mesh_center[0], mesh_center[2]

    dynamic_radius_limit = max(width_x, width_z) * 0.55 

    # --- ADIM 1: TABAN (RANSAC) ---
    lower_half_mask = (vertices[:, 1] < min_y + height_span * 0.45)
    
    upward_facing_mask = (normals[:, 1] > 0.75)
    floor_candidates_idx = np.where(lower_half_mask & upward_facing_mask)[0]
    
    floor_mask = np.zeros(len(vertices), dtype=bool)
    floor_y = min_y + height_span * 0.25 
    
    if len(floor_candidates_idx) > 50:
        pcd_floor = o3d.geometry.PointCloud()
        pcd_floor.points = o3d.utility.Vector3dVector(vertices[floor_candidates_idx])
        plane_model, inliers = pcd_floor.segment_plane(distance_threshold=0.2, ransac_n=3, num_iterations=1000)
        confirmed_floor_indices = floor_candidates_idx[inliers]
        floor_mask[confirmed_floor_indices] = True
        
        floor_y = np.mean(vertices[confirmed_floor_indices, 1])
        center_x = np.mean(vertices[confirmed_floor_indices, 0])
        center_z = np.mean(vertices[confirmed_floor_indices, 2])
        
        y_tolerance = height_span * 0.05 
        points_at_floor_level = (np.abs(vertices[:, 1] - floor_y) < y_tolerance) & (normals[:, 1] > 0.7)
        radius_mask_floor = np.sqrt((vertices[:, 0] - center_x)**2 + (vertices[:, 2] - center_z)**2) < dynamic_radius_limit
        floor_mask = floor_mask | (points_at_floor_level & radius_mask_floor)
        
        del pcd_floor

    # --- ADIM 2: DUVAR ---
    cavity_top_y = min(max_y - (height_span * 0.05), floor_y + (width_x * 0.5))
    
    height_mask = (vertices[:, 1] > floor_y + 0.1) & (vertices[:, 1] < cavity_top_y)
    dists_to_center = np.sqrt((vertices[:, 0] - center_x)**2 + (vertices[:, 2] - center_z)**2)
    radius_limit_mask = dists_to_center < dynamic_radius_limit 
    is_vertical = np.abs(normals[:, 1]) < 0.70 
    
    is_upper_area = vertices[:, 1] > (floor_y + height_span * 0.20)
    is_sloping_up = normals[:, 1] > 0.45 
    occlusal_rim_mask = is_upper_area & is_sloping_up
    
    vec_to_center_x, vec_to_center_z = center_x - vertices[:, 0], center_z - vertices[:, 2]
    dot_prod = (vec_to_center_x * normals[:, 0]) + (vec_to_center_z * normals[:, 2])
    inward_facing_mask = dot_prod > 0.0
    
    wall_mask = height_mask & radius_limit_mask & is_vertical & inward_facing_mask & (~occlusal_rim_mask)
    
    # --- GÜVENLİK KİLİDİ ---
    depths, _ = compute_hull_depth(vertices)
    is_inside_concavity = np.ones(len(vertices), dtype=bool) 
    
    if depths is not None:
        ### --- EN KATI GÜNCELLEME: Sığlık sınırı 0.12 yapıldı (Doğal olukları kesin reddet) --- ###
        is_inside_concavity = depths > 0.12
        logger.info("Güvenlik kilidi devrede: Dış yüzey sızıntıları filtreleniyor.")
    else:
        logger.warning("Convex Hull hesaplanamadı, güvenlik kilidi atlandı!")

    combined_mask = (floor_mask | wall_mask) & is_inside_concavity

    # --- ADIM 3: TEMİZLİK (DBSCAN VE BOYUT ODAKLI SEÇİM) ---
    if np.sum(combined_mask) > 50:
        pts = vertices[combined_mask]
        
        if len(pts) > 60000:
            indices = np.random.choice(len(pts), 60000, replace=False)
            clustering_pts = pts[indices]
            original_indices = np.where(combined_mask)[0][indices]
        else:
            clustering_pts = pts
            original_indices = np.where(combined_mask)[0]

        ### --- EN KATI GÜNCELLEME: Eps atlama mesafesi 0.85'e çekildi --- ###
        clustering = DBSCAN(eps=0.85, min_samples=10).fit(clustering_pts) 
        labels = clustering.labels_
        unique_labels = set(labels)
        best_cluster = -1
        
        max_points = 0 
        
        for lbl in unique_labels:
            if lbl == -1: continue # Gürültüleri atla
            idx = np.where(labels == lbl)[0]
            pts_cluster = clustering_pts[idx]
            
            if np.min(pts_cluster[:, 1]) > floor_y + (height_span * 0.3): continue
            
            cluster_size = len(idx)
            if cluster_size > max_points:
                max_points = cluster_size
                best_cluster = lbl
                
        final_mask = np.zeros(len(vertices), dtype=bool)
        if best_cluster != -1:
            idx = np.where(labels == best_cluster)[0]
            final_mask[original_indices[idx]] = True
        combined_mask = final_mask
        
        del clustering, pts, clustering_pts
        gc.collect()

    # --- ADIM 4: GAP FILLING ---
    if np.sum(combined_mask) > 0:
        tree = KDTree(vertices[combined_mask])
        
        ### --- EN KATI GÜNCELLEME: Eğim(0.50) ve Mesafe(0.50) minimuma çekildi --- ###
        candidates_mask = (~combined_mask) & radius_limit_mask & \
                          (vertices[:, 1] > floor_y - 0.2) & (vertices[:, 1] < cavity_top_y) & \
                          (normals[:, 1] < 0.50) & is_inside_concavity
                          
        candidate_indices = np.where(candidates_mask)[0]
        if len(candidate_indices) > 0:
            dists, _ = tree.query(vertices[candidate_indices], distance_upper_bound=0.50)
            combined_mask[candidate_indices[dists < 0.50]] = True
            
        del tree

    strict_mask = combined_mask & (vertices[:, 1] <= floor_y + (height_span * 0.3))

    return {
        "cavity": combined_mask,
        "strict_cavity": strict_mask,
        "top_y": max_y,
        "floor_y": floor_y,
        "cavity_top_y": cavity_top_y,
        "floor_center": [center_x, floor_y, center_z],
        "center_z": center_z,
        "vertices": vertices,
        "normals": normals,
        "mesh": mesh
    }

# ---------------------------------------------------------
# 3. HESAPLAMA (PCA + YENİ LOKAL EKSEN PROJEKSİYONU)
# ---------------------------------------------------------
def calculate_metrics(data):
    logger.info("Metrik Hesaplama Başladı")
    verts = data["vertices"]
    mask = data["cavity"]
    strict_mask = data["strict_cavity"]
    floor_y = data["floor_y"]
    top_y = data["top_y"]
    center_z = data["center_z"]
    floor_center = data["floor_center"]
    
    metrics, landmarks = {}, {}
    if np.sum(mask) < 50: return fill_zero_metrics(metrics, 0)

    cavity_pts = verts[mask]
    
    if len(cavity_pts) > 10:
        top_5_percentile = np.percentile(cavity_pts[:, 1], 95)
        okluzal_y = top_5_percentile
        
        pts_2d = cavity_pts[:, [0, 2]] 
        pca = PCA(n_components=2)
        pca.fit(pts_2d)
        
        direction_vector = pca.components_[0] 
        side_vector = pca.components_[1]      
        center_point_2d = pca.mean_
        
        SHIFT_OFFSET = -0.5 
        center_point_2d = center_point_2d + (side_vector * SHIFT_OFFSET)
        
        vecs = pts_2d - center_point_2d
        projections = np.dot(vecs, direction_vector)
        
        okluzal_indices = np.where(cavity_pts[:, 1] >= okluzal_y - 1.0)[0]
        
        if len(okluzal_indices) > 0:
            p_min, p_max = np.min(projections[okluzal_indices]), np.max(projections[okluzal_indices])
        else:
            p_min, p_max = np.min(projections), np.max(projections)
            
        metrics["mesio_distal_width"] = float(p_max - p_min)
        
        start_2d = center_point_2d + direction_vector * p_min
        end_2d = center_point_2d + direction_vector * p_max
        landmarks["mesio_distal_width"] = {
            "start": [float(start_2d[0]), float(okluzal_y), float(start_2d[1])], 
            "end": [float(end_2d[0]), float(okluzal_y), float(end_2d[1])]
        }
        pca_axis = {"direction": direction_vector, "center": center_point_2d, "cav_min": p_min, "cav_max": p_max}
    else:
        metrics["mesio_distal_width"] = 0.0
        okluzal_y = top_y
        center_point_2d = np.array([floor_center[0], floor_center[2]])
        direction_vector = np.array([1.0, 0.0])
        side_vector = np.array([0.0, 1.0])

    if 'pca_axis' in locals():
        tooth_slice_mask = (verts[:, 1] > okluzal_y - 0.5) & (verts[:, 1] < okluzal_y + 0.5)
        tooth_pts = verts[tooth_slice_mask]
        
        if len(tooth_pts) > 10:
            t_pts_2d = tooth_pts[:, [0, 2]]
            t_vecs = t_pts_2d - pca_axis["center"]
            t_projections = np.dot(t_vecs, pca_axis["direction"])
            
            t_min, t_max = np.min(t_projections), np.max(t_projections)
            c_min, c_max = pca_axis["cav_min"], pca_axis["cav_max"]
            
            w1, w2 = abs(c_min - t_min), abs(t_max - c_max)
            if pca_axis["direction"][0] > 0:
                raw_distal, raw_mesial = w1, w2
                p_t_mesial, p_c_mesial, p_c_distal, p_t_distal = t_min, c_min, c_max, t_max
            else:
                raw_distal, raw_mesial = w2, w1
                p_t_mesial, p_c_mesial, p_c_distal, p_t_distal = t_max, c_max, c_min, t_min

            metrics["mesial_marginal_ridge_width"] = raw_mesial * 0.80
            metrics["distal_marginal_ridge_width"] = raw_distal * 0.80
            
            m_red, d_red = raw_mesial * 0.20, raw_distal * 0.20
            
            m_start_proj = p_t_mesial + (m_red if p_t_mesial < p_c_mesial else -m_red)
            m_start_2d = pca_axis["center"] + pca_axis["direction"] * m_start_proj
            m_end_2d = pca_axis["center"] + pca_axis["direction"] * p_c_mesial
            landmarks["mesial_marginal_ridge_width"] = {"start": [float(m_start_2d[0]), float(okluzal_y), float(m_start_2d[1])], "end": [float(m_end_2d[0]), float(okluzal_y), float(m_end_2d[1])]}
            
            d_end_proj = p_t_distal - (d_red if p_t_distal > p_c_distal else -d_red)
            d_start_2d = pca_axis["center"] + pca_axis["direction"] * p_c_distal
            d_end_2d = pca_axis["center"] + pca_axis["direction"] * d_end_proj
            landmarks["distal_marginal_ridge_width"] = {"start": [float(d_start_2d[0]), float(okluzal_y), float(d_start_2d[1])], "end": [float(d_end_2d[0]), float(okluzal_y), float(d_end_2d[1])]}
        else:
            metrics["mesial_marginal_ridge_width"] = metrics["distal_marginal_ridge_width"] = 0.0
    else:
        metrics["mesial_marginal_ridge_width"] = metrics["distal_marginal_ridge_width"] = 0.0

    measuring_pts = verts[strict_mask] if np.sum(strict_mask) > 50 else verts[mask]
    
    measuring_pts_2d = measuring_pts[:, [0, 2]] - center_point_2d
    u_proj = np.dot(measuring_pts_2d, direction_vector) 
    v_proj = np.dot(measuring_pts_2d, side_vector)      
    
    u_min, u_max = np.percentile(u_proj, 2), np.percentile(u_proj, 98)
    mid_u = (u_min + u_max) / 2
    
    def get_isthmus_local(start_u, end_u):
        best, min_w = None, 999
        for u in np.arange(start_u, end_u, 0.25):
            mask_slice = np.abs(u_proj - u) < 0.3
            slice_v = v_proj[mask_slice]
            if len(slice_v) < 5: continue
            
            v_min, v_max = np.percentile(slice_v, 5), np.percentile(slice_v, 95)
            w = v_max - v_min
            if 0.5 < w < min_w:
                min_w = w
                vis_y_isth = floor_y + 1.0
                
                start_2d = center_point_2d + direction_vector * u + side_vector * v_min
                end_2d = center_point_2d + direction_vector * u + side_vector * v_max
                
                best = {
                    "width": float(w), 
                    "start": [float(start_2d[0]), float(vis_y_isth), float(start_2d[1])], 
                    "end": [float(end_2d[0]), float(vis_y_isth), float(end_2d[1])]
                }
        return best

    mesial_data = get_isthmus_local(u_min + 0.5, mid_u - 0.5)
    distal_data = get_isthmus_local(mid_u + 0.5, u_max - 0.5)
    
    metrics["mesial_isthmus_width"] = mesial_data["width"] if mesial_data else 0.0
    if mesial_data: landmarks["mesial_isthmus_width"] = mesial_data
    metrics["distal_isthmus_width"] = distal_data["width"] if distal_data else 0.0
    if distal_data: landmarks["distal_isthmus_width"] = distal_data

    v_min_bl, v_max_bl = np.percentile(v_proj, 2), np.percentile(v_proj, 98)
    metrics["buccal_lingual_width"] = float(v_max_bl - v_min_bl)
    
    mean_u = np.mean(u_proj)
    bl_start_2d = center_point_2d + direction_vector * mean_u + side_vector * v_min_bl
    bl_end_2d = center_point_2d + direction_vector * mean_u + side_vector * v_max_bl
    
    landmarks["buccal_lingual_width"] = {
        "start": [float(bl_start_2d[0]), float(floor_y+1), float(bl_start_2d[1])], 
        "end": [float(bl_end_2d[0]), float(floor_y+1), float(bl_end_2d[1])]
    }

    pts_y = verts[mask, 1]
    margin_y = np.percentile(pts_y, 98) if len(pts_y) > 0 else top_y
    metrics["cavity_depth"] = float(abs(margin_y - floor_y))
    landmarks["cavity_depth"] = {"start": [float(floor_center[0]), float(floor_y), float(center_z)], "end": [float(floor_center[0]), float(margin_y), float(center_z)]}

    md = metrics["mesio_distal_width"]
    if md > 0.1:
        metrics["buccal_lingual_width_rate"] = metrics["buccal_lingual_width"] / md
        metrics["mesial_marginal_ridge_width_rate"] = metrics["mesial_marginal_ridge_width"] / md
        metrics["distal_marginal_ridge_width_rate"] = metrics["distal_marginal_ridge_width"] / md
        if 't_min' in locals() and 't_max' in locals():
            tooth_width = abs(t_max - t_min)
            metrics["mesio_distal_width_rate"] = md / tooth_width if tooth_width > 0.1 else 0.0
        else:
             metrics["mesio_distal_width_rate"] = 0.0
    else:
        for k in ["buccal_lingual_width_rate", "mesio_distal_width_rate", "mesial_marginal_ridge_width_rate", "distal_marginal_ridge_width_rate"]:
            metrics[k] = 0.0
            
    avg_isth = (metrics["mesial_isthmus_width"] + metrics["distal_isthmus_width"]) / 2
    metrics["outline_form"] = metrics["buccal_lingual_width"] / avg_isth if avg_isth > 0.1 else 0.0
    
    if np.sum(strict_mask) > 10:
        metrics["smoothness"] = max(0.0, 10.0 - np.sum(np.var(data["normals"][strict_mask], axis=0)) * 10.0)
    else: metrics["smoothness"] = 10.0

    if 'pca' in locals():
        del pca
    gc.collect()

    return metrics, landmarks

def fill_zero_metrics(metrics, depth):
    keys = ["outline_form", "mesial_isthmus_width", "distal_isthmus_width", "buccal_lingual_width", 
            "buccal_lingual_width_rate", "mesio_distal_width", "mesio_distal_width_rate", 
            "mesial_marginal_ridge_width", "distal_marginal_ridge_width", 
            "mesial_marginal_ridge_width_rate", "distal_marginal_ridge_width_rate", "smoothness"]
    for k in keys: metrics[k] = 0.0
    metrics["cavity_depth"] = float(depth)
    return metrics, {}

# ---------------------------------------------------------
# 4. ANA FONKSİYON
# ---------------------------------------------------------
def analyze_preprocessed_cavity(stl_path):
    logger.info(f"=== GERÇEK ANALİZ BAŞLADI ===")
    start_t = time.time()
    
    try:
        student = cached_mesh_load(stl_path)
        if not student: return {"error": "Dosya yükleme hatası"}
        
        topo_data = analyze_topology_angular(student)
        metrics, landmarks = calculate_metrics(topo_data)
        
        scores = {f"{k}_score": grade_metric(k, v) for k, v in metrics.items()}
        total_score = sum(scores.get(f"{k}_score", 0) for k in ["outline_form", "mesial_isthmus_width", "distal_isthmus_width", "buccal_lingual_width", "buccal_lingual_width_rate", "mesio_distal_width_rate", "mesial_marginal_ridge_width_rate", "distal_marginal_ridge_width_rate", "cavity_depth", "smoothness"])
        
        fatal_errors = []
        if metrics.get("cavity_depth", 0) > 3.5:
            total_score = 0
            fatal_errors.append("Kritik Hata: Derinlik > 3.5 mm")

        mesh_colored = o3d.geometry.TriangleMesh()
        mesh_colored.vertices = student.vertices
        mesh_colored.triangles = student.triangles
        mesh_colored.compute_vertex_normals()

        colors = np.ones((len(np.asarray(student.vertices)), 3)) * 0.95
        colors[topo_data["cavity"]] = [0.8, 0.1, 0.1]
        mesh_colored.vertex_colors = o3d.utility.Vector3dVector(colors)
        
        colored_filename = os.path.basename(stl_path).replace('.stl', '_colored.ply')
        colored_path = os.path.join(os.path.dirname(stl_path), colored_filename)
        
        o3d.io.write_triangle_mesh(colored_path, mesh_colored, write_ascii=False)
        
        del student
        gc.collect()
        
        logger.info(f"=== ANALİZ BAŞARIYLA BİTTİ === (Süre: {time.time() - start_t:.2f}s)")
        
        return {
            **metrics, "scores": scores, "total_score_130": total_score, "final_score_100": total_score, 
            "comparison": {}, "landmarks": landmarks, "colored_mesh_path": colored_path, "fatal_errors": fatal_errors 
        }
    except Exception as e:
        logger.error(f"=== ANALİZ ÇÖKTÜ ===: {e}", exc_info=True)
        return {"error": f"Beklenmeyen hata: {str(e)}"}