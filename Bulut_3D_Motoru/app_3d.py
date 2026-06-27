from flask import Flask, request, jsonify
import os
import requests
import json
import cv2
import numpy as np
import open3d as o3d
import zipfile
from scipy.spatial import Delaunay  # YENİ EKLENDİ: 2.5D Delaunay için

app = Flask(__name__)

MODELS_DIR = os.path.join('static', 'models')
os.makedirs(MODELS_DIR, exist_ok=True)
NODEODM_API_URL = "http://127.0.0.1:3000"

@app.route('/upload', methods=['POST'])
def upload_photos():
    files = request.files.getlist('photos')
    if not files or len(files) == 0:
        return jsonify({'error': 'Hiç fotoğraf seçilmedi!'}), 400

    print(f">>> [app_3d] {len(files)} fotoğraf alındı. NodeODM'e gönderiliyor...")

    try:
        upload_files = []
        gcp_lines = ["WGS84 UTM 35N"] 
        images_with_gcp = 0

        aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_250)
        parameters = cv2.aruco.DetectorParameters()

        for idx, f in enumerate(files):
            img_bytes = f.read()
            f.seek(0) 
            
            ext = os.path.splitext(f.filename)[1]
            if not ext:
                ext = ".jpg"
            safe_filename = f"img_{idx}{ext}"

            upload_files.append(('images', (safe_filename, img_bytes, f.content_type)))

            nparr = np.frombuffer(img_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if img is not None:
                corners, ids, rejected = cv2.aruco.detectMarkers(img, aruco_dict, parameters=parameters)
                if ids is not None:
                    for i in range(len(ids)):
                        if ids[i][0] == 0: 
                            c = corners[i][0]
                            tl, tr, br, bl = c[0], c[1], c[2], c[3]

                            px_tl_x, px_tl_y = int(round(tl[0])), int(round(tl[1]))
                            px_tr_x, px_tr_y = int(round(tr[0])), int(round(tr[1]))
                            px_br_x, px_br_y = int(round(br[0])), int(round(br[1]))
                            px_bl_x, px_bl_y = int(round(bl[0])), int(round(bl[1]))

                            gcp_lines.append(f"0.000 10.000 0.000 {px_tl_x} {px_tl_y} {safe_filename}")
                            gcp_lines.append(f"10.000 10.000 0.000 {px_tr_x} {px_tr_y} {safe_filename}")
                            gcp_lines.append(f"10.000 0.000 0.000 {px_br_x} {px_br_y} {safe_filename}")
                            gcp_lines.append(f"0.000 0.000 0.000 {px_bl_x} {px_bl_y} {safe_filename}")
                            
                            images_with_gcp += 1
                            break

        if images_with_gcp > 0:
            gcp_content = "\n".join(gcp_lines) + "\n"
            upload_files.append(('images', ('gcp_list.txt', gcp_content.encode('utf-8'), 'text/plain')))
            print(f">>> [app_3d] BAŞARILI: {images_with_gcp} fotoğrafta referans bulundu.")

        options = {
            "pc-quality": "high",          
            "feature-quality": "high",     
            "use-3dmesh": False, 
            "dsm": False,
            "dtm": False,
            "orthophoto-resolution": 0
        }
        data = {'options': json.dumps(options)}

        res = requests.post(f"{NODEODM_API_URL}/task/new", files=upload_files, data=data)
        
        if res.status_code != 200:
            return jsonify({'error': f'API Hatası: {res.text}'}), 500
            
        res_data = res.json()
        
        if 'error' in res_data:
            return jsonify({'error': f"NodeODM Hatası: {res_data['error']}"}), 400
            
        task_uuid = res_data.get('uuid')

        return jsonify({'task_id': task_uuid, 'message': 'Nokta bulutu üretimi başladı!'})

    except Exception as e:
        print(">>> [app_3d] KRİTİK HATA:", str(e))
        return jsonify({'error': str(e)}), 500


@app.route('/check_status/<task_uuid>')
def check_status(task_uuid):
    try:
        res = requests.get(f"{NODEODM_API_URL}/task/{task_uuid}/info")
        if res.status_code != 200:
             return jsonify({'status': 'error', 'error': 'Durum sorgusu başarısız.'})
             
        task_info = res.json()
        status_code = task_info.get('status', {}).get('code')
        progress = task_info.get('progress', 0)

        if status_code in [10, 20]:
            return jsonify({'status': 'processing', 'progress': progress})
        elif status_code == 30:
            return jsonify({'status': 'error', 'error': 'Fotogrametri motoru hata verdi.'})
        elif status_code == 40:
            
            # --- ÇÖZÜM 1: EŞZAMANLI İSTEK ÇAKIŞMASINI (RACE CONDITION) ÖNLEME ---
            extract_dir = os.path.join(MODELS_DIR, task_uuid)
            
            # Dosya adını önceden kalan uyumluluk için "poisson_tooth_model.obj" bıraktım.
            # Ancak algoritma artık Delaunay çalışıyor.
            final_obj_path = os.path.join(extract_dir, "poisson_tooth_model.obj")
            lock_file = os.path.join(MODELS_DIR, f"{task_uuid}.lock")

            # 1. İşlem zaten bitmiş ve dosya oluşmuşsa direkt başarılı dön
            if os.path.exists(final_obj_path):
                relative_path = final_obj_path.replace("\\", "/").split('static/')[-1]
                return jsonify({'status': 'completed', 'model_url': f'/static/{relative_path}'})

            # 2. İşlem şu an arka planda yapılıyorsa (kilit dosyası varsa), arayüze 'işleniyor' de
            if os.path.exists(lock_file):
                return jsonify({'status': 'processing', 'progress': 99})

            # 3. İlk gelen istek kilit dosyasını oluşturur ve işlemi başlatır
            with open(lock_file, 'w') as f:
                f.write('isleniyor')

            try:
                model_url = f"{NODEODM_API_URL}/task/{task_uuid}/download/all.zip"
                model_res = requests.get(model_url, stream=True)
                
                if model_res.status_code == 200:
                    local_zip_path = os.path.join(MODELS_DIR, f"{task_uuid}.zip")
                    with open(local_zip_path, 'wb') as f:
                        for chunk in model_res.iter_content(chunk_size=8192):
                            f.write(chunk)
                    
                    os.makedirs(extract_dir, exist_ok=True)
                    with zipfile.ZipFile(local_zip_path, 'r') as zip_ref:
                        zip_ref.extractall(extract_dir)

                    # --- ÇÖZÜM 2: GEREKSİZ ZIP DOSYASINI SİLME ---
                    if os.path.exists(local_zip_path):
                        os.remove(local_zip_path)
                        print(f">>> [app_3d] Çıkarma sonrası gereksiz ZIP silindi: {task_uuid}.zip")
                    
                    ply_file_path = None
                    for root, dirs, files in os.walk(extract_dir):
                        for file in files:
                            if file.endswith('.ply'):
                                ply_file_path = os.path.join(root, file)
                                break
                        if ply_file_path:
                            break
                    
                    if ply_file_path:
                        print(">>> [app_3d] Nokta bulutu indirildi. 2.5D Delaunay Algoritması başlatılıyor...")
                        pcd = o3d.io.read_point_cloud(ply_file_path)
                        
                        # Noktaları numpy dizisine çevir
                        points = np.asarray(pcd.points)

                        # 1. Adım: 2.5D Projeksiyon
                        # Noktaları X ve Z (yatay) düzlemine yansıtarak 2D kabul ediyoruz.
                        points_2d = points[:, [0, 2]]

                        # 2. Adım: 2D Delaunay Üçgenlemesi
                        print(">>> [app_3d] Yüzey örülüyor (2.5D Delaunay)...")
                        tri = Delaunay(points_2d)

                        # 3. Adım: Yeni Mesh'i Oluşturma
                        mesh = o3d.geometry.TriangleMesh()
                        
                        # Noktaların orijinal 3D (X, Y, Z) koordinatlarını aynen koruyoruz
                        mesh.vertices = o3d.utility.Vector3dVector(points) 
                        
                        # Delaunay'in bulduğu üçgen bağlantılarını modele atıyoruz
                        mesh.triangles = o3d.utility.Vector3iVector(tri.simplices)

                        # Işıklandırma ve analiz için normalleri hesapla
                        mesh.compute_vertex_normals()

                        # Delaunay bazen sınır noktalarında çok uzun ve keskin üçgenler üretebilir.
                        # Bunu hafifletmek ve diş yüzeyini doğal tutmak için 5 iterasyonluk hafif bir düzeltme ekledim.
                        mesh = mesh.filter_smooth_taubin(number_of_iterations=5)
                        mesh.compute_vertex_normals()

                        o3d.io.write_triangle_mesh(final_obj_path, mesh)
                        print(f">>> [app_3d] 2.5D Delaunay işlemi başarılı! Model kaydedildi: {final_obj_path}")

                        relative_path = final_obj_path.replace("\\", "/").split('static/')[-1]
                        return jsonify({'status': 'completed', 'model_url': f'/static/{relative_path}'})

                    else:
                        return jsonify({'status': 'error', 'error': 'ZIP içinde Nokta Bulutu (.ply) dosyası bulunamadı.'})
                else:
                    return jsonify({'status': 'error', 'error': 'Model çekilemedi.'})
            finally:
                # İşlem bittiğinde (başarılı veya hata olsa bile) kilidi kaldır
                if os.path.exists(lock_file):
                    os.remove(lock_file)
        else:
            return jsonify({'status': 'processing', 'progress': progress})

    except Exception as e:
        # Hata durumunda da kilidi temizle
        lock_file = os.path.join(MODELS_DIR, f"{task_uuid}.lock")
        if 'lock_file' in locals() and os.path.exists(lock_file):
            os.remove(lock_file)
        return jsonify({'status': 'error', 'error': str(e)})


if __name__ == '__main__':
    # NodeODM Motoru 5001 portunda çalışacak
    app.run(host='0.0.0.0', port=5001, debug=False)