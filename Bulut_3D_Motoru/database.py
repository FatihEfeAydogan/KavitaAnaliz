import mysql.connector
import os
import json

# Veritabanı bağlantı ayarları
db_config = {
    "host": "localhost",
    "user": "root",
    "password": "root",  # Şifrenizi buraya yazdığınızdan emin olun
    "database": "model_dentistry_db"  # Veritabanı adı
}

def get_connection(use_db=True):
    """Veritabanı bağlantısı oluşturur."""
    config = db_config.copy()
    if not use_db:
        config.pop('database', None) # DB henüz yoksa database parametresi olmadan bağlan
    return mysql.connector.connect(**config)

def init_db():
    """init.sql dosyasını çalıştırarak veritabanı ve tabloları kurar."""
    try:
        conn = get_connection(use_db=False)
        cursor = conn.cursor()
        
        base_dir = os.path.dirname(os.path.abspath(__file__))
        sql_file_path = os.path.join(base_dir, 'init.sql')
        
        with open(sql_file_path, 'r', encoding='utf-8') as f:
            sql_script = f.read()
        
        commands = sql_script.split(';')
        for command in commands:
            if command.strip():
                cursor.execute(command)
                
        print("✅ Veritabanı ve tablolar başarıyla oluşturuldu/güncellendi!")
        
    except FileNotFoundError:
        print(f"❌ HATA: 'init.sql' dosyası bulunamadı! Yol: {sql_file_path}")
    except mysql.connector.Error as err:
        print(f"❌ Veritabanı Hatası: {err}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()


def save_analysis(student_name, stl_url, colored_ply_url, metrics):
    """Kavite analiz sonuçlarını veritabanına kaydeder."""
    conn = get_connection()
    cursor = conn.cursor()
    
    scores = metrics.get('scores', {})
    fatal_errors = json.dumps(metrics.get('fatal_errors', []))
    landmarks = json.dumps(metrics.get('landmarks', {}))

    sql = """
        INSERT INTO analyses (
            student_name, stl_url, colored_ply_url,
            
            outline_form, mesial_isthmus_width, distal_isthmus_width,
            buccal_lingual_width, buccal_lingual_width_rate,
            mesio_distal_width, mesio_distal_width_rate,
            mesial_marginal_ridge_width, distal_marginal_ridge_width,
            mesial_marginal_ridge_width_rate, distal_marginal_ridge_width_rate,
            cavity_depth, smoothness,
            
            outline_form_score, mesial_isthmus_width_score, distal_isthmus_width_score,
            buccal_lingual_width_score, buccal_lingual_width_rate_score,
            mesio_distal_width_score, mesio_distal_width_rate_score,
            mesial_marginal_ridge_width_score, distal_marginal_ridge_width_score,
            mesial_marginal_ridge_width_rate_score, distal_marginal_ridge_width_rate_score,
            cavity_depth_score, smoothness_score,
            
            total_score_130, final_score_100, fatal_errors, landmarks
        ) VALUES (
            %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s
        )
    """
    
    val = (
        student_name, stl_url, colored_ply_url,
        
        metrics.get('outline_form', 0), metrics.get('mesial_isthmus_width', 0), metrics.get('distal_isthmus_width', 0),
        metrics.get('buccal_lingual_width', 0), metrics.get('buccal_lingual_width_rate', 0),
        metrics.get('mesio_distal_width', 0), metrics.get('mesio_distal_width_rate', 0),
        metrics.get('mesial_marginal_ridge_width', 0), metrics.get('distal_marginal_ridge_width', 0),
        metrics.get('mesial_marginal_ridge_width_rate', 0), metrics.get('distal_marginal_ridge_width_rate', 0),
        metrics.get('cavity_depth', 0), metrics.get('smoothness', 0),
        
        scores.get('outline_form_score', 0), scores.get('mesial_isthmus_width_score', 0), scores.get('distal_isthmus_width_score', 0),
        scores.get('buccal_lingual_width_score', 0), scores.get('buccal_lingual_width_rate_score', 0),
        scores.get('mesio_distal_width_score', 0), scores.get('mesio_distal_width_rate_score', 0),
        scores.get('mesial_marginal_ridge_width_score', 0), scores.get('distal_marginal_ridge_width_score', 0),
        scores.get('mesial_marginal_ridge_width_rate_score', 0), scores.get('distal_marginal_ridge_width_rate_score', 0),
        scores.get('cavity_depth_score', 0), scores.get('smoothness_score', 0),
        
        metrics.get('total_score_130', 0), metrics.get('final_score_100', 0), fatal_errors, landmarks
    )
    
    cursor.execute(sql, val)
    conn.commit()
    analysis_id = cursor.lastrowid
    
    cursor.close()
    conn.close()
    return analysis_id

def get_all_analyses(limit=100):
    """Geçmiş tüm analizleri getirir."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True) # Dictionary formatında döndürür (JSON için ideal)
    cursor.execute("SELECT * FROM analyses ORDER BY created_at DESC LIMIT %s", (limit,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows

def get_analysis_by_id(analysis_id):
    """Spesifik bir analizi ID'ye göre getirir."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM analyses WHERE id = %s", (analysis_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if row and row.get('landmarks'):
        try:
            row['landmarks'] = json.loads(row['landmarks'])
        except:
            pass
    return row

def delete_analysis(analysis_id):
    """Analizi siler."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM analyses WHERE id = %s", (analysis_id,))
    conn.commit()
    success = cursor.rowcount > 0
    cursor.close()
    conn.close()
    return success

def get_stats():
    """Özet istatistikleri döndürür."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT COUNT(*) as total_analyses, AVG(final_score_100) as avg_score FROM analyses")
    stats = cursor.fetchone()
    cursor.close()
    conn.close()
    return stats

if __name__ == "__main__":
    init_db()