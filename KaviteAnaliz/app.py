from flask import Flask, jsonify, render_template, request, redirect, url_for
import mysql.connector
import os
from werkzeug.utils import secure_filename
import json 
import logging

from analysis import analyze_preprocessed_cavity
from cut_model import crop_bottom_of_mesh
from rotate import align_single_file

app = Flask(__name__)

# --- AYARLAR ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Artık dosya kopyalanmayacağı için doğrudan tek klasör kullanıyoruz
ANALYZED_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads', 'analyzed')

app.config['ANALYZED_FOLDER'] = ANALYZED_FOLDER
os.makedirs(ANALYZED_FOLDER, exist_ok=True)

logging.basicConfig(level=logging.INFO)

# ---------------------- MySQL BAĞLANTISI ----------------------
def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="root",  
        database="dentalanalysis"
    )

def get_default_metrics():
    return {
        "outline_form": 0.0, "mesial_isthmus_width": 0.0, "distal_isthmus_width": 0.0,
        "buccal_lingual_width": 0.0, "buccal_lingual_width_rate": 0.0,
        "mesio_distal_width": 0.0, "mesio_distal_width_rate": 0.0,
        "mesial_marginal_ridge_width": 0.0, "mesial_marginal_ridge_width_rate": 0.0,
        "distal_marginal_ridge_width": 0.0, "distal_marginal_ridge_width_rate": 0.0,
        "cavity_depth": 0.0, "smoothness": 0.0,
        "scores": {}, "comparison": {}, "landmarks": {}, 
        "total_score_130": 0.0, "final_score_100": 0.0
    }

def save_scores_to_db(student_id, result):
    db = get_db_connection()
    cursor = db.cursor()
    
    scores_dict = result.get("scores", {})
    final_score = result.get("final_score_100", 0)

    sql_query = """
        INSERT INTO cavity_scores (
            studentID, outline_form, mesial_isthmus_width, distal_isthmus_width, buccal_lingual_width, 
            buccal_lingual_width_rate, mesio_distal_width, mesio_distal_width_rate, mesial_marginal_ridge_width, 
            mesial_marginal_ridge_width_rate, distal_marginal_ridge_width, distal_marginal_ridge_width_rate, 
            cavity_depth, smoothness, outline_form_score, mesial_isthmus_width_score, distal_isthmus_width_score, 
            buccal_lingual_width_score, buccal_lingual_width_rate_score, mesio_distal_width_score, 
            mesio_distal_width_rate_score, mesial_marginal_ridge_width_score, mesial_marginal_ridge_width_rate_score, 
            distal_marginal_ridge_width_score, distal_marginal_ridge_width_rate_score, cavity_depth_score, 
            smoothness_score, score
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE 
            outline_form=%s, mesial_isthmus_width=%s, distal_isthmus_width=%s, buccal_lingual_width=%s, 
            buccal_lingual_width_rate=%s, mesio_distal_width=%s, mesio_distal_width_rate=%s, 
            mesial_marginal_ridge_width=%s, mesial_marginal_ridge_width_rate=%s, distal_marginal_ridge_width=%s, 
            distal_marginal_ridge_width_rate=%s, cavity_depth=%s, smoothness=%s, outline_form_score=%s, 
            mesial_isthmus_width_score=%s, distal_isthmus_width_score=%s, buccal_lingual_width_score=%s, 
            buccal_lingual_width_rate_score=%s, mesio_distal_width_score=%s, mesio_distal_width_rate_score=%s, 
            mesial_marginal_ridge_width_score=%s, mesial_marginal_ridge_width_rate_score=%s, 
            distal_marginal_ridge_width_score=%s, distal_marginal_ridge_width_rate_score=%s, 
            cavity_depth_score=%s, smoothness_score=%s, score=%s
    """
    
    params_vals = (
        result.get("outline_form", 0), result.get("mesial_isthmus_width", 0), 
        result.get("distal_isthmus_width", 0), result.get("buccal_lingual_width", 0), 
        result.get("buccal_lingual_width_rate", 0), result.get("mesio_distal_width", 0), 
        result.get("mesio_distal_width_rate", 0), result.get("mesial_marginal_ridge_width", 0), 
        result.get("mesial_marginal_ridge_width_rate", 0), result.get("distal_marginal_ridge_width", 0), 
        result.get("distal_marginal_ridge_width_rate", 0), result.get("cavity_depth", 0), 
        result.get("smoothness", 0), scores_dict.get("outline_form_score", 0), 
        scores_dict.get("mesial_isthmus_width_score", 0), scores_dict.get("distal_isthmus_width_score", 0), 
        scores_dict.get("buccal_lingual_width_score", 0), scores_dict.get("buccal_lingual_width_rate_score", 0), 
        scores_dict.get("mesio_distal_width_score", 0), scores_dict.get("mesio_distal_width_rate_score", 0), 
        scores_dict.get("mesial_marginal_ridge_width_score", 0), 
        scores_dict.get("mesial_marginal_ridge_width_rate_score", 0), 
        scores_dict.get("distal_marginal_ridge_width_score", 0), 
        scores_dict.get("distal_marginal_ridge_width_rate_score", 0), 
        scores_dict.get("cavity_depth_score", 0), scores_dict.get("smoothness_score", 0), 
        final_score
    )
    
    cursor.execute(sql_query, (student_id,) + params_vals + params_vals)
    db.commit()
    cursor.close()
    db.close()

