"""
isolate_tooth.py
----------------
RANSAC + Merkez Odaklı İzolasyon Sürümü
Sabit kırpma oranları tamamen kaldırılmıştır.
"""

import open3d as o3d
import numpy as np
import os

def _apply_vertex_mask(mesh, keep_mask):
    tris  = np.asarray(mesh.triangles)
    valid = keep_mask[tris[:, 0]] & keep_mask[tris[:, 1]] & keep_mask[tris[:, 2]]
    mesh.triangles = o3d.utility.Vector3iVector(tris[valid])
    mesh.remove_unreferenced_vertices()
    return mesh

def _remove_statistical_outliers(mesh, nb_neighbors=20, std_ratio=1.5):
    pcd = o3d.geometry.PointCloud()
    pcd.points = mesh.vertices
    cl, ind = pcd.remove_statistical_outlier(nb_neighbors=nb_neighbors, std_ratio=std_ratio)
    keep_mask = np.zeros(len(mesh.vertices), dtype=bool)
    keep_mask[ind] = True
    return _apply_vertex_mask(mesh, keep_mask)

# ─────────────────────────────────────────────────────────────────────────────
# ADIM 1 – RANSAC ile Masayı Bul, Sil ve Masanın Merkezini Hafızaya Al
# ─────────────────────────────────────────────────────────────────────────────
def _remove_plane_ransac_and_find_center(mesh):
    pcd = o3d.geometry.PointCloud()
    pcd.points = mesh.vertices

    bbox = mesh.get_axis_aligned_bounding_box()
    diagonal = np.linalg.norm(bbox.get_max_bound() - bbox.get_min_bound())
    dist_thresh = diagonal * 0.01  

    # Düzlemi bul
    plane_model, inliers = pcd.segment_plane(distance_threshold=dist_thresh,
                                             ransac_n=3,
                                             num_iterations=2000)
    
    # ---------------------------------------------------------
    # AKILLI KONTROL MEKANİZMASI EKLENDİ
    # ---------------------------------------------------------
    total_points = len(pcd.points)
    inlier_ratio = len(inliers) / total_points

    # Eğer bulunan en büyük düzlem, modelin %10'undan daha azını kaplıyorsa, 
    # bu muhtemelen bir zemin değil, dişin düz bir duvarıdır!
    if inlier_ratio < 0.10: 
        print(f"      → Uyarı: Belirgin bir zemin bulunamadı (Oran: %{inlier_ratio*100:.1f}). Zemin silme işlemi atlanıyor.")
        
        # Zemin olmadığı için modeli hiç kırpmadan geri dönüyoruz.
        # Merkez olarak da dişin kendi genel merkezini veriyoruz.
        return mesh, np.mean(np.asarray(mesh.vertices), axis=0)
    # ---------------------------------------------------------

    print(f"      → Zemin bulundu (Modelin %{inlier_ratio*100:.1f}'i). Siliniyor...")

    # Zemin bulunduysa, orijinal işlemlere devam et
    inlier_cloud = pcd.select_by_index(inliers)
    table_center = np.mean(np.asarray(inlier_cloud.points), axis=0)

    [a, b, c, d] = plane_model
    verts = np.asarray(mesh.vertices)
    norm = np.linalg.norm([a, b, c])
    distances = np.abs((verts[:, 0] * a + verts[:, 1] * b + verts[:, 2] * c + d) / norm)

    keep_mask = distances > (dist_thresh * 1.5)
    mesh = _apply_vertex_mask(mesh, keep_mask)

    return mesh, table_center


