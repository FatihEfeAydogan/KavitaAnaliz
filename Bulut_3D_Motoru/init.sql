-- 1. Veritabanını oluştur ve seç
CREATE DATABASE IF NOT EXISTS model_dentistry_db;
USE model_dentistry_db;

-- 2. Eski tablolar varsa çakışmayı önlemek için sil (Opsiyonel ama temizlik için iyi)
DROP TABLE IF EXISTS cavity_scores;
DROP TABLE IF EXISTS student_list;
DROP TABLE IF EXISTS analyses;

-- 3. Tekil ve Kapsamlı Analiz Tablosu
CREATE TABLE analyses (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_name VARCHAR(100) DEFAULT 'Anonim',
    stl_url VARCHAR(500),
    colored_ply_url VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Ölçüm Değerleri (Float)
    outline_form FLOAT DEFAULT 0,
    mesial_isthmus_width FLOAT DEFAULT 0,
    distal_isthmus_width FLOAT DEFAULT 0,
    buccal_lingual_width FLOAT DEFAULT 0,
    buccal_lingual_width_rate FLOAT DEFAULT 0,
    mesio_distal_width FLOAT DEFAULT 0,
    mesio_distal_width_rate FLOAT DEFAULT 0,
    mesial_marginal_ridge_width FLOAT DEFAULT 0,
    distal_marginal_ridge_width FLOAT DEFAULT 0,
    mesial_marginal_ridge_width_rate FLOAT DEFAULT 0,
    distal_marginal_ridge_width_rate FLOAT DEFAULT 0,
    cavity_depth FLOAT DEFAULT 0,
    smoothness FLOAT DEFAULT 0,

    -- Puanlar (Int)
    outline_form_score INT DEFAULT 0,
    mesial_isthmus_width_score INT DEFAULT 0,
    distal_isthmus_width_score INT DEFAULT 0,
    buccal_lingual_width_score INT DEFAULT 0,
    buccal_lingual_width_rate_score INT DEFAULT 0,
    mesio_distal_width_score INT DEFAULT 0,
    mesio_distal_width_rate_score INT DEFAULT 0,
    mesial_marginal_ridge_width_score INT DEFAULT 0,
    distal_marginal_ridge_width_score INT DEFAULT 0,
    mesial_marginal_ridge_width_rate_score INT DEFAULT 0,
    distal_marginal_ridge_width_rate_score INT DEFAULT 0,
    cavity_depth_score INT DEFAULT 0,
    smoothness_score INT DEFAULT 0,

    -- Toplam ve Sonuç
    total_score_130 INT DEFAULT 0,
    final_score_100 FLOAT DEFAULT 0,
    
    -- JSON formatında ekstra veriler (Landmarklar ve Hatalar)
    fatal_errors TEXT,
    landmarks JSON
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;