import numpy as np
import trimesh
from skimage import measure
from scipy import ndimage
from scipy.ndimage import distance_transform_edt, gaussian_filter
import warnings
warnings.filterwarnings('ignore')

# ═══════════════════════════════════════════════════════════════
# v5 — Gerçekçi Molar Geometrisi
#
# Önceki versiyonlardaki temel sorunlar:
#   1. Crown çok yassı → heightmap profili %65 taban veriyor,
#      gerçek diş gibi belirgin kusp yükseklikleri yok.
#   2. Kök daralması yeterince agresif değil → %60 erozyon ile
#      Three.js'te fark edilmiyor.
#   3. Cavity derinliği yanlış hesaplanan layer sayısı nedeniyle
#      görsel olarak sığ kalıyor.
#
# v5 çözümleri:
#   1. Crown profili: güçlü kubbe (dist^0.35 + yüksek taban oranı)
#      → belirgin oklüzal yükseklik, gerçek molar görünümü
#   2. Kök: 3 bölgeli profil (crown-base / mid-root / apex)
#      Her bölgede farklı erozyon hızı → gerçek kök silueti
#   3. Derinlik: sabit 3.16mm, layer = round(3.16 / mm_per_px_up)
# ═══════════════════════════════════════════════════════════════

DEFAULT_CAVITY_DEPTH_MM = 3.16   # analiz.py'de dinamik yapılana kadar sabit


def _erode_mask_px(mask_bool, pixels):
    if pixels < 0.5:
        return mask_bool
    struct = ndimage.generate_binary_structure(2, 1)
    return ndimage.binary_erosion(mask_bool, structure=struct,
                                  iterations=max(1, int(round(pixels))))


def create_crown_heightmap(tooth_mask, mm_per_px_up, crown_height_mm=6.0):
    """
    Oklüzal yüzey için heightmap — 4 kusp + merkezi fossa geometrisi.
    Gerçek molar görünümü: köşelerde yüksek kusp tepeleri, ortada çukur.
    """
    t_bool = (tooth_mask > 128).astype(np.float32)
    dist   = distance_transform_edt(t_bool)
    d_max  = dist.max()
    if d_max < 0.01:
        return None

    h, w   = t_bool.shape
    layers = max(40, int(round(crown_height_mm / mm_per_px_up)))

    # Diş sınırlayıcı kutusu → normalize koordinatlar
    ys, xs = np.where(t_bool > 0)
    y0, y1 = ys.min(), ys.max()
    x0, x1 = xs.min(), xs.max()
    Y = np.zeros((h, w), dtype=np.float32)
    X = np.zeros((h, w), dtype=np.float32)
    Y[t_bool > 0] = (np.mgrid[0:h, 0:w][0][t_bool > 0] - y0) / max(y1 - y0, 1)
    X[t_bool > 0] = (np.mgrid[0:h, 0:w][1][t_bool > 0] - x0) / max(x1 - x0, 1)

    # 4 köşede kusp merkezleri (normalize: 0=mesial/buccal, 1=distal/lingual)
    # Molar için tipik: mesio-buccal, disto-buccal, mesio-lingual, disto-lingual
    cusp_centers = [(0.25, 0.25), (0.75, 0.25), (0.25, 0.75), (0.75, 0.75)]
    cusp_heights = [1.0, 0.90, 0.95, 0.85]  # MB en yüksek
    cusp_width   = 0.38                       # Gaussian genişliği

    cusp_map = np.zeros((h, w), dtype=np.float32)
    for (cx_n, cy_n), ch_n in zip(cusp_centers, cusp_heights):
        dx = X - cx_n
        dy = Y - cy_n
        gauss = np.exp(-(dx**2 + dy**2) / (2 * cusp_width**2))
        cusp_map = np.maximum(cusp_map, gauss * ch_n)

    cusp_map[t_bool == 0] = 0.0

    # Merkezi fossa → kusp haritasından çıkar (çukur oluştur)
    # Sadece diş içindeki bölgede uygula
    fossa_x, fossa_y = 0.5, 0.5
    dx_f = X - fossa_x
    dy_f = Y - fossa_y
    fossa_dip = 0.30 * np.exp(-(dx_f**2 + dy_f**2) / (2 * 0.15**2))
    fossa_dip[t_bool == 0] = 0.0
    cusp_map = np.clip(cusp_map - fossa_dip, 0.0, 1.0)

    # Kenar kalınlığı: dist ile blend → kenarlar çok ince olmasın
    edge_base = np.power(np.clip(dist / d_max, 0, 1), 0.6) * 0.55
    profile = cusp_map * 0.45 + edge_base
    profile = np.clip(profile, 0.0, 1.0)
    profile[t_bool == 0] = 0.0

    hmap = profile * layers

    sigma = max(1.5, 1.8 / mm_per_px_up)
    hmap  = gaussian_filter(hmap, sigma=sigma)
    hmap[t_bool == 0] = 0.0
    return hmap