# ─────────────────────────────────────────────────────────────────────────────
# ADIM 2 – Merkeze En Yakın Kümeyi Tut (En Büyük Olanı Değil!)
# ─────────────────────────────────────────────────────────────────────────────
def _keep_central_cluster(mesh, reference_center):
    tri_clusters, cluster_n_triangles, _ = mesh.cluster_connected_triangles()
    tri_clusters = np.asarray(tri_clusters)
    cluster_n_triangles = np.asarray(cluster_n_triangles)

    if len(cluster_n_triangles) == 0:
        return mesh

    # Sadece dişe benzeyebilecek hacme sahip kümeleri aday yap (min 500 üçgen).
    # Yoksa havada kalan minik bir toz tanesi merkeze denk gelirse onu seçebilir.
    valid_clusters = np.where(cluster_n_triangles > 500)[0]

    # Eğer sahnede hiç büyük parça kalmadıysa çökmeyelim, en büyük 3 kümeyi aday yap
    if len(valid_clusters) == 0:
        valid_clusters = np.argsort(cluster_n_triangles)[-3:]

    best_cluster = -1
    min_dist = float('inf')

    verts = np.asarray(mesh.vertices)
    tris = np.asarray(mesh.triangles)

    # Tüm aday kümeler arasında "Masanın Merkezine" en yakın olanı bul
    for cid in valid_clusters:
        cluster_tris_idx = np.where(tri_clusters == cid)[0]
        cluster_verts_idx = np.unique(tris[cluster_tris_idx])
        cluster_center = np.mean(verts[cluster_verts_idx], axis=0)

        # Sadece X ve Y (yatay) eksenindeki uzaklığa bak, yükseklik (Z) yanıltmasın
        dist = np.linalg.norm(cluster_center[:2] - reference_center[:2])

        if dist < min_dist:
            min_dist = dist
            best_cluster = cid

    # Seçilen merkez kümeyi (dişi) tut, geri kalan devasa gürültüleri at
    remove_mask = tri_clusters != best_cluster
    mesh.remove_triangles_by_mask(remove_mask)
    mesh.remove_unreferenced_vertices()
    return mesh



# ─────────────────────────────────────────────────────────────────────────────
# ANA FONKSİYON
# ─────────────────────────────────────────────────────────────────────────────
def isolate_tooth(input_obj_path: str, output_stl_path: str) -> None:
    if not os.path.exists(input_obj_path):
        raise FileNotFoundError(f"Girdi dosyası bulunamadı: {input_obj_path}")

    print("[1/5] Model yükleniyor ve kopyalar siliniyor...")
    mesh = o3d.io.read_triangle_mesh(input_obj_path)
    mesh.remove_duplicated_vertices()
    mesh.remove_duplicated_triangles()
    mesh.remove_unreferenced_vertices()

    print("[2/5] Uçuşan tozlar temizleniyor...")
    mesh = _remove_statistical_outliers(mesh)

    print("[3/5] RANSAC ile masa bulunup siliniyor (Masa merkezi hesaplanıyor)...")
    mesh, table_center = _remove_plane_ransac_and_find_center(mesh)
    print(f"      → Referans Merkez: (X: {table_center[0]:.2f}, Y: {table_center[1]:.2f})")

    print("[4/5] Merkeze en yakın parça (Diş) izole ediliyor...")
    mesh = _keep_central_cluster(mesh, reference_center=table_center)

    print("[5/5] Taubin smoothing uygulanıyor...")
    mesh = mesh.filter_smooth_taubin(number_of_iterations=10)
    mesh.compute_vertex_normals()

    print("[6/6] Loop Subdivision uygulanıyor (Vertex sayısı 16 katına çıkarılıyor)...")
    # number_of_iterations=2 ile her üçgen 4'e, sonra tekrar 4'e bölünür (Toplam 16 kat artış)
    mesh = mesh.subdivide_loop(number_of_iterations=2)
    mesh.compute_vertex_normals()

    os.makedirs(os.path.dirname(os.path.abspath(output_stl_path)), exist_ok=True)
    o3d.io.write_triangle_mesh(output_stl_path, mesh)
    print(f"\n[BAŞARILI] İşlem tamamlandı. Yüksek Çözünürlüklü Kalan Köşe: {len(mesh.vertices):,}")

if __name__ == "__main__":
    GIRDI_OBJ = r"odm_textured_model_geo.obj"
    CIKTI_STL = r"smoothed_cropped_model.stl"

    isolate_tooth(GIRDI_OBJ, CIKTI_STL)