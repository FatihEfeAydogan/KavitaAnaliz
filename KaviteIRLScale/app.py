from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
import os
from analysis import analyze_dental_images

app = Flask(__name__)
CORS(app) 

CURRENT_DIR = os.path.abspath(os.getcwd())

if "KaviteIRLScale" not in CURRENT_DIR:
    BASE_DIR = os.path.join(CURRENT_DIR, 'KaviteIRLScale')
else:
    BASE_DIR = CURRENT_DIR

UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
DRAWN_FOLDER = os.path.join(UPLOAD_FOLDER, 'drawn')

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['DRAWN_FOLDER'] = DRAWN_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DRAWN_FOLDER, exist_ok=True)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process_web():
    student_name = request.form.get('student_name', '')
    student_lastname = request.form.get('student_lastname', '')
    student_no = request.form.get('student_no', '')

    img_90 = request.files.get('img_90')

    if not img_90:
        return "Lütfen analiz için oklüzal (90°) fotoğrafı yükleyin.", 400

    f_90 = secure_filename(img_90.filename)
    path_90 = os.path.join(app.config['UPLOAD_FOLDER'], f_90)
    img_90.save(path_90)

    # Sadece tek fotoğraf ile analiz
    analysis_result = analyze_dental_images(path_90, app.config['DRAWN_FOLDER'], f_90)

    if analysis_result.get("error"):
        return f"Analiz sırasında bir hata oluştu: {analysis_result['error']}", 500

    final_result = {
        "ogrenci_ad": student_name,
        "ogrenci_soyad": student_lastname,
        "ogrenci_no": student_no,
        "orijinal_foto": f_90,
        **analysis_result
    }
    return render_template('result.html', result=final_result)

@app.route('/api/process', methods=['POST'])
def process_api():
    try:
        student_name = request.form.get('student_name', '')
        student_lastname = request.form.get('student_lastname', '')
        student_no = request.form.get('student_no', '')

        img_90 = request.files.get('img_90')
        
        if not img_90:
            return jsonify({"error": "Oklüzal fotoğraf eksik."}), 400

        f_90 = secure_filename(img_90.filename)
        path_90 = os.path.join(app.config['UPLOAD_FOLDER'], f_90)
        img_90.save(path_90)

        analysis_result = analyze_dental_images(path_90, app.config['DRAWN_FOLDER'], f_90)

        if analysis_result.get("error"):
            return jsonify({"error": analysis_result['error']}), 500

        final_result = {
            "success": True,
            "metrics": analysis_result
        }
        return jsonify(final_result), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)