def create_cavity_depth_map(cav_mask, mm_per_px_up,
                             cavity_depth_mm=DEFAULT_CAVITY_DEPTH_MM):
    """
    Kavite derinlik haritası.
    Sabit depth = 3.16mm (daha sonra dinamik yapılacak).
    """
    c_bool = (cav_mask > 128).astype(np.float32)
    layers = max(5, int(round(cavity_depth_mm / mm_per_px_up)))

    print(f"    [Kavite] depth={cavity_depth_mm:.2f}mm  "
          f"mm_per_px_up={mm_per_px_up:.4f}  layers={layers}px  "
          f"gerçek={layers * mm_per_px_up:.2f}mm")

    dist  = distance_transform_edt(c_bool)
    d_max = dist.max()
    if d_max < 0.01:
        return np.zeros_like(c_bool, dtype=np.float32), 0

    norm   = dist / d_max
    floor  = 0.82 + 0.18 * norm             # içbükey taban
    dmap   = c_bool * floor * layers

    sigma  = max(1.2, 1.5 / mm_per_px_up)
    dmap   = gaussian_filter(dmap, sigma=sigma)
    dmap[c_bool == 0] = 0.0
    return dmap, layers


def build_molar_volume(tooth_mask, hmap, mm_per_px_up,
                        crown_height_mm=6.0, root_height_mm=5.0, pad=4):
    """
    Gerçek molar için 3 bölgeli volume:

    Z (aşağıdan yukarıya):
    ┌────────────────────────────────────────────┐
    │ APEX  (root ucu)  — en küçük kesit         │  %25 root
    │ MID-ROOT          — orta daralma           │  %50 root
    │ ROOT-BASE (cervix)— crown'a geçiş          │  %25 root
    │ CROWN             — oklüzal heightmap       │
    └────────────────────────────────────────────┘

    Erozyon profili (aşağıdan yukarıya):
      apex:      dist_max × 0.80  (çok küçük kesit)
      mid-root:  dist_max × 0.45
      cervix:    dist_max × 0.15  (neredeyse tam genişlik)
      crown:     heightmap
    """
    t_bool    = (tooth_mask > 128)
    dist_2d   = distance_transform_edt(t_bool)
    max_r     = dist_2d.max()               # oklüzal maskenin max iç yarıçapı

    crown_L   = max(40, int(round(crown_height_mm / mm_per_px_up)))
    root_L    = max(30, int(round(root_height_mm  / mm_per_px_up)))
    total_Z   = root_L + crown_L + 3       # +3: alt/üst boş katmanlar

    h, w      = tooth_mask.shape
    vol       = np.zeros((total_Z, h + 2*pad, w + 2*pad), dtype=np.bool_)

    t_pad     = np.pad(t_bool, pad, mode='constant', constant_values=False)
    h_pad     = np.pad(hmap,   pad, mode='constant', constant_values=0.0)

    # ── ROOT bölgesi (Z = 1 .. root_L) ──────────────────────────────────
    # Erozyon miktarı: apex → cervix doğrusal değil, 3 bölgeli

    apex_frac   = 0.25    # root'un alt %25'i = apex
    mid_frac    = 0.75    # root'un alt %75'i = mid-root bitiş

    for zi in range(1, root_L + 1):
        t = (zi - 1) / max(root_L - 1, 1)   # 0=apex, 1=cervix

        # Üç bölgeli erozyon profili
        if t < apex_frac:
            # Apex: hızla daralır
            local_t = t / apex_frac
            erode_px = max_r * (0.80 - 0.35 * local_t)   # 0.80→0.45
        elif t < mid_frac:
            # Mid-root: daha yavaş daralma
            local_t = (t - apex_frac) / (mid_frac - apex_frac)
            erode_px = max_r * (0.45 - 0.30 * local_t)   # 0.45→0.15
        else:
            # Cervix: crown'a yumuşak geçiş
            local_t = (t - mid_frac) / (1.0 - mid_frac)
            erode_px = max_r * (0.15 - 0.15 * local_t)   # 0.15→0.00

        if erode_px < 0.5:
            layer = t_pad
        else:
            small = _erode_mask_px(t_bool, erode_px)
            layer = np.pad(small, pad, mode='constant', constant_values=False)

        vol[zi] = layer

    # ── CROWN bölgesi (Z = root_L+1 .. root_L+crown_L) ──────────────────
    crown_base = root_L + 1
    max_h_val  = int(h_pad.max()) + 1

    for z_loc in range(1, max_h_val + 1):
        z_glob = crown_base + z_loc - 1
        if z_glob >= total_Z - 1:
            break
        vol[z_glob] = h_pad >= z_loc

    # Crown tabanı solid (kök-crown geçişi)
    vol[crown_base] = t_pad

    return vol, root_L, crown_L


