import mysql.connector
import os  # <--- Eklendi

# Veritabanı bağlantı ayarları
db_config = {
    "host": "localhost",
    "user": "root",
    "password": "root"  # Şifrenizi buraya yazdığınızdan emin olun
}

def init_db():
    try:
        # MySQL sunucusuna bağlan
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        
        # --- GÜNCELLEME BAŞLANGICI ---
        # Bu dosyanın (setup_db.py) bulunduğu klasörü bul
        base_dir = os.path.dirname(os.path.abspath(__file__))
        # init.sql yolunu buna göre oluştur
        sql_file_path = os.path.join(base_dir, 'init.sql')
        
        print(f"Dosya aranıyor: {sql_file_path}") # Kontrol için yolu yazdır

        # init.sql dosyasını oku
        with open(sql_file_path, 'r', encoding='utf-8') as f:
            sql_script = f.read()
        # --- GÜNCELLEME BİTİŞİ ---
        
        # Komutları noktalı virgüle göre ayırıp tek tek çalıştır
        commands = sql_script.split(';')
        
        for command in commands:
            if command.strip():
                cursor.execute(command)
                
        print("✅ Veritabanı ve tablolar başarıyla oluşturuldu!")
        
    except FileNotFoundError:
        print("❌ HATA: 'init.sql' dosyası bulunamadı!")
        print(f"Lütfen '{sql_file_path}' yolunda dosyanın olduğundan emin olun.")
    except mysql.connector.Error as err:
        print(f"❌ Veritabanı Hatası: {err}")
        print("İpucu: Şifrenizin doğru olduğundan emin olun.")
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

if __name__ == "__main__":
    init_db()