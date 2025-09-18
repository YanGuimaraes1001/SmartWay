import numpy as np
from ultralytics import YOLO
import cv2
import cvzone
import time
from collections import deque
from datetime import datetime
import psycopg2
from psycopg2 import sql
import os

# Firebase imports (comentados para teste local)
# import firebase_admin
# from firebase_admin import credentials, db

# Configuração do banco PostgreSQL
DB_CONFIG = {
    'host': 'localhost',
    'database': 'car_detection',
    'user': 'projete',
    'password': '12345678',
    'port': 5432
}

def initialize_database():
    """Inicializar conexão com PostgreSQL"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.close()
        print("Conectado à DB PostgreSQL com sucesso")
        return True
    except Exception as e:
        print(f"Falha ao conectar à DB: {e}")
        return False

def send_to_database(total, current_cars, avg): 
    """Enviar dados de detecção para PostgreSQL"""
    if not database_enabled:
        return
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        insert_query = """
        INSERT INTO veiculos (current_cars, rolling_average, total_count) 
        VALUES (%s, %s, %s)"""
        cursor.execute(insert_query, (current_cars, avg, total))
        conn.commit()
        cursor.close()
        conn.close()
        print(f"Dados enviados à database: Total={total}, Current={current_cars}, Avg={avg:.2f}")
    except Exception as e:
        print(f"Erro ao enviar dados para DB: {e}")

# Firebase initialization (comentado para teste local)
# def initialize_firebase():
#     """Initialize Firebase - update paths and URL for your local setup"""
#     try:
#         firebase_key_path = "chaveFirebase.json"
#         
#         if not os.path.exists(firebase_key_path):
#             print("Warning: Firebase key not found. Firebase logging disabled.")
#             return False
#             
#         cred = credentials.Certificate(firebase_key_path)
#         firebase_admin.initialize_app(cred, {
#             'databaseURL': 'https://projetedb-2224f-default-rtdb.firebaseio.com/'
#         })
#         print("Firebase initialized successfully")
#         return True
#     except Exception as e:
#         print(f"Firebase initialization failed: {e}")
#         return False

# Inicializar banco de dados
database_enabled = initialize_database()

# Configuração do vídeo
VIDEO_PATH = "cars.mp4"
MASK_PATH = "mask-950x480.png"  # Arquivo de máscara opcional

# Verificar se o arquivo de vídeo existe
if not os.path.exists(VIDEO_PATH):
    print(f"Erro: Arquivo de vídeo '{VIDEO_PATH}' não encontrado!")
    print("Coloque o arquivo de vídeo no mesmo diretório do script")
    exit()

cap = cv2.VideoCapture(VIDEO_PATH)

if not cap.isOpened():
    print("Erro: Não foi possível abrir o arquivo de vídeo")
    exit()

# Configuração otimizada de processamento de frames
FRAME_SKIP = 1
frame_count = 0

# Configuração de logging para banco de dados
DATABASE_UPDATE_INTERVAL = 5  # Atualizar banco a cada 5 segundos
last_database_update = 0

# Carregar modelo YOLO otimizado
print("Carregando modelo YOLO...")
model = YOLO("yolov8n.pt")  # Versão nano - mais rápida
print("Modelo YOLO carregado com sucesso")

# Classes de veículos (lista otimizada)
VEHICLE_CLASSES = {2, 3, 5, 7}  # carro, moto, ônibus, caminhão

# Carregar máscara (opcional)
mask = None
if os.path.exists(MASK_PATH):
    mask = cv2.imread(MASK_PATH)
    print("Máscara carregada com sucesso")
else:
    print(f"Aviso: Arquivo de máscara '{MASK_PATH}' não encontrado - continuando sem máscara")

# Configuração da linha de contagem
limits = [400, 297, 673, 297]
totalCount = []

# Configuração da média móvel
WINDOW_SIZE = 20  # Janela de 20 segundos
detection_history = deque()

# Nome da janela (constante para evitar múltiplas janelas)
WINDOW_NAME = 'Detecção Otimizada de Carros'

def euclidean_distance(a, b):
    """Calcular distância euclidiana entre dois pontos"""
    return np.sqrt((a[0] - b[0])**2 + (a[1] - b[1])**2)

def update_rolling_average(current_count):
    """Atualizar média móvel das detecções"""
    current_time = time.time()
    detection_history.append((current_time, current_count))

    # Remover entradas mais antigas que WINDOW_SIZE
    cutoff_time = current_time - WINDOW_SIZE
    while detection_history and detection_history[0][0] < cutoff_time:
        detection_history.popleft()

    return sum(count for _, count in detection_history) / len(detection_history) if detection_history else 0.0

# Função Firebase (comentada para teste local)
# def send_to_firebase(total_crossed, current_cars, avg_cars):
#     """Send detection data to Firebase"""
#     if not firebase_enabled:
#         return
#     try:
#         ref = db.reference(f'/car_detection/{session_id}')
#         data = {
#             'timestamp': int(time.time()),
#             'datetime': datetime.now().isoformat(),
#             'total_count': total_crossed,
#             'current_cars': current_cars,
#             'rolling_average': round(avg_cars, 2)
#         }
#         ref.child(str(int(time.time()))).set(data)
#         print(f"Data sent to Firebase: {data}")
#     except Exception as e:
#         print(f"Firebase error: {e}")

# Variáveis de rastreamento
tracked_objects = {}
next_id = 0
MAX_DISTANCE = 60

print("Iniciando processamento otimizado de vídeo...")
print("Pressione 'q' para sair")

# Obter propriedades do vídeo
fps = cap.get(cv2.CAP_PROP_FPS)
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
print(f"Vídeo: {fps:.1f} FPS, {total_frames} frames")

# Criar janela uma única vez
cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
cv2.resizeWindow(WINDOW_NAME, 1200, 800)

start_time = time.time()
processed_frames = 0

try:
    while True:
        success, img = cap.read()
        if not success:
            print("Fim do vídeo alcançado")
            break

        frame_count += 1
        if frame_count % FRAME_SKIP != 0:
            continue
        
        processed_frames += 1

        # Aplicar máscara se disponível
        if mask is not None:
            mask_resized = cv2.resize(mask, (img.shape[1], img.shape[0]))
            if len(mask_resized.shape) == 3:
                imgRegion = cv2.bitwise_and(img, mask_resized)
            else:
                mask_resized = cv2.cvtColor(mask_resized, cv2.COLOR_GRAY2BGR)
                imgRegion = cv2.bitwise_and(img, mask_resized)
        else:
            imgRegion = img.copy()

        # Executar detecção otimizada
        results = model(imgRegion, stream=False, verbose=False)  # Changed stream=False
        current_detections = []

        # Process results - fixed to handle single result properly
        if results and len(results) > 0:
            r = results[0]  # Take only the first result
            boxes = r.boxes
            if boxes is not None:
                for box in boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    conf = float(box.conf[0])
                    cls = int(box.cls[0])

                    # Filtrar veículos otimizado
                    if cls in VEHICLE_CLASSES and conf > 0.25:
                        w, h = x2 - x1, y2 - y1
                        cx, cy = x1 + w // 2, y1 + h // 2
                        current_detections.append((cx, cy, x1, y1, w, h, conf))

        # Atualizar média móvel
        avg_cars = update_rolling_average(len(current_detections))

        # Rastreamento otimizado
        new_tracked_objects = {}
        used_ids = set()

        for cx, cy, x1, y1, w, h, conf in current_detections:
            best_id = None
            min_dist = MAX_DISTANCE

            # Encontrar objeto mais próximo existente
            for obj_id, (prev_cx, prev_cy) in tracked_objects.items():
                if obj_id not in used_ids:
                    dist = euclidean_distance((cx, cy), (prev_cx, prev_cy))
                    if dist < min_dist:
                        best_id = obj_id
                        min_dist = dist

            # Atribuir novo ID se nenhuma correspondência for encontrada
            if best_id is None:
                best_id = next_id
                next_id += 1

            new_tracked_objects[best_id] = (cx, cy)
            used_ids.add(best_id)

            # Desenho simplificado
            x2, y2 = x1 + w, y1 + h
            cv2.rectangle(img, (x1, y1), (x2, y2), (255, 0, 255), 2)
            cv2.putText(img, f'{conf:.2f}', (x1, max(35, y1)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

            # Detecção de cruzamento de linha
            if limits[0] < cx < limits[2] and limits[1] - 15 < cy < limits[1] + 15:
                if best_id not in totalCount:
                    totalCount.append(best_id)
                    cv2.line(img, (limits[0], limits[1]), (limits[2], limits[3]), (0, 255, 0), 5)

        tracked_objects = new_tracked_objects

        # Desenhar linha de contagem e exibir informações
        cv2.line(img, (limits[0], limits[1]), (limits[2], limits[3]), (0, 0, 255), 3)
        
        # Display otimizado de texto
        cv2.putText(img, f'Total: {len(totalCount)}', (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
        cv2.putText(img, f'Current: {len(current_detections)}', (50, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.putText(img, f'Avg ({WINDOW_SIZE}s): {avg_cars:.1f}', (50, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)

        # Exibir FPS de processamento
        if processed_frames > 0:
            elapsed_time = time.time() - start_time
            processing_fps = processed_frames / elapsed_time
            cv2.putText(img, f'FPS: {processing_fps:.1f}', (50, 140), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        # Atualizações otimizadas do banco de dados
        current_time = time.time()
        if current_time - last_database_update >= DATABASE_UPDATE_INTERVAL:
            send_to_database(len(totalCount), len(current_detections), avg_cars)
            last_database_update = current_time

        # Exibir frame - usando nome de janela consistente
        cv2.imshow(WINDOW_NAME, img)
        
        # Verificar se 'q' foi pressionado para sair
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q') or key == 27:  # 'q' or ESC
            print("Saindo...")
            break
        
        # Verificar se a janela foi fechada
        if cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
            print("Janela fechada pelo usuário")
            break

except KeyboardInterrupt:
    print("\nInterrompido pelo usuário")
except Exception as e:
    print(f"Erro durante execução: {e}")
finally:
    # Limpeza garantida
    cap.release()
    cv2.destroyAllWindows()
    
    # Aguardar um pouco para garantir que as janelas sejam fechadas
    cv2.waitKey(1)
    
    # Atualização final do banco de dados
    if database_enabled and 'current_detections' in locals() and 'avg_cars' in locals():
        send_to_database(len(totalCount), len(current_detections), avg_cars)

print(f"\nProcessamento completo!")
print(f"Total de carros contados: {len(totalCount)}")
print(f"Frames processados: {processed_frames}")
if processed_frames > 0:
    elapsed_time = time.time() - start_time
    print(f"FPS médio de processamento: {processed_frames/elapsed_time:.1f}")
    if fps > 0:
        print(f"Melhoria de desempenho: ~{((processed_frames/elapsed_time) / (fps/FRAME_SKIP)) * 100:.0f}% do tempo real")
