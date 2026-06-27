"""
cavity_utils.py
───────────────
Convex Hull (Dış Zarf) ve İçbükeylik (Concavity) Analizi ile
Taç ve Kavite Bölgesi Tespit Araçları.
"""

import numpy as np
from scipy.spatial import ConvexHull

def compute_hull_depth(vertices, max_sample=40000):
    """
    Her vertex için 'Convex Hull içi derinlik' (zarfa olan uzaklık) değerini hesaplar.
    Derinlik ne kadar büyükse, nokta kavite içinde o kadar derindedir.
    """
    n = len(vertices)

    # Büyük mesh'lerde bellek ve hız optimizasyonu için subsample
    if n > max_sample:
        idx_s = np.random.choice(n, max_sample, replace=False)
        hull_verts = vertices[idx_s]
    else:
        hull_verts = vertices

    try:
        hull = ConvexHull(hull_verts)
    except Exception as e:
        print(f"⚠️ ConvexHull hesaplanamadı: {e}")
        return None, None

    eqs = hull.equations  # [n_faces, 4] -> ax + by + cz + d = 0

    # Noktaları parça parça işleyerek RAM taşmasını önler
    chunk = 8000
    max_dists = np.zeros(n, dtype=np.float64)

    for start in range(0, n, chunk):
        end = min(start + chunk, n)
        v = vertices[start:end]                         
        d = v @ eqs[:, :3].T + eqs[:, 3]               
        max_dists[start:end] = d.max(axis=1)

    # Değerleri pozitife çeviriyoruz: Büyük değer = Daha derin çukur
    depth = -max_dists  
    return depth, hull


def find_cavity_opening_direction(vertices, normals, depth_percentile=60):
    """
    Taç üzerindeki kavitenin açılma yönünü tespit eder.
    Mutlak derinlik bandı kullanarak kök uzunluğundan bağımsız çalışır.
    """
    print("🔍 Convex Hull derinlik analizi başladı...")
    depth, hull = compute_hull_depth(vertices)

    if depth is None:
        return None, None

    inside_mask = depth > 0
    n_inside = int(inside_mask.sum())
    print(f"   Zarf içi nokta sayısı: {n_inside} / {len(vertices)}")

    if n_inside < 20:
        print("⚠️ Zarf içinde yeterli nokta yok — tarama kalitesi düşük olabilir.")
        return None, None

    # MUTLAK DERİNLİK FİLTRESİ: Köke bağlı nokta yoğunluğu tuzağını engeller
    max_depth = np.max(depth[inside_mask])
    
    # Maksimum derinliğin sadece belirlenen yüzdelik derinlik bandında kalanları al (Örn: en derin %40)
    d_thresh = max_depth * (depth_percentile / 100.0)
    deep_mask = inside_mask & (depth > d_thresh)
    n_deep = int(deep_mask.sum())
    print(f"   Derin taç/kavite noktaları: {n_deep}")

    # Bu derin çukurdaki yüzey normallerinin ortalaması gerçek açılış yönünü verir
    mean_norm = np.mean(normals[deep_mask], axis=0)
    mag = np.linalg.norm(mean_norm)

    if mag < 0.05:
        # Normaller birbirini nötrlediyse derinlik bandını daralt (%80 derinliğe in)
        d_thresh = max_depth * 0.80
        deep_mask = inside_mask & (depth > d_thresh)
        mean_norm = np.mean(normals[deep_mask], axis=0)
        mag = np.linalg.norm(mean_norm)
        if mag < 0.05:
            print("⚠️ Ortalama normal vektörü çok küçük.")
            return None, inside_mask

    direction = mean_norm / mag
    print(f"   Kavite açılma yönü (Birim Vektör): {np.round(direction, 3)}")
    return direction, inside_mask


def rotation_align(source_vec, target_vec):
    """
    source_vec vektörünü target_vec vektörüne hizalayan 3x3 rotasyon matrisi üretir.
    Rodrigues formülü kullanılır.
    """
    a = np.asarray(source_vec, dtype=float)
    b = np.asarray(target_vec, dtype=float)
    a /= np.linalg.norm(a)
    b /= np.linalg.norm(b)

    v = np.cross(a, b)
    c = np.dot(a, b)

    if np.abs(c + 1.0) < 1e-6:  # 180 derecelik tam ters yön durumu
        perp = np.array([1.0, 0.0, 0.0]) if abs(a[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
        axis = np.cross(a, perp)
        axis /= np.linalg.norm(axis)
        return 2.0 * np.outer(axis, axis) - np.eye(3)

    if np.abs(c - 1.0) < 1e-6:  # Zaten aynı yöne bakıyorlar
        return np.eye(3)

    s = np.linalg.norm(v)
    K = np.array([[0, -v[2], v[1]],
                  [v[2],  0, -v[0]],
                  [-v[1], v[0],  0]])
    return np.eye(3) + K + K @ K * ((1.0 - c) / s ** 2)