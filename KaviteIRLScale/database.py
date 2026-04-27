import mysql.connector
from mysql.connector import Error

DB_CONFIG = {'host': 'localhost', 'user': 'root', 'password': 'root'} 

def get_db_connection():
    config = DB_CONFIG.copy()
    config['database'] = 'kavite_db'
    return mysql.connector.connect(**config)

def init_db():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("CREATE DATABASE IF NOT EXISTS kavite_db")
        cursor.execute("USE kavite_db")
        
        # Tabloyu silip 3 görsel destekli yeni tabloyu kuruyoruz
        cursor.execute("DROP TABLE IF EXISTS kavite_sonuclar")
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS kavite_sonuclar (
                id INT AUTO_INCREMENT PRIMARY KEY,
                ogrenci_ad VARCHAR(100),
                ogrenci_soyad VARCHAR(100),
                ogrenci_no VARCHAR(50),
                img_90 VARCHAR(255),
                drawn_img_90 VARCHAR(255),
                drawn_img_45_1 VARCHAR(255),
                drawn_img_45_2 VARCHAR(255),
                outline_form FLOAT, outline_form_score INT,
                mesial_isthmus_width FLOAT, mesial_isthmus_width_score INT,
                distal_isthmus_width FLOAT, distal_isthmus_width_score INT,
                buccal_lingual_width FLOAT, buccal_lingual_width_score INT,
                buccal_lingual_width_rate FLOAT, buccal_lingual_width_rate_score INT,
                mesio_distal_width FLOAT, mesio_distal_width_score INT,
                mesio_distal_width_rate FLOAT, mesio_distal_width_rate_score INT,
                mesial_mr_width FLOAT, mesial_mr_width_score INT,
                mesial_mr_width_rate FLOAT, mesial_mr_width_rate_score INT,
                distal_mr_width FLOAT, distal_mr_width_score INT,
                distal_mr_width_rate FLOAT, distal_mr_width_rate_score INT,
                cavity_depth FLOAT, cavity_depth_score INT,
                smoothness FLOAT, smoothness_score INT,
                total_score INT, fatal_error TEXT,
                islem_tarihi TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        print("✅ Veritabanı başarıyla güncellendi (3 Görsel Desteği Eklendi).")
    except Error as e:
        print(f"Veritabanı hatası: {e}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

def save_result(student, filenames, metrics):
    conn = get_db_connection()
    cursor = conn.cursor()
    sql = '''INSERT INTO kavite_sonuclar (
                ogrenci_ad, ogrenci_soyad, ogrenci_no, img_90, drawn_img_90, drawn_img_45_1, drawn_img_45_2,
                outline_form, outline_form_score, mesial_isthmus_width, mesial_isthmus_width_score,
                distal_isthmus_width, distal_isthmus_width_score, buccal_lingual_width, buccal_lingual_width_score,
                buccal_lingual_width_rate, buccal_lingual_width_rate_score, mesio_distal_width, mesio_distal_width_score,
                mesio_distal_width_rate, mesio_distal_width_rate_score, mesial_mr_width, mesial_mr_width_score,
                mesial_mr_width_rate, mesial_mr_width_rate_score, distal_mr_width, distal_mr_width_score,
                distal_mr_width_rate, distal_mr_width_rate_score, cavity_depth, cavity_depth_score,
                smoothness, smoothness_score, total_score, fatal_error
             ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)'''
    val = (
        student['name'], student['lastname'], student['no'], filenames['img_90'], metrics['drawn_90'], metrics['drawn_45_1'], metrics['drawn_45_2'],
        metrics['outline_form'], metrics['outline_form_score'], metrics['mesial_isthmus_width'], metrics['mesial_isthmus_width_score'],
        metrics['distal_isthmus_width'], metrics['distal_isthmus_width_score'], metrics['buccal_lingual_width'], metrics['buccal_lingual_width_score'],
        metrics['buccal_lingual_width_rate'], metrics['buccal_lingual_width_rate_score'], metrics['mesio_distal_width'], metrics['mesio_distal_width_score'],
        metrics['mesio_distal_width_rate'], metrics['mesio_distal_width_rate_score'], metrics['mesial_marginal_ridge_width'], metrics['mesial_marginal_ridge_width_score'],
        metrics['mesial_marginal_ridge_width_rate'], metrics['mesial_marginal_ridge_width_rate_score'], metrics['distal_marginal_ridge_width'], metrics['distal_marginal_ridge_width_score'],
        metrics['distal_marginal_ridge_width_rate'], metrics['distal_marginal_ridge_width_rate_score'], metrics['cavity_depth'], metrics['cavity_depth_score'],
        metrics['smoothness'], metrics['smoothness_score'], metrics['total_score'], metrics.get('fatal_error', '')
    )
    cursor.execute(sql, val)
    last_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return last_id

def get_all_students():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, ogrenci_ad, ogrenci_soyad, ogrenci_no, img_90 FROM kavite_sonuclar ORDER BY islem_tarihi DESC")
    students = cursor.fetchall()
    conn.close()
    return students

def get_result_by_id(result_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM kavite_sonuclar WHERE id = %s", (result_id,))
    result = cursor.fetchone()
    conn.close()
    return result

def update_student(student_id, data):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE kavite_sonuclar SET ogrenci_ad=%s, ogrenci_soyad=%s, ogrenci_no=%s WHERE id=%s", 
                   (data['ad'], data['soyad'], data['numara'], student_id))
    conn.commit()
    conn.close()

def delete_student(student_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM kavite_sonuclar WHERE id=%s", (student_id,))
    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()