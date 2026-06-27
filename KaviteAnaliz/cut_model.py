"""
cut_model.py
────────────
Hizalanmış diş modelini kavite tabanının 1 mm altından keser.

Yöntem: Köke veya toplam boya bağlı oranlar tamamen kaldırılmıştır.
Oklüzal tepeden (Y_max) aşağıya doğru mutlak milimetrik analiz yapar.
Uzun veya kısa kök yapılarından etkilenmez.
"""

import os
import numpy as np
import open3d as o3d
from cavity_utils import compute_hull_depth

# ─────────────────────────────────────────────────────────────────────────────
# KAVİTE TABANI Y KOORDINATINI BUL (MUTLAK DEĞER ODAKLI)
# ─────────────────────────────────────────────────────────────────────────────
def find_cavity_floor_y(vertices, normals, y_max):
    """
    Kavite tabanının Y koordinatını kök oranlarından bağımsız olarak bulur.
    Hizalanmış modelde arama bölgesi oklüzal tepeden (Y_max) aşağıya doğru mutlak 6.0 mm'dir.
    """
    # ── Yöntem 1: Convex Hull Derinliği ve Yukarı Bakan Normaller ───────────
    print("   Taban tespiti: Convex Hull mutlak derinliği deneniyor...")
    depth, hull = compute_hull_depth(vertices)

    if depth is not None:
        inside_mask = depth > 0
        if inside_mask.sum() >= 30:
            # Model hizalı olduğundan, gerçek taban noktaları yukarı (+Y) bakar
            up_in_hull = inside_mask & (normals[:, 1] > 0.60)

            if up_in_hull.sum() >= 20:
                candidate_ys = vertices[up_in_hull, 1]
                ys_s = np.sort(candidate_ys)
                min_cluster = max(15, len(ys_s) // 25)

                for i in range(len(ys_s)):
                    # 0.8 mm'lik hassas pencere ile taban düzlüğü aranır
                    band = ys_s[(ys_s >= ys_s[i]) & (ys_s <= ys_s[i] + 0.8)]
                    if len(band) >= min_cluster:
                        floor_y = float(np.median(band))
                        print(f"   🎯 Taban (Hull + Normal): Y={floor_y:.2f} ({len(band)} nokta)")
                        return floor_y

            # Eğer yukarı bakan normal azsa, mutlak en derin bölgenin alt sınırını referans al
            max_d = np.max(depth[inside_mask])
            deep_mask = inside_mask & (depth > (max_d * 0.60))
            if deep_mask.sum() >= 20:
                floor_y = float(np.percentile(vertices[deep_mask, 1], 20))
                print(f"   🎯 Taban (Hull Mutlak Eşik): Y={floor_y:.2f}")
                return floor_y

    # ── Yöntem 2: Kayan Pencere (Yedek - Üstten Aşağı Mutlak Arama) ──────────
    print("   Taban tespiti: Üstten aşağı mutlak kayan pencere deneniyor...")
    up_facing = normals[:, 1] > 0.78
    
    # Oranlar kaldırıldı: Arama bölgesi sadece tacın ilk 6 mm'lik oklüzal kısmıdır.
    # Bu mesafe standart bir dental kuron yüksekliğine göre güvenli bölgedir.
    crown_zone_mask = vertices[:, 1] > (y_max - 6.0)
    cands = np.where(up_facing & crown_zone_mask)[0]

    if len(cands) < 30:
        print("   ⚠️ Yedek taban bulma yöntemi de başarısız oldu.")
        return None

    ys = np.sort(vertices[cands, 1])
    mc = max(15, len(ys) // 25)

    for i in range(len(ys)):
        band = ys[(ys >= ys[i]) & (ys <= ys[i] + 1.0)]
        if len(band) >= mc:
            floor_y = float(np.median(band))
            print(f"   🎯 Taban (Mutlak Kayan Pencere): Y={floor_y:.2f} ({len(band)} nokta)")
            return floor_y

    fallback = float(np.percentile(vertices[cands, 1], 10))
    print(f"   ⚠️ Küme bulunamadı. Fallback Taban: Y={fallback:.2f}")
    return fallback


# ─────────────────────────────────────────────────────────────────────────────
# ANA KESİM FONKSİYONU
# ─────────────────────────────────────────────────────────────────────────────
def crop_bottom_of_mesh(input_path, output_path, cut_ratio=None, axis=None, visualize=False):
    """
    Kavite tabanını tespit edip tabanın 1 mm altından itibaren tüm alt kök yapısını keser.
    Eski API parametreleri (cut_ratio, axis) uyumluluk adına korunmuş ancak işlevsizleştirilmiştir.
    """
    gap_mm = 1.0
    print(f"\n{'─'*50}")
    print(f"  MUTLAK KESİM SİSTEMİ BAŞLADI: {os.path.basename(input_path)}")
    print(f"{'─'*50}")

    if not os.path.exists(input_path):
        print(f"❌ Dosya bulunamadı: {input_path}")
        return

    try:
        mesh = o3d.io.read_triangle_mesh(input_path)
    except Exception as e:
        print(f"❌ Dosya okunamadı: {e}")
        return

    if mesh.is_empty():
        print("❌ Model içeriği boş!")
        return

    mesh.remove_duplicated_vertices()
    mesh.remove_degenerate_triangles()
    mesh.compute_vertex_normals()

    vertices = np.asarray(mesh.vertices)
    normals = np.asarray(mesh.vertex_normals)

    y_min = float(vertices[:, 1].min())
    y_max = float(vertices[:, 1].max())
    print(f"   Mevcut Diş Sınırları -> En Alt Y: {y_min:.2f} | En Üst Y: {y_max:.2f}")

    # Kavite tabanını mutlak değerlerle hesapla
    floor_y = find_cavity_floor_y(vertices, normals, y_max)

    if floor_y is None:
        # Tamamen başarısızlık durumunda oklüzal tepeden 4.5 mm aşağısını kes (Kök bağımsız koruma)
        cut_line_y = y_max - 4.5
        print(f"⚠️ Kritik Fallback Kesim Çizgisi (Tepeden -4.5mm): Y={cut_line_y:.2f}")
    else:
        cut_line_y = floor_y - gap_mm
        print(f"✂️ Kesim Noktası Belirlendi: Taban({floor_y:.2f}) - {gap_mm}mm Pay = Y_{cut_line_y:.2f}")

    # Bounding Box ile Kesme İşlemi
    bbox = mesh.get_axis_aligned_bounding_box()
    new_min = np.array(bbox.get_min_bound(), dtype=float)
    new_max = np.array(bbox.get_max_bound(), dtype=float)

    if new_min[1] >= cut_line_y:
        print("✅ Diş zaten taban payından daha kısa, kesim sınırları içerisinde.")
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        o3d.io.write_triangle_mesh(output_path, mesh, write_ascii=False)
        return

    # Sadece dikey alt sınırı yeni kesim çizgisine çekiyoruz
    new_min[1] = cut_line_y
    crop_box = o3d.geometry.AxisAlignedBoundingBox(min_bound=new_min, max_bound=new_max)

    if visualize:
        crop_box.color = (1, 0, 0)
        o3d.visualization.draw_geometries([mesh, crop_box], window_name="Mutlak Kesim Önizleme")

    cropped = mesh.crop(crop_box)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    if not cropped.is_empty() and len(np.asarray(cropped.vertices)) > 0:
        cropped.remove_unreferenced_vertices()
        cropped.remove_degenerate_triangles()
        cropped.remove_duplicated_vertices()
        cropped.compute_vertex_normals()
        cropped.compute_triangle_normals()
        o3d.io.write_triangle_mesh(output_path, cropped, write_ascii=False)
        print(f"✅ Kesim tamamlandı. Kalan Taç Yüksekliği: {y_max - cut_line_y:.2f} mm")
    else:
        print("❌ Hata: Kesim sonrası boş model oluştu! Orijinal model korunuyor.")
        o3d.io.write_triangle_mesh(output_path, mesh, write_ascii=False)