# ---------------------- ROTALAR ----------------------

@app.route('/')
def index():
    return render_template('index.html')

@app.route("/students")
def list_students():
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM student_list")
    students = cursor.fetchall()
    cursor.close()
    db.close()
    return render_template("students.html", students=students)

@app.route('/init_upload', methods=['POST'])
def init_upload():
    try:
        s_name = request.form.get("student_name", "").strip()
        s_last = request.form.get("student_lastname", "").strip()
        s_no = request.form.get("student_no", "").strip()
        file = request.files.get("stl_file")
        
        if not file or file.filename == "":
            return jsonify({"success": False, "message": "Dosya seçilmedi."})
            
        filename = secure_filename(file.filename)
        
        # --- YENİ: Kopyalama kaldırıldı, doğrudan çalışılacak klasöre kaydediliyor ---
        filepath = os.path.join(app.config['ANALYZED_FOLDER'], filename)
        file.save(filepath)
        
        student_id = f"{s_no}_{s_name}_{s_last}_{filename}"
        
        db = get_db_connection()
        cursor = db.cursor()
        
        # --- YENİ: İki dosya yolu da aynı dosyayı (analyzed içindeki) işaret eder ---
        db_path = os.path.join('uploads', 'analyzed', filename).replace("\\", "/")
        
        cursor.execute("""
            INSERT INTO student_list (studentID, studentName, studentLastname, studentNo, stlFile, alignedFile)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE 
                studentName=%s, studentLastname=%s, studentNo=%s, stlFile=%s, alignedFile=%s
        """, (student_id, s_name, s_last, s_no, db_path, db_path,
              s_name, s_last, s_no, db_path, db_path))
        db.commit()
        cursor.close()
        db.close()
        
        return jsonify({"success": True, "student_id": student_id, "filename": filename})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route('/process_step', methods=['POST'])
def process_step():
    data = request.json
    st_id = data.get("student_id")
    fname = data.get("filename")
    p_type = data.get("type")
    
    root, ext = os.path.splitext(fname)
    current_path = os.path.join(app.config['ANALYZED_FOLDER'], fname)
    new_filename = fname
    
    try:
        if p_type == "rotate":
            logging.info(f"Hizalama tetiklendi: {fname}")
            new_filename = f"{root}_aligned{ext}"
            new_path = os.path.join(app.config['ANALYZED_FOLDER'], new_filename)
            align_single_file(current_path, new_path)
            
        elif p_type == "crop":
            logging.info(f"Kesme tetiklendi: {fname}")
            new_filename = f"{root}_cropped{ext}"
            new_path = os.path.join(app.config['ANALYZED_FOLDER'], new_filename)
            crop_bottom_of_mesh(current_path, new_path, cut_ratio=0.6, axis=1)
            
        elif p_type == "analyze":
            logging.info(f"Analiz tetiklendi: {fname}")
            result = analyze_preprocessed_cavity(current_path)
            if "error" in result:
                return jsonify({"success": False, "message": result["error"]})
                
            save_scores_to_db(st_id, result)
            
            landmarks_path = os.path.join(app.config['ANALYZED_FOLDER'], f"{root}_landmarks.json")
            with open(landmarks_path, 'w', encoding='utf-8') as f:
                json.dump(result.get("landmarks", {}), f)
                
            return jsonify({"success": True, "new_filename": fname})

        db = get_db_connection()
        cursor = db.cursor()
        db_aligned_path = os.path.join('uploads', 'analyzed', new_filename).replace("\\", "/")
        cursor.execute("UPDATE student_list SET alignedFile=%s WHERE studentID=%s", (db_aligned_path, st_id))
        db.commit()
        cursor.close()
        db.close()
        
        return jsonify({"success": True, "new_filename": new_filename})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/result/<student_id>")
