import atexit
import subprocess
import sys

from flask import Flask, render_template, request, jsonify
import os
import uuid
import requests

# Kendi analiz ve izolasyon modüllerimiz
from process_model import isolate_tooth
from database import save_analysis, get_all_analyses, get_analysis_by_id, delete_analysis, get_stats

app = Flask(__name__)

# --- KLASÖR YOLLARI ---
MODELS_DIR = os.path.join('static', 'models')
UPLOADS_DIR = os.path.join('static', 'uploads') # Manuel yüklemeler için yeni klasör

os.makedirs(MODELS_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)

# 3D Fotogrametri Motorunun Adresi
APP_3D_URL = "http://127.0.0.1:5001"

@app.route('/')
def index():
    return render_template('index.html')


# ==========================================
# MODÜL 1: FOTOGRAMETRİ (app_3d'ye Proxy)
# ==========================================
@app.route('/upload', methods=['POST'])
def upload_photos():
    """Gelen fotoğrafları doğrudan app_3d.py'ye iletir"""
    try:
        files = request.files.getlist('photos')
        files_to_send = [('photos', (f.filename, f.read(), f.content_type)) for f in files]

        res = requests.post(f"{APP_3D_URL}/upload", files=files_to_send)
        return jsonify(res.json()), res.status_code
    except requests.exceptions.ConnectionError:
        return jsonify({'error': 'app_3d.py motoru çalışmıyor (Port 5001). Fotogrametri yapılamaz.'}), 500
    except Exception as e:
        return jsonify({'error': f'Beklenmeyen hata: {str(e)}'}), 500


@app.route('/check_status/<task_uuid>')
def check_status(task_uuid):
    """Durum sorgularını doğrudan app_3d.py'ye iletir"""
    try:
        res = requests.get(f"{APP_3D_URL}/check_status/{task_uuid}")
        return jsonify(res.json()), res.status_code
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


# ==========================================
# MODÜL 2: AKILLI KAVİTE ANALİZİ (Bu Sunucuda Çalışır)
# ==========================================
@app.route('/upload_model', methods=['POST'])
def upload_model():
    if 'model_file' not in request.files:
        return "Model dosyası bulunamadı.", 400

    file = request.files['model_file']
    if file.filename == '':
        return "Dosya seçilmedi.", 400

    student_name = request.form.get('student_name', 'Anonim').strip()
    student_lastname = request.form.get('student_lastname', '').strip()
    student_no = request.form.get('student_no', '').strip()

    task_id = str(uuid.uuid4())
    task_dir = os.path.join(UPLOADS_DIR, task_id)
    os.makedirs(task_dir, exist_ok=True)

    file_ext = os.path.splitext(file.filename)[1].lower()
    
    try:
        if file_ext == '.obj':
            print(">>> [app] OBJ tespit edildi. İzolasyon işlemi başlatılıyor...")
            input_obj_path = os.path.join(task_dir, "uploaded_model.obj")
            file.save(input_obj_path)
            
            target_stl_path = os.path.join(task_dir, "isolated_tooth.stl")
            # Sadece masayı silip STL olarak kaydeder (process_model.py)
            isolate_tooth(input_obj_path, target_stl_path)
            
        elif file_ext == '.stl':
            print(">>> [app] STL tespit edildi. İzolasyon atlanıyor...")
            target_stl_path = os.path.join(task_dir, "isolated_tooth.stl")
            file.save(target_stl_path)
            
        else:
            return "Desteklenmeyen dosya formatı. Lütfen .stl veya .obj yükleyin.", 400

        # Sadece temiz STL'in web yolunu oluşturuyoruz, analiz YOK.
        stl_url = f"/static/uploads/{task_id}/isolated_tooth.stl"

        student_obj = {
            "studentName": student_name,
            "studentLastname": student_lastname,
            "studentNo": student_no,
            "stlFile": stl_url
        }

        return render_template(
            'result.html',
            student=student_obj,
            stl_url=stl_url
        )

    except Exception as e:
        print(">>> HATA OLUŞTU:", str(e))
        return f"İşlem sırasında sunucu hatası oluştu: {str(e)}", 500

# ==========================================
# MODÜL 3: VERİTABANI API'leri
# ==========================================
@app.route('/api/analyses', methods=['GET'])
def api_get_analyses():
    limit = request.args.get('limit', 100, type=int)
    rows = get_all_analyses(limit=limit)
    return jsonify(rows)

@app.route('/api/analyses/<int:analysis_id>', methods=['GET'])
def api_get_analysis(analysis_id):
    row = get_analysis_by_id(analysis_id)
    if row is None:
        return jsonify({'error': 'Analiz bulunamadı'}), 404
    return jsonify(row)

@app.route('/api/analyses/<int:analysis_id>', methods=['DELETE'])
def api_delete_analysis(analysis_id):
    success = delete_analysis(analysis_id)
    if success:
        return jsonify({'message': f'Analiz {analysis_id} silindi.'})
    return jsonify({'error': 'Analiz bulunamadı'}), 404

@app.route('/api/stats', methods=['GET'])
def api_stats():
    return jsonify(get_stats())

@app.route('/gecmis')
def gecmis():
    analyses = get_all_analyses(limit=200)
    return render_template('gecmis.html', analyses=analyses)

if __name__ == '__main__':
    print(">>> 3D Motoru (app_3d.py) arka planda başlatılıyor...")
    
    # app_3d.py'yi ayrı bir işlem (process) olarak başlat
    # sys.executable, o an çalışan Python'un yolunu otomatik bulur
    p3d = subprocess.Popen([sys.executable, "app_3d.py"])

    # Ana sunucu (app.py) kapatıldığında (CTRL+C) arkada asılı kalmasın diye app_3d.py'yi de kapat
    @atexit.register
    def kill_3d_engine():
        print(">>> 3D Motoru kapatılıyor...")
        p3d.terminate()

    # Ana Flask uygulamasını başlat
    # debug=True ise, Flask 'reloader' kullandığı için bu kod iki kere tetiklenebilir.
    # Bunu engellemek için use_reloader=False kullanmak daha sağlıklıdır.
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)