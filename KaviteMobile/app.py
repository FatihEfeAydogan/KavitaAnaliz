from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from werkzeug.utils import secure_filename
import os
from analysis import analyze_dental_images
import database  # Veritabanı fonksiyonları

app = Flask(__name__)
CORS(app)

# Dizin Yolu Düzeltmesi: Betiğin bulunduğu klasör ana dizin kabul edilecek
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
DRAWN_FOLDER  = os.path.join(UPLOAD_FOLDER, 'drawn')

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['DRAWN_FOLDER']  = DRAWN_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DRAWN_FOLDER,  exist_ok=True)

# Veritabanı tablolarını otomatik oluştur (sunucu başlarken)
database.init_db()

def _parse_box_coords(form):
    try:
        bx1, by1, bx2, by2 = form.get('box_x1'), form.get('box_y1'), form.get('box_x2'), form.get('box_y2')
        if bx1 and by1 and bx2 and by2:
            x1, x2 = sorted([float(bx1), float(bx2)])
            y1, y2 = sorted([float(by1), float(by2)])
            if (x2 - x1) > 10 and (y2 - y1) > 10:
                return [x1, y1, x2, y2]
    except (ValueError, TypeError):
        pass
    return None

# ──────────────────────────────────────────────────────────────────────
# 1. WEB ARAYÜZÜ ROTALARI (HTML / ŞABLON DÖNDÜRENLER)
# ──────────────────────────────────────────────────────────────────────

@app.route('/')
def index_web():
    """Web tarayıcıları için görsel arayüzü yükler"""
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process_web():
    """Web arayüzünden gönderilen formu işler ve sonuç sayfasını gösterir"""
    student_data = {
        'name': request.form.get('student_name', ''),
        'lastname': request.form.get('student_lastname', ''),
        'no': request.form.get('student_no', '')
    }

    img_90 = request.files.get('img_90')
    if not img_90:
        return render_template('index.html', error="Lütfen analiz için oklüzal (90°) fotoğrafı yükleyin.")

    box_coords = _parse_box_coords(request.form)
    if not box_coords:
        return render_template('index.html', error="Lütfen analiz edilecek hedef dişi fotoğraf üzerinde kare içine alın.")

    f_90    = secure_filename(img_90.filename)
    path_90 = os.path.join(app.config['UPLOAD_FOLDER'], f_90)
    img_90.save(path_90)

    analysis_result = analyze_dental_images(path_90, app.config['DRAWN_FOLDER'], f_90, box_coords=box_coords)

    if analysis_result.get("error"):
        return render_template('index.html', error=f"Analiz sırasında bir hata oluştu: {analysis_result['error']}")

    # Veritabanına kaydet
    database.save_result(student_data, f_90, analysis_result)

    final_result = {
        "ogrenci_ad":    student_data['name'],
        "ogrenci_soyad": student_data['lastname'],
        "ogrenci_no":    student_data['no'],
        "orijinal_foto": f_90,
        **analysis_result
    }
    
    return render_template('result.html', result=final_result)


# ──────────────────────────────────────────────────────────────────────
# 2. MOBİL UYGULAMA ROTALARI (SADECE JSON DÖNDÜRENLER - API)
# ──────────────────────────────────────────────────────────────────────

@app.route('/api/status', methods=['GET'])
def api_status():
    """Mobil uygulamanın sunucu bağlantısını doğrulaması için JSON endpoint"""
    return jsonify({"status": "Sunucu aktif ve mobil uygulama bağlantısına hazır."})

@app.route('/api/process', methods=['POST'])
def process_mobile():
    """Mobil uygulamadan gelen verileri işler ve saf JSON verisi döndürür"""
    student_data = {
        'name': request.form.get('student_name', ''),
        'lastname': request.form.get('student_lastname', ''),
        'no': request.form.get('student_no', '')
    }

    img_90 = request.files.get('img_90')
    if not img_90:
        return jsonify({"error": "Lütfen analiz için oklüzal (90°) fotoğrafı yükleyin."}), 400

    box_coords = _parse_box_coords(request.form)
    if not box_coords:
        return jsonify({"error": "Lütfen analiz edilecek hedef dişi fotoğraf üzerinde kare içine alın."}), 400

    f_90    = secure_filename(img_90.filename)
    path_90 = os.path.join(app.config['UPLOAD_FOLDER'], f_90)
    img_90.save(path_90)

    analysis_result = analyze_dental_images(path_90, app.config['DRAWN_FOLDER'], f_90, box_coords=box_coords)

    if analysis_result.get("error"):
        return jsonify({"error": f"Analiz sırasında bir hata oluştu: {analysis_result['error']}"}), 500

    # Veritabanına kaydet
    database.save_result(student_data, f_90, analysis_result)

    final_result = {
        "ogrenci_ad":    student_data['name'],
        "ogrenci_soyad": student_data['lastname'],
        "ogrenci_no":    student_data['no'],
        "orijinal_foto": f_90,
        **analysis_result
    }
    
    return jsonify({"metrics": final_result})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)