def result_page(student_id):
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    try:
        cursor.execute("SELECT * FROM student_list WHERE studentID = %s", (student_id,))
        student = cursor.fetchone()
        cursor.execute("SELECT * FROM cavity_scores WHERE studentID = %s", (student_id,))
        db_data = cursor.fetchone()

        if not student: 
            return "Kayıt bulunamadı."

        aligned_db_path = student.get('alignedFile')
        if aligned_db_path:
            final_filename = os.path.basename(aligned_db_path)
        else:
            final_filename = os.path.basename(student['stlFile'])
        
        root, _ = os.path.splitext(final_filename)
        colored_mesh_path = os.path.join('uploads', 'analyzed', final_filename.replace('.stl', '_colored.ply')).replace("\\", "/")
        cavity_mesh_path = os.path.join('uploads', 'analyzed', final_filename.replace('.stl', '_cavity.ply')).replace("\\", "/")

        result = get_default_metrics()
        
        if db_data:
            result.update(db_data)
            scores_dict = {k: v for k, v in db_data.items() if k.endswith('_score')}
        else:
            scores_dict = {}

        landmarks_path = os.path.join(app.config['ANALYZED_FOLDER'], f"{root}_landmarks.json")
        if os.path.exists(landmarks_path):
            with open(landmarks_path, 'r', encoding='utf-8') as f:
                result["landmarks"] = json.load(f)

        visual_stl_path = os.path.join('uploads', 'analyzed', final_filename).replace("\\", "/")

        return render_template(
            "result.html", 
            student=student, 
            scores=db_data if db_data else get_default_metrics(), 
            result_metrics=result, 
            scores_dict=scores_dict, 
            final_score=db_data.get('score', 0) if db_data else 0, 
            student_stl_path=visual_stl_path,
            colored_mesh_path=colored_mesh_path,
            cavity_mesh_path=cavity_mesh_path
        )
    except Exception as e:
        return f"Hata: {str(e)}"
    finally:
        cursor.close()
        db.close()

@app.route('/update_student/<student_id>', methods=['POST'])
def update_student(student_id):
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    try:
        data = request.get_json()
        query = "UPDATE student_list SET studentName = %s, studentLastname = %s, studentNo = %s WHERE studentID = %s"
        cursor.execute(query, (data.get('ad'), data.get('soyad'), data.get('numara'), student_id))
        db.commit()
        return jsonify({'success': True, 'message': 'Güncelleme başarılı'})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)})
    finally:
        cursor.close()
        db.close()

@app.route('/delete_student/<student_id>', methods=['POST'])
def delete_student(student_id):
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("SELECT stlFile FROM student_list WHERE studentID = %s", (student_id,))
        record = cursor.fetchone()
        
        cursor.execute("DELETE FROM cavity_scores WHERE studentID = %s", (student_id,))
        cursor.execute("DELETE FROM student_list WHERE studentID = %s", (student_id,))
        db.commit()
        
        if record and record['stlFile']:
            original_full_path = os.path.join('static', record['stlFile'])
            if os.path.exists(original_full_path):
                try: os.remove(original_full_path)
                except: pass
            
            filename = os.path.basename(original_full_path)
            
            for suffix in ['', '_colored.ply', '_cavity.ply', '_cropped.stl', '_aligned.stl', '_landmarks.json']:
                temp_path = os.path.join(app.config['ANALYZED_FOLDER'], filename.replace('.stl', suffix))
                if os.path.exists(temp_path):
                    try: os.remove(temp_path)
                    except: pass

        return jsonify({'success': True, 'message': 'Silme başarılı'})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)})
    finally:
        cursor.close()
        db.close()

if __name__ == "__main__":
    app.run(debug=True)