def apply_cavity(vol, cav_mask, hmap, root_L, cavity_depth_mm, mm_per_px_up, pad=4):
    """
    Kavite oyma — basit ve doğru:
    - cavity_depth_mm doğrudan layer sayısına çevrilir
    - Her kavite pikseli için: yüzey katmanından tam derinlik kadar yukarı doğru sil
    - Dmap, floor_factor gibi karmaşıklık yok
    """
    # Kaç layer = istenen derinlik?
    dep_layers = max(2, int(round(cavity_depth_mm / mm_per_px_up)))
    print(f"    [apply_cavity] cavity_depth_mm={cavity_depth_mm:.2f}  "
          f"mm_per_px_up={mm_per_px_up:.4f}  dep_layers={dep_layers}  "
          f"gerçek={dep_layers * mm_per_px_up:.3f}mm")

    c_bool = (cav_mask > 128)
    c_pad  = np.pad(c_bool, pad, mode='constant', constant_values=False)
    h_pad  = np.pad(hmap,   pad, mode='constant', constant_values=0.0)
    cb     = root_L + 1

    ys, xs = np.where(c_pad)
    for y, x in zip(ys, xs):
        # Oklüzal yüzey katmanı bu piksel için
        surf_z = cb + int(round(h_pad[y, x]))
        # Alt sınır: yüzeyden tam dep_layers aşağı
        bot_z  = surf_z - dep_layers
        # Crown tabanını delme
        bot_z  = max(cb + 1, bot_z)
        if surf_z > bot_z:
            vol[bot_z:surf_z + 1, y, x] = False
    return vol


def morph_smooth(vol, iters=2):
    s   = ndimage.generate_binary_structure(3, 1)
    vol = ndimage.binary_dilation(vol, structure=s, iterations=iters)
    vol = ndimage.binary_erosion( vol, structure=s, iterations=iters)
    return vol


# ═══════════════════════════════════════════════════════════════
# ANA FONKSİYON
# ═══════════════════════════════════════════════════════════════

def create_composite_stl(
    tooth_mask,
    cav_mask,
    mm_per_px,
    output_path,
    cavity_depth      = DEFAULT_CAVITY_DEPTH_MM,
    base_depth        = 6.0,    # crown yüksekliği (mm)
    root_depth        = 5.0,    # kök yüksekliği (mm)
    smooth_iterations = 22,
    voxel_upsample    = 2,
    feature_angle_deg = 28,
):
    PAD = 4

    # ── Supersampling ────────────────────────────────────────────────────
    if voxel_upsample > 1:
        u  = voxel_upsample
        tm = ndimage.zoom(tooth_mask.astype(np.float32), u, order=1)
        cm = ndimage.zoom(cav_mask.astype(np.float32),   u, order=1)
        mp = mm_per_px / u
        tm = (tm > 64).astype(np.uint8) * 255
        cm = (cm > 64).astype(np.uint8) * 255
    else:
        tm, cm, mp = tooth_mask, cav_mask, mm_per_px

    print(f">>> STL v6  mm_per_px={mm_per_px:.4f}  mp={mp:.4f}  upsample={voxel_upsample}x")

    # ── Heightmap ────────────────────────────────────────────────────────
    hmap = create_crown_heightmap(tm, mp, base_depth)
    if hmap is None:
        print(">>> STL HATA: heightmap yok"); return False

    # ── Volume ──────────────────────────────────────────────────────────
    vol, root_L, crown_L = build_molar_volume(
        tm, hmap, mp,
        crown_height_mm=base_depth,
        root_height_mm=root_depth,
        pad=PAD,
    )
    print(f"    root={root_L}px={root_L*mp:.1f}mm  crown={crown_L}px={crown_L*mp:.1f}mm")

    # ── Kaviteyi Oy (direkt mm → layer, dmap yok) ────────────────────────
    vol = apply_cavity(vol, cm, hmap, root_L, cavity_depth, mp, pad=PAD)

    if not np.any(vol):
        print(">>> STL HATA: volume boş"); return False

    # ── Morfolojik pre-smooth ────────────────────────────────────────────
    vol = morph_smooth(vol, iters=2)

    # ── Marching Cubes ───────────────────────────────────────────────────
    try:
        verts, faces, normals, _ = measure.marching_cubes(
            vol.astype(np.float32), level=0.5,
            step_size=1, allow_degenerate=False)
    except Exception as e:
        print(f">>> STL HATA MC: {e}"); return False

    # ── mm'ye çevir ──────────────────────────────────────────────────────
    vm = np.zeros_like(verts, dtype=np.float64)
    vm[:, 0] = (verts[:, 2] - PAD) * mp    # X
    vm[:, 1] = (verts[:, 1] - PAD) * mp    # Y
    vm[:, 2] =  verts[:, 0]        * mp    # Z (0=apex, yukarı=oklüzal)

    mesh = trimesh.Trimesh(vertices=vm, faces=faces, process=True)
    if not len(mesh.faces):
        print(">>> STL HATA: mesh boş"); return False

    # ── Feature-preserving Taubin smooth ────────────────────────────────
    trimesh.smoothing.filter_taubin(mesh, lamb=0.5, nu=-0.53, iterations=5)

    if len(mesh.face_adjacency_angles) > 0:
        ang_thresh  = np.radians(feature_angle_deg)
        sharp_e     = mesh.face_adjacency_edges[mesh.face_adjacency_angles > ang_thresh]
        sharp_v     = np.unique(sharp_e.flatten())

        m2 = mesh.copy()
        trimesh.smoothing.filter_taubin(m2, lamb=0.5, nu=-0.53, iterations=smooth_iterations)

        mask_s = np.ones(len(mesh.vertices), dtype=bool)
        mask_s[sharp_v] = False
        mesh.vertices[mask_s] = m2.vertices[mask_s]
        trimesh.smoothing.filter_taubin(mesh, lamb=0.5, nu=-0.53, iterations=2)
    else:
        trimesh.smoothing.filter_taubin(mesh, lamb=0.5, nu=-0.53, iterations=smooth_iterations)

    try:
        trimesh.smoothing.filter_humphrey(mesh, alpha=0.1, beta=0.5, iterations=5)
    except Exception:
        pass

    # ── Merkeze hizala — geometrik merkez, taban Z=0 ─────────────────────
    # X,Y: bounding box merkezi   Z: taban sıfırda
    # Bu sayede Three.js'te mesh.rotation.x vb. kendi ekseni etrafında döner.
    b  = mesh.bounds
    cx = (b[0, 0] + b[1, 0]) / 2
    cy = (b[0, 1] + b[1, 1]) / 2
    cz = b[0, 2]               # taban sıfırda kalır

    mesh.apply_translation([-cx, -cy, -cz])

    # Vertices'i centroid'e göre de doğrula (trimesh.centroid bazen kayar)
    centroid = mesh.centroid
    if abs(centroid[0]) > 0.5 or abs(centroid[1]) > 0.5:
        mesh.apply_translation([-centroid[0], -centroid[1], 0])

    mesh.export(output_path)
    b2 = mesh.bounds
    print(f">>> STL OK: {len(mesh.faces)} yüz  {len(mesh.vertices)} vertex")
    print(f"    X={b2[1,0]-b2[0,0]:.1f}mm  Y={b2[1,1]-b2[0,1]:.1f}mm  "
          f"Z={b2[1,2]-b2[0,2]:.1f}mm")
    return True


# ── Preset'ler ───────────────────────────────────────────────────────────────

def create_composite_stl_highquality(tooth_mask, cav_mask, mm_per_px, output_path,
                                      cavity_depth=DEFAULT_CAVITY_DEPTH_MM,
                                      base_depth=6.0):
    return create_composite_stl(
        tooth_mask, cav_mask, mm_per_px, output_path,
        cavity_depth=cavity_depth, base_depth=base_depth, root_depth=5.0,
        smooth_iterations=28, voxel_upsample=2, feature_angle_deg=28,
    )

def create_composite_stl_fast(tooth_mask, cav_mask, mm_per_px, output_path,
                               cavity_depth=DEFAULT_CAVITY_DEPTH_MM,
                               base_depth=6.0):
    return create_composite_stl(
        tooth_mask, cav_mask, mm_per_px, output_path,
        cavity_depth=cavity_depth, base_depth=base_depth, root_depth=5.0,
        smooth_iterations=12, voxel_upsample=1, feature_angle_deg=32,
    )