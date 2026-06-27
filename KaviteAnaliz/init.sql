-- 1. Veritabanını oluştur ve seç
CREATE DATABASE IF NOT EXISTS dentalanalysis;
USE dentalanalysis;

-- 2. Öğrenci Listesi Tablosu (Görsel ve app.py'ye göre)
CREATE TABLE IF NOT EXISTS student_list (
    studentID VARCHAR(255) NOT NULL,
    studentName VARCHAR(100),
    studentLastname VARCHAR(100),
    studentNo VARCHAR(50),
    stlFile VARCHAR(500),
    alignedFile VARCHAR(500),
    PRIMARY KEY (studentID)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 3. Analiz Puanları Tablosu (app.py'deki insert sorgusuna göre)
CREATE TABLE IF NOT EXISTS cavity_scores (
    studentID VARCHAR(255) NOT NULL,
    
    -- Ölçüm Değerleri (Float)
    outline_form FLOAT DEFAULT 0,
    mesial_isthmus_width FLOAT DEFAULT 0,
    distal_isthmus_width FLOAT DEFAULT 0,
    buccal_lingual_width FLOAT DEFAULT 0,
    buccal_lingual_width_rate FLOAT DEFAULT 0,
    mesio_distal_width FLOAT DEFAULT 0,
    mesio_distal_width_rate FLOAT DEFAULT 0,
    mesial_marginal_ridge_width FLOAT DEFAULT 0,
    mesial_marginal_ridge_width_rate FLOAT DEFAULT 0,
    distal_marginal_ridge_width FLOAT DEFAULT 0,
    distal_marginal_ridge_width_rate FLOAT DEFAULT 0,
    cavity_depth FLOAT DEFAULT 0,
    smoothness FLOAT DEFAULT 0,
    
    -- Puanlar (Genelde 0, 5, 10 tam sayılarıdır ama Float da tutulabilir)
    outline_form_score INT DEFAULT 0,
    mesial_isthmus_width_score INT DEFAULT 0,
    distal_isthmus_width_score INT DEFAULT 0,
    buccal_lingual_width_score INT DEFAULT 0,
    buccal_lingual_width_rate_score INT DEFAULT 0,
    mesio_distal_width_score INT DEFAULT 0,
    mesio_distal_width_rate_score INT DEFAULT 0,
    mesial_marginal_ridge_width_score INT DEFAULT 0,
    mesial_marginal_ridge_width_rate_score INT DEFAULT 0,
    distal_marginal_ridge_width_score INT DEFAULT 0,
    distal_marginal_ridge_width_rate_score INT DEFAULT 0,
    cavity_depth_score INT DEFAULT 0,
    smoothness_score INT DEFAULT 0,
    
    -- Toplam Puan
    score FLOAT DEFAULT 0,

    -- Anahtar Bağlantıları
    PRIMARY KEY (studentID),
    CONSTRAINT fk_student 
        FOREIGN KEY (studentID) 
        REFERENCES student_list (studentID) 
        ON DELETE CASCADE 
        ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;