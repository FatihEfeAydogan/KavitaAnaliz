import open3d as o3d
import os

def check_mesh_stats(file_path):
    print(f"\n📂 Dosya okunuyor: {file_path}")
    
    # 1. Dosya Kontrolü
    if not os.path.exists(file_path):
        print("❌ HATA: Dosya bulunamadı!")
        return

    # 2. Modeli Sadece Okuma Modunda Yükle (Diske yazma yapmaz)
    try:
        mesh = o3d.io.read_triangle_mesh(file_path)
    except Exception as e:
        print(f"❌ HATA: Dosya okunamadı. {e}")
        return

    if mesh.is_empty():
        print("⚠️ UYARI: Dosya boş veya bozuk.")
        return

    # 3. İstatistikleri Al
    vertex_count = len(mesh.vertices)
    triangle_count = len(mesh.triangles)

    # 4. Sonuçları Yazdır
    print("-" * 40)
    print(f"📊 ANALİZ SONUCU: {os.path.basename(file_path)}")
    print("-" * 40)
    print(f"🟣 Vertex (Nokta) Sayısı : {vertex_count:,}")  # Binlik ayracı ile yazar
    print(f"🔺 Triangle (Üçgen) Sayısı: {triangle_count:,}")
    print("-" * 40)

    # 5. Projenin Kurallarına Göre Yorumla
    if vertex_count > 300000:
        print("⚠️  DURUM: ÇOK YÜKSEK DETAY")
        print("   -> Sistemin bunu analizde otomatik olarak 300.000 altına düşürecektir.")
        print("   -> (Voxel Clustering devreye girer)")
    elif vertex_count < 15000:
        print("⚠️  DURUM: ÇOK DÜŞÜK DETAY")
        print("   -> Sistemin buna analizde yapay noktalar ekleyecektir.")
        print("   -> (Subdivision devreye girer)")
    else:
        print("✅  DURUM: İDEAL ARALIK")
        print("   -> Herhangi bir optimizasyona uğramadan analize girer.")
    print("-" * 40)

# --- AYARLAR ---
# Buraya kontrol etmek istediğin dosyanın yolunu yaz
FILE_TO_CHECK = "static/uploads/z.stl" 

if __name__ == "__main__":
    check_mesh_stats(FILE_TO_CHECK)