import React, { useState, useRef, useEffect } from 'react';
import { StyleSheet, Text, View, TextInput, TouchableOpacity, ScrollView, Alert, ActivityIndicator, Image, Dimensions, PanResponder } from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import axios from 'axios';

const SERVER_URL = "http://10.210.142.53:5000"; // Python sunucunuzun güncel IP adresi
const BACKEND_URL = `${SERVER_URL}/api/process`;   // Flask ile uyumlu endpoint
const WINDOW_WIDTH = Dimensions.get('window').width;

export default function App() {
  const [name, setName] = useState('');
  const [lastname, setLastname] = useState('');
  const [studentNo, setStudentNo] = useState('');
  const [img90, setImg90] = useState(null);
  const [loading, setLoading] = useState(false);
  const [resultData, setResultData] = useState(null);

  // Kutu koordinatları
  const [boxX1, setBoxX1] = useState('');
  const [boxY1, setBoxY1] = useState('');
  const [boxX2, setBoxX2] = useState('');
  const [boxY2, setBoxY2] = useState('');

  // Görsel üzerindeki dinamik kare çizimi ve ölçekleme takibi için stateler
  const [canvasLayout, setCanvasLayout] = useState(null);
  const [touchStart, setTouchStart] = useState(null);
  const [touchCurrent, setTouchCurrent] = useState(null);

  // PanResponder'ın güncel stateleri görebilmesi için Ref deposu
  const gestureStateRef = useRef({
    start: null,
    current: null,
    layout: null,
    img: null
  });

  // State'ler değiştikçe Ref deposunu güncelliyoruz
  useEffect(() => { gestureStateRef.current.img = img90; }, [img90]);
  useEffect(() => { gestureStateRef.current.layout = canvasLayout; }, [canvasLayout]);

  const pickImage = async (setImageFunc) => {
    let result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      allowsEditing: false, 
      quality: 1,
    });
    if (!result.canceled) {
      setImageFunc(result.assets[0]);
      resetBoxCoordinates();
    }
  };

  const takePhoto = async (setImageFunc) => {
    const { status } = await ImagePicker.requestCameraPermissionsAsync();
    if (status !== 'granted') {
      Alert.alert('İzin Gerekli', 'Kamera izni vermeniz gerekiyor.');
      return;
    }
    let result = await ImagePicker.launchCameraAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      allowsEditing: false, 
      quality: 1,
    });
    if (!result.canceled) {
      setImageFunc(result.assets[0]);
      resetBoxCoordinates();
    }
  };

  const resetBoxCoordinates = () => {
    setBoxX1('');
    setBoxY1('');
    setBoxX2('');
    setBoxY2('');
    setTouchStart(null);
    setTouchCurrent(null);
    gestureStateRef.current.start = null;
    gestureStateRef.current.current = null;
  };

  // Görsel üzerinde parmakla kare çizilmesini sağlayan PanResponder mekanizması
  const panResponder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponder: () => true,
      onPanResponderGrant: (evt) => {
        const pos = { x: evt.nativeEvent.locationX, y: evt.nativeEvent.locationY };
        setTouchStart(pos);
        setTouchCurrent(pos);
        gestureStateRef.current.start = pos;
        gestureStateRef.current.current = pos;
      },
      onPanResponderMove: (evt) => {
        const pos = { x: evt.nativeEvent.locationX, y: evt.nativeEvent.locationY };
        setTouchCurrent(pos);
        gestureStateRef.current.current = pos;
      },
      onPanResponderRelease: () => {
        const { start, current, layout, img } = gestureStateRef.current;

        if (!start || !current || !layout || !img) return;

        const scaleX = img.width / layout.width;
        const scaleY = img.height / layout.height;

        const x1 = Math.round(Math.min(start.x, current.x) * scaleX);
        const y1 = Math.round(Math.min(start.y, current.y) * scaleY);
        const x2 = Math.round(Math.max(start.x, current.x) * scaleX);
        const y2 = Math.round(Math.max(start.y, current.y) * scaleY);

        if (Math.abs(x2 - x1) > 10 && Math.abs(y2 - y1) > 10) {
          setBoxX1(x1.toString());
          setBoxY1(y1.toString());
          setBoxX2(x2.toString());
          setBoxY2(y2.toString());
        } else {
          Alert.alert("Hata", "Lütfen dişi kapsayacak şekilde daha belirgin bir kare çizin.");
          resetBoxCoordinates();
        }
      },
    })
  ).current;

  const sendForAnalysis = async () => {
    if (!name || !studentNo || !img90) {
      Alert.alert("Eksik Bilgi", "Lütfen tüm bilgileri doldurun ve fotoğraf çekin.");
      return;
    }

    if (!boxX1 || !boxY1 || !boxX2 || !boxY2) {
      Alert.alert("Hedef Diş Seçilmedi", "Lütfen görsel üzerinde parmağınızı sürükleyerek hedef dişi kare içine alın.");
      return;
    }

    setLoading(true);
    let formData = new FormData();
    formData.append('student_name', name);
    formData.append('student_lastname', lastname);
    formData.append('student_no', studentNo);
    formData.append('img_90', { uri: img90.uri, name: 'okluzal.jpg', type: 'image/jpeg' });
    
    formData.append('box_x1', boxX1);
    formData.append('box_y1', boxY1);
    formData.append('box_x2', boxX2);
    formData.append('box_y2', boxY2);

    try {
      const response = await axios.post(BACKEND_URL, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 45000, 
      });
      
      // backend'den json formatında metrics objesi bekliyoruz
      if (response.data && response.data.metrics) {
        setResultData(response.data.metrics);
      } else {
        Alert.alert("Analiz Hatası", "Sunucudan geçersiz veri yapısı döndü. Lütfen Flask backend çıktısını kontrol edin.");
      }
    } catch (error) {
      console.error(error);
      Alert.alert("Bağlantı Hatası", "Sunucuya ulaşılamadı. IP adresini ve sunucu durumunu kontrol edin.");
    } finally {
      setLoading(false);
    }
  };

  const ResultRow = ({ title, value, score, isSpecial }) => (
    <View style={[styles.tableRow, isSpecial ? styles.specialRow : null]}>
      <Text style={styles.tableColTitle}>{title}</Text>
      <Text style={styles.tableColValue}>{value}</Text>
      <Text style={styles.tableColScore}>{score} Puan</Text>
    </View>
  );

  // Ekranda parmakla çizilen kırmızı karenin gösterilmesi
  const renderSelectionBox = () => {
    if (!touchStart || !touchCurrent) return null;
    const width = touchCurrent.x - touchStart.x;
    const height = touchCurrent.y - touchStart.y;
    const size = Math.max(Math.abs(width), Math.abs(height));
    
    return (
      <View style={[styles.selectionBox, {
        left: width < 0 ? touchStart.x - size : touchStart.x,
        top: height < 0 ? touchStart.y - size : touchStart.y,
        width: size,
        height: size,
      }]}>
        <View style={styles.centerDot} />
      </View>
    );
  };

  return (
    <ScrollView style={styles.container}>
      <Text style={styles.header}>🦷 Dijital Kavite Analizi</Text>

      {!resultData ? (
        <View>
          <View style={styles.card}>
            <TextInput style={styles.input} placeholder="Ad" onChangeText={setName} value={name} />
            <TextInput style={styles.input} placeholder="Soyad" onChangeText={setLastname} value={lastname} />
            <TextInput style={styles.input} placeholder="Öğrenci No" onChangeText={setStudentNo} value={studentNo} keyboardType="numeric" />
          </View>
          
          <View style={styles.card}>
            <Text style={styles.label}>Oklüzal (90°) Fotoğraf</Text>
            <View style={styles.actionRow}>
              <TouchableOpacity style={styles.camBtn} onPress={() => takePhoto(setImg90)}>
                <Text style={styles.btnText}>📸 Çek</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.galBtn} onPress={() => pickImage(setImg90)}>
                <Text style={styles.btnText}>🖼️ Seç</Text>
              </TouchableOpacity>
            </View>

            {img90 && (
              <View style={styles.imageSelectionContainer}>
                <Text style={styles.infoText}>👇 Parmağınızı sürükleyerek hedef dişi KARE içine alın:</Text>
                <View 
                  {...panResponder.panHandlers}
                  style={styles.canvasContainer}
                  onLayout={(e) => setCanvasLayout(e.nativeEvent.layout)}
                >
                  <Image source={{ uri: img90.uri }} style={styles.sourceImage} resizeMode="cover" />
                  {renderSelectionBox()}
                </View>
                {boxX1 !== '' && <Text style={styles.successText}>✅ Hedef Diş Alanı Seçildi</Text>}
              </View>
            )}
          </View>

          {loading ? (
            <View style={styles.loadingBox}>
              <ActivityIndicator size="large" color="#007bff" />
              <Text style={styles.loadingText}>Yapay Zeka Bölgeyi İzole Edip Analiz Ediyor...</Text>
            </View>
          ) : (
            <TouchableOpacity style={styles.submitBtn} onPress={sendForAnalysis}>
              <Text style={styles.submitBtnText}>ANALİZİ BAŞLAT</Text>
            </TouchableOpacity>
          )}
        </View>
      ) : (
        <View style={styles.resultContainer}>
          <View style={[styles.scoreCard, resultData.fatal_error ? styles.errorCard : null]}>
            <Text style={styles.scoreTitle}>Toplam Puan</Text>
            <Text style={resultData.fatal_error ? styles.totalScoreError : styles.totalScore}>
              {resultData.fatal_error ? "0" : resultData.total_score}
            </Text>
            {resultData.fatal_error && <Text style={styles.errorText}>{resultData.fatal_error}</Text>}
          </View>

          {/* SAM Genişlik Çizimi */}
          <View style={styles.imageCard}>
            <Text style={styles.cardTitle}>Genişlik Analizi (SAM)</Text>
            {resultData.base64_image && (
              <Image 
                source={{ uri: `data:image/jpeg;base64,${resultData.base64_image}` }} 
                style={styles.resultImage} 
                resizeMode="contain" 
              />
            )}
          </View>

          {/* Metrik Listesi */}
          <View style={styles.tableCard}>
            <Text style={styles.cardTitle}>Metrikler</Text>
            <ResultRow title="Outline Form" value={resultData.outline_form?.toFixed(2)} score={resultData.outline_form_score} />
            <ResultRow title="Mesial Isthmus" value={`${resultData.mesial_isthmus_width?.toFixed(2)} mm`} score={resultData.mesial_isthmus_width_score} />
            <ResultRow title="Distal Isthmus" value={`${resultData.distal_isthmus_width?.toFixed(2)} mm`} score={resultData.distal_isthmus_width_score} />
            <ResultRow title="Buccal-Lingual" value={`${resultData.buccal_lingual_width?.toFixed(2)} mm`} score={resultData.buccal_lingual_width_score} />
            <ResultRow title="Mesio-Distal" value={`${resultData.mesio_distal_width?.toFixed(2)} mm`} score={resultData.mesio_distal_width_score} />
            <ResultRow title="Mesial Marginal Ridge" value={`${resultData.mesial_marginal_ridge_width?.toFixed(2)} mm`} score={resultData.mesial_marginal_ridge_width_score} />
            <ResultRow title="Distal Marginal Ridge" value={`${resultData.distal_marginal_ridge_width?.toFixed(2)} mm`} score={resultData.distal_marginal_ridge_width_score} />
          </View>

          <TouchableOpacity style={styles.resetBtn} onPress={() => { setResultData(null); resetBoxCoordinates(); }}>
            <Text style={styles.submitBtnText}>YENİ ANALİZ YAP</Text>
          </TouchableOpacity>
        </View>
      )}
      <View style={{height: 60}} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f4f7f6', padding: 15, paddingTop: 60 },
  header: { fontSize: 26, fontWeight: 'bold', textAlign: 'center', marginBottom: 25, color: '#2c3e50' },
  card: { backgroundColor: 'white', padding: 20, borderRadius: 15, marginBottom: 15, elevation: 3 },
  input: { borderBottomWidth: 1, borderBottomColor: '#ddd', padding: 12, marginBottom: 15, fontSize: 16 },
  label: { fontSize: 16, fontWeight: '600', marginBottom: 10, color: '#34495e' },
  actionRow: { flexDirection: 'row', justifyContent: 'space-between' },
  camBtn: { flex: 1, backgroundColor: '#3498db', padding: 14, borderRadius: 10, alignItems: 'center', marginRight: 5 },
  galBtn: { flex: 1, backgroundColor: '#7f8c8d', padding: 14, borderRadius: 10, alignItems: 'center', marginLeft: 5 },
  btnText: { color: 'white', fontWeight: 'bold' },
  imageSelectionContainer: { marginTop: 15, alignItems: 'center' },
  infoText: { fontSize: 13, color: '#1a56db', fontWeight: '600', marginBottom: 8, textAlign: 'center' },
  canvasContainer: { width: WINDOW_WIDTH - 70, height: 320, backgroundColor: '#eee', borderRadius: 12, overflow: 'hidden', position: 'relative' },
  sourceImage: { width: '100%', height: '100%' },
  selectionBox: { position: 'absolute', borderWidth: 2, borderColor: 'red', backgroundColor: 'rgba(255, 0, 0, 0.15)', justifyContent: 'center', alignItems: 'center' },
  centerDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: 'yellow', borderWidth: 1, borderColor: 'black' },
  successText: { color: '#27ae60', marginTop: 10, fontWeight: 'bold', textAlign: 'center' },
  submitBtn: { backgroundColor: '#2ecc71', padding: 20, borderRadius: 15, alignItems: 'center', elevation: 4 },
  submitBtnText: { color: 'white', fontSize: 18, fontWeight: 'bold' },
  loadingBox: { marginTop: 20, alignItems: 'center' },
  loadingText: { marginTop: 10, color: '#555' },
  scoreCard: { backgroundColor: 'white', padding: 25, borderRadius: 20, alignItems: 'center', marginBottom: 20, elevation: 5, borderLeftWidth: 8, borderLeftColor: '#2ecc71' },
  errorCard: { borderLeftColor: '#e74c3c' },
  scoreTitle: { fontSize: 16, color: '#7f8c8d' },
  totalScore: { fontSize: 48, fontWeight: 'bold', color: '#2ecc71' },
  totalScoreError: { fontSize: 48, fontWeight: 'bold', color: '#e74c3c' },
  errorText: { color: '#e74c3c', fontWeight: 'bold', marginTop: 10, textAlign: 'center' },
  imageCard: { backgroundColor: 'white', padding: 15, borderRadius: 15, marginBottom: 15, elevation: 3 },
  cardTitle: { fontSize: 18, fontWeight: 'bold', marginBottom: 15, color: '#34495e', textAlign: 'center' },
  resultImage: { width: '100%', height: 300, borderRadius: 10 },
  tableCard: { backgroundColor: 'white', borderRadius: 15, overflow: 'hidden', elevation: 3, marginBottom: 20 },
  tableRow: { flexDirection: 'row', padding: 15, borderBottomWidth: 1, borderBottomColor: '#eee' },
  specialRow: { backgroundColor: '#fff9e6' },
  tableColTitle: { flex: 2, color: '#34495e' },
  tableColValue: { flex: 1.5, textAlign: 'center', fontWeight: 'bold' },
  tableColScore: { flex: 1, textAlign: 'right', color: '#2ecc71', fontWeight: 'bold' },
  resetBtn: { backgroundColor: '#e67e22', padding: 18, borderRadius: 15, alignItems: 'center', marginBottom: 40 },
});