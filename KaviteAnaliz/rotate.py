"""
rotate.py
─────────
İçbükeylik Odaklı Deterministik Hizalama Sistemi.
Dişin anatomik yapısından veya altının açık/kapalı olmasından bağımsız olarak,
sadece taç/kavite oryantasyonuna odaklanarak tek geçişte (single-pass) hizalama yapar.
"""

import os
import numpy as np
import open3d as o3d

from cavity_utils import find_cavity_opening_direction, rotation_align

def _normalize_xz_rotation(mesh):
    """
    Diş dikey olarak (+Y) hizalandıktan sonra, üst oklüzal kesitteki 
    en uzun yatay ekseni (Mesio-Distal) bularak X eksenine kilitler.
    """
    verts = np.asarray(mesh.vertices)
    y_max = float(verts[:, 1].max())

    # ORANSAL TUZAK KALDIRILDI: Kök uzunluğundan bağımsız olarak
    # sadece en üstteki 2.5 mm'lik taç alanını yatay kilit için referans alıyoruz.
    top_thresh = y_max - 2.5
    top_mask = verts[:, 1] > top_thresh

    # Güvenlik kontrolü: Eğer model çok küçükse veya nokta azsa koruma kalkanı
    if top_mask.sum() < 30:
        y_min = float(verts[:, 1].min())
        top_mask = verts[:, 1] > (y_min + (y_max - y_min) * 0.5)

    pts_2d = verts[top_mask][:, [0, 2]]

    cov_2d = np.cov(pts_2d.T)
    _, evecs_2d = np.linalg.eigh(cov_2d)

    major_axis = evecs_2d[:, 1]  
    angle = np.arctan2(major_axis[1], major_axis[0])

    mesh.rotate(
        mesh.get_rotation_matrix_from_xyz((0.0, -angle, 0.0)),
        center=(0, 0, 0)
    )
    return mesh


def _fallback_pca_alignment(mesh):
    """
    Nadir durumlarda (çukur barındırmayan dümdüz modeller, hatalı taramalar vb.)
    Convex Hull yön bulamazsa sistemin çökmemesini sağlayan yedek kaba dikey hizalama.
    """
    print("   ⚠️ Taç tespiti başarısız oldu. Yedek dikey PCA yöntemi uygulanıyor...")
    verts = np.asarray(mesh.vertices)
    cov = np.cov(verts.T)
    _, evecs = np.linalg.eigh(cov)

    target_axes = np.zeros((3, 3))
    target_axes[:, 0] = evecs[:, 1]   # X
    target_axes[:, 1] = evecs[:, 2]   # Y (En uzun geometrik eksen)
    target_axes[:, 2] = evecs[:, 0]   # Z
    
    R_pca = np.linalg.inv(target_axes)
    mesh.rotate(R_pca, center=(0, 0, 0))
    return mesh


def align_single_file(source_path, output_path):
    """
    Ana yürütücü fonksiyon. Modeli yükler, taç çukurunu gökyüzüne çevirir,
    Mesio-Distal ekseni kilitler ve debug dosyası oluşturmadan doğrudan kaydeder.
    """
    print(f"\n{'='*55}")
    print(f"  TAÇ ODAKLI DETERMINISTIK HİZALAMA")
    print(f"  Kaynak: {os.path.basename(source_path)}")
    print(f"{'='*55}")

    mesh = o3d.io.read_triangle_mesh(source_path)
    if mesh.is_empty():
        print("❌ Dosya okunamadı veya model boş!")
        return

    # Geometrik ön temizlik
    mesh.remove_duplicated_vertices()
    mesh.remove_degenerate_triangles()
    mesh.compute_vertex_normals()

    # Modeli manipülasyon kolaylığı için orijine (0, 0, 0) taşı
    center = np.mean(np.asarray(mesh.vertices), axis=0)
    mesh.translate(-center)

    verts = np.asarray(mesh.vertices)
    normals = np.asarray(mesh.vertex_normals)

    # 1. ADIM: Taç/Kavite bölgesini tespit et ve açılış yönünü bul
    direction, _ = find_cavity_opening_direction(verts, normals)

    # 2. ADIM: Dikey Hizalama (Kavite ağzını dimdik +Y yönüne sabitleme)
    if direction is not None:
        print("   ✅ Taç geometrisi doğrulandı. Kavite eksenine göre döndürülüyor...")
        R = rotation_align(direction, np.array([0.0, 1.0, 0.0]))
        mesh.rotate(R, center=(0, 0, 0))
    else:
        mesh = _fallback_pca_alignment(mesh)

    # 3. ADIM: Yatay Hizalama (Mesio-Distal genişliği X eksenine oturtma)
    print("   ✅ Üst %20 oklüzal dilim referansıyla yatay eksen kilitleniyor...")
    mesh = _normalize_xz_rotation(mesh)

    # Normalleri güncelle ve diske nihai çıktıyı yaz (Hızlı - Debug Dosyaları Yok)
    mesh.compute_vertex_normals()
    mesh.compute_triangle_normals()
    
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    o3d.io.write_triangle_mesh(output_path, mesh, write_ascii=False)
    print(f"✅ Hizalama işlemi başarıyla tamamlandı -> {output_path}")