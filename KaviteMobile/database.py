import mysql.connector
from mysql.connector import Error

DB_CONFIG = {'host': 'localhost', 'user': 'root', 'password': 'root'} 

def get_db_connection():
    config = DB_CONFIG.copy()
    config['database'] = 'kavite_mobile_db'
    return mysql.connector.connect(**config)

def init_db():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("CREATE DATABASE IF NOT EXISTS kavite_mobile_db")
        cursor.execute("USE kavite_mobile_db")
        
        # DİKKAT: Her başlatmada verilerin silinmesini önlemek için DROP TABLE komutu KALDIRILDI!
        # Eski kayıtlar artık silinmeyecek ve liste alt alta uzamaya devam edecek.
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS kavite_sonuclar (
                id INT AUTO_INCREMENT PRIMARY KEY,
                ogrenci_ad VARCHAR(100),
                ogrenci_soyad VARCHAR(100),
                ogrenci_no VARCHAR(50),
                img_90 VARCHAR(255),
                drawn_img_90 VARCHAR(255),
                stl_file VARCHAR(255),
                
                outline_form FLOAT, outline_form_score INT,
                mesial_isthmus_width FLOAT, mesial_isthmus_width_score INT,
                distal_isthmus_width FLOAT, distal_isthmus_width_score INT,
                buccal_lingual_width FLOAT, buccal_lingual_width_score INT,
                mesio_distal_width FLOAT, mesio_distal_width_score INT,
                mesial_mr_width FLOAT, mesial_mr_width_score INT,
                distal_mr_width FLOAT, distal_mr_width_score INT,
                
                total_score INT, fatal_error TEXT,
                islem_tarihi TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        print("✅ Veritabanı başarıyla başlatıldı (Veriler artık silinmeyecek).")
    except Error as e:
        print(f"Veritabanı hatası: {e}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

def save_result(student_data, original_filename, analysis_result):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    sql = '''INSERT INTO kavite_sonuclar (
                ogrenci_ad, ogrenci_soyad, ogrenci_no, img_90, drawn_img_90, stl_file,
                outline_form, outline_form_score, 
                mesial_isthmus_width, mesial_isthmus_width_score,
                distal_isthmus_width, distal_isthmus_width_score, 
                buccal_lingual_width, buccal_lingual_width_score,
                mesio_distal_width, mesio_distal_width_score, 
                mesial_mr_width, mesial_mr_width_score,
                distal_mr_width, distal_mr_width_score, 
                total_score, fatal_error
             ) VALUES (
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s
             )'''
             
    val = (
        student_data.get('name', ''), 
        student_data.get('lastname', ''), 
        student_data.get('no', ''), 
        original_filename, 
        analysis_result.get('drawn_90', ''), 
        analysis_result.get('stl_file', ''),
        
        analysis_result.get('outline_form', 0.0), analysis_result.get('outline_form_score', 0), 
        
        analysis_result.get('mesial_isthmus_width', 0.0), analysis_result.get('mesial_isthmus_width_score', 0),
        analysis_result.get('distal_isthmus_width', 0.0), analysis_result.get('distal_isthmus_width_score', 0), 
        
        analysis_result.get('buccal_lingual_width', 0.0), analysis_result.get('buccal_lingual_width_score', 0),
        analysis_result.get('mesio_distal_width', 0.0), analysis_result.get('mesio_distal_width_score', 0), 
        
        analysis_result.get('mesial_marginal_ridge_width', 0.0), analysis_result.get('mesial_marginal_ridge_width_score', 0),
        analysis_result.get('distal_marginal_ridge_width', 0.0), analysis_result.get('distal_marginal_ridge_width_score', 0), 
        
        analysis_result.get('total_score', 0), 
        analysis_result.get('fatal_error', '')
    )
    
    cursor.execute(sql, val)
    last_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return last_id

if __name__ == '__main__':
    init_db()