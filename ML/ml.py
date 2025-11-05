import paho.mqtt.client as mqtt
import json
import random
from time import sleep
import time
from datetime import datetime
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import accuracy_score, mean_squared_error
import os

# Configurações dos DOIS Firebase diferentes
FIREBASE_TRAINING_URL = "https://projetedb-2224f-default-rtdb.firebaseio.com/"  # Base de treinamento
FIREBASE_TRAINING_KEY = "chaveml.json"  # Chave para base de treinamento

FIREBASE_SEMAFORO_URL = "https://SEU-PROJETO-SEMAFOROS-default-rtdb.firebaseio.com/"  # Base dos semáforos  
FIREBASE_SEMAFORO_KEY = "chaveFirebase.json"  # Chave para base dos semáforos

# Flags de controle
usar_db_treino = False
usar_db_semaforo = False
firebase_training = None
firebase_semaforo = None

# Tentar inicializar os dois Firebase separadamente
try:
    import firebase_admin
    from firebase_admin import credentials, db
    
    # Firebase 1: Para dados de treinamento ML
    if os.path.exists(FIREBASE_TRAINING_KEY):
        try:
            cred_training = credentials.Certificate(FIREBASE_TRAINING_KEY)
            firebase_training = firebase_admin.initialize_app(cred_training, {
                'databaseURL': FIREBASE_TRAINING_URL
            }, name='training_app')
            print("✓ Firebase TREINAMENTO inicializado")
            usar_db_treino = True
        except Exception as e:
            print(f"✗ Erro Firebase TREINAMENTO: {e}")
            usar_db_treino = False
    else:
        print(f"✗ Chave de treinamento '{FIREBASE_TRAINING_KEY}' não encontrada")
    
    # Firebase 2: Para dados dos semáforos
    if os.path.exists(FIREBASE_SEMAFORO_KEY):
        try:
            cred_semaforo = credentials.Certificate(FIREBASE_SEMAFORO_KEY)
            firebase_semaforo = firebase_admin.initialize_app(cred_semaforo, {
                'databaseURL': FIREBASE_SEMAFORO_URL
            }, name='semaforo_app')
            print("✓ Firebase SEMÁFOROS inicializado")
            usar_db_semaforo = True
        except Exception as e:
            print(f"✗ Erro Firebase SEMÁFOROS: {e}")
            usar_db_semaforo = False
    else:
        print(f"✗ Chave de semáforos '{FIREBASE_SEMAFORO_KEY}' não encontrada")
        
except ImportError:
    print("✗ Firebase Admin SDK não instalado. Use: pip install firebase-admin")
except Exception as e:
    print(f"✗ Erro geral Firebase: {e}")

def inicializar_firebase():
    """Testa conexão com Firebase de treinamento"""
    if usar_db_treino and firebase_training:
        try:
            ref = db.reference('/ml_training_data', app=firebase_training)
            test_data = ref.get()
            print("✓ Conectado ao Firebase TREINAMENTO")
            return True
        except Exception as e:
            print(f"✗ Falha Firebase TREINAMENTO: {e}")
            return False
    return False

def testar_firebase_semaforos():
    """Testa conexão com Firebase dos semáforos"""
    if usar_db_semaforo and firebase_semaforo:
        try:
            ref = db.reference('/car_detection', app=firebase_semaforo)
            test_data = ref.get()
            print("✓ Conectado ao Firebase SEMÁFOROS")
            return True
        except Exception as e:
            print(f"✗ Falha Firebase SEMÁFOROS: {e}")
            return False
    return False

def enviardadosfirebase(dados):
    """Salva dados de treinamento no Firebase de treinamento"""
    if usar_db_treino and firebase_training:
        try:
            ref = db.reference('/ml_training_data', app=firebase_training)
            record = {
                'timestamp': dados[0],
                'semaforo_a_cars': dados[1],
                'semaforo_b_cars': dados[2],
                'semaforo_c_cars': dados[3],
                'semaforo_d_cars': dados[4],
                'hora_dia': dados[5],
                'dia_semana': dados[6],
                'semaforo_escolhido': dados[7],
                'tempo_verde': dados[8],
                'cars_antes': dados[9]
            }
            new_record_ref = ref.push(record)
            print(f"✓ Dados salvos no Firebase TREINAMENTO: {record['semaforo_escolhido']} - {record['tempo_verde']}s")
            return new_record_ref.key
        except Exception as e:
            print(f"✗ Falha ao salvar no Firebase TREINAMENTO: {e}")
            return None
    else:
        print("Firebase TREINAMENTO indisponível - dados não salvos")
        return None

def resultado_treinamento(record_id, cars_depois, eficiencia):
    """Atualiza resultado no Firebase de treinamento"""
    if usar_db_treino and firebase_training and record_id:
        try:
            ref = db.reference(f'/ml_training_data/{record_id}', app=firebase_training)
            ref.update({
                'cars_depois': cars_depois,
                'eficiencia': eficiencia
            })
            print(f"✓ Resultado atualizado no Firebase TREINAMENTO: eficiência {eficiencia:.2f}")
        except Exception as e:
            print(f"✗ Erro ao atualizar no Firebase TREINAMENTO: {e}")

def pegardadostreinamento(limitefirebase=None):
    """Recupera dados do Firebase de treinamento"""
    if usar_db_treino and firebase_training:
        try:
            ref = db.reference('/ml_training_data', app=firebase_training)
            resultados = ref.get()
            if not resultados:
                print("Nenhum dado de treinamento encontrado")
                return []
            
            dados = []
            for key, value in resultados.items():
                if isinstance(value, dict) and 'cars_depois' in value:
                    dados.append([
                        key,
                        value.get('timestamp', 0),
                        value.get('semaforo_a_cars', 0),
                        value.get('semaforo_b_cars', 0),
                        value.get('semaforo_c_cars', 0),
                        value.get('semaforo_d_cars', 0),
                        value.get('hora_dia', 0),
                        value.get('dia_semana', 0),
                        value.get('semaforo_escolhido', 'A'),
                        value.get('tempo_verde', 5),
                        value.get('cars_antes', 0),
                        value.get('cars_depois', 0),
                        value.get('eficiencia', 0)
                    ])
            
            if limitefirebase:
                dados = sorted(dados, key=lambda x: x[1], reverse=True)[:limitefirebase]
            
            print(f"✓ {len(dados)} registros recuperados do Firebase TREINAMENTO")
            return dados
        except Exception as e:
            print(f"✗ Erro ao buscar dados do Firebase TREINAMENTO: {e}")
            return []
    else:
        print("Firebase TREINAMENTO indisponível")
        return []

def verificar_dados_coletados():
    """Verifica dados de treinamento disponíveis"""
    if usar_db_treino and firebase_training:
        try:
            ref = db.reference('/ml_training_data', app=firebase_training)
            dados = ref.get()
            total = len(dados) if dados else 0
            completos = sum(1 for key, value in (dados.items() if dados else []) 
                          if isinstance(value, dict) and 'cars_depois' in value)
            print(f"Firebase TREINAMENTO - Total: {total}, Completos: {completos}")
            return completos
        except Exception as e:
            print(f"✗ Erro ao verificar Firebase TREINAMENTO: {e}")
            return 0
    return 0

def obter_dados_4_lanes():
    """Obtém dados das 4 lanes do Firebase dos semáforos"""
    if usar_db_semaforo and firebase_semaforo:
        try:
            vias_dados = {}
            semaforos = ["A", "B", "C", "D"]
            lanes = ["lane_1", "lane_2", "lane_3", "lane_4"]
            
            print("Buscando dados no Firebase SEMÁFOROS...")
            
            for i, lane in enumerate(lanes):
                try:
                    ref = db.reference(f'/car_detection/{lane}', app=firebase_semaforo)
                    lane_data = ref.get()
                    
                    if lane_data:
                        print(f"✓ Dados encontrados para {lane}")
                        
                        # Busca sessão mais recente
                        latest_session = None
                        latest_timestamp = 0
                        
                        for session_id, session_data in lane_data.items():
                            if isinstance(session_data, dict):
                                for timestamp_key in session_data.keys():
                                    try:
                                        timestamp_val = int(timestamp_key)
                                        if timestamp_val > latest_timestamp:
                                            latest_timestamp = timestamp_val
                                            latest_session = session_id
                                    except ValueError:
                                        continue
                        
                        if latest_session:
                            session_ref = db.reference(f'/car_detection/{lane}/{latest_session}', app=firebase_semaforo)
                            session_data = session_ref.get()
                            
                            if session_data:
                                timestamps = []
                                for ts_key in session_data.keys():
                                    try:
                                        timestamps.append(int(ts_key))
                                    except ValueError:
                                        continue
                                
                                if timestamps:
                                    latest_ts = max(timestamps)
                                    latest_data = session_data[str(latest_ts)]
                                    current_cars = latest_data.get('current_cars', 0)
                                    vias_dados[semaforos[i]] = current_cars
                                    print(f"  {lane} -> Semáforo {semaforos[i]}: {current_cars} carros")
                                else:
                                    vias_dados[semaforos[i]] = 0
                            else:
                                vias_dados[semaforos[i]] = 0
                        else:
                            vias_dados[semaforos[i]] = 0
                    else:
                        vias_dados[semaforos[i]] = 0
                        
                except Exception as e:
                    print(f"✗ Erro ao acessar {lane} no Firebase SEMÁFOROS: {e}")
                    vias_dados[semaforos[i]] = 0
            
            print(f"Dados do Firebase SEMÁFOROS: {vias_dados}")
            return vias_dados
            
        except Exception as e:
            print(f"✗ Erro geral no Firebase SEMÁFOROS: {e}")
            return None
    else:
        # Dados simulados quando Firebase dos semáforos não está disponível
        print("Firebase SEMÁFOROS indisponível - usando dados simulados")
        agora = datetime.now()
        hora = agora.hour
        
        # Simula padrões de tráfego baseados na hora
        if 7 <= hora <= 9 or 17 <= hora <= 19:  # Rush hours
            multiplicador = 1.5
        elif 22 <= hora or hora <= 6:  # Madrugada
            multiplicador = 0.3
        else:
            multiplicador = 1.0
        
        vias = {
            'A': int(random.randint(0, 8) * multiplicador),
            'B': int(random.randint(0, 6) * multiplicador),
            'C': int(random.randint(0, 7) * multiplicador),
            'D': int(random.randint(0, 5) * multiplicador)
        }
        
        print(f"Dados simulados: {vias}")
        return vias

# Resto do código (TrafficMLController, decisao_baseada_regras, etc.) permanece igual...

class TrafficMLController:
    def __init__(self):
        self.semaforo_model = None
        self.tempo_model = None
        self.is_trained = False
        self.feature_columns = ['semaforo_a_cars', 'semaforo_b_cars', 'semaforo_c_cars', 
                              'semaforo_d_cars', 'hora_dia', 'dia_semana', 'cars_antes']
        
    def preparar_dados_treinamento(self):
        dados_completos = pegardadostreinamento()
        if len(dados_completos) < 10:
            print(f"Poucos dados para treinamento: {len(dados_completos)} (mínimo: 10)")
            return None, None, None, None
            
        colunas = ['id', 'timestamp', 'semaforo_a_cars', 'semaforo_b_cars', 
                  'semaforo_c_cars', 'semaforo_d_cars', 'hora_dia', 'dia_semana',
                  'semaforo_escolhido', 'tempo_verde', 'cars_antes', 'cars_depois', 'eficiencia']
        
        df = pd.DataFrame(dados_completos, columns=colunas)
        
        X = df[self.feature_columns]
        semaforo_map = {'A': 0, 'B': 1, 'C': 2, 'D': 3}
        y_semaforo = df['semaforo_escolhido'].map(semaforo_map)
        y_tempo = df['tempo_verde']
        
        return train_test_split(X, y_semaforo, y_tempo, test_size=0.2, random_state=42)
        
    def treinar_modelos(self):
        data = self.preparar_dados_treinamento()
        if data[0] is None:
            return False
            
        X_train, X_test, y_sem_train, y_sem_test, y_tempo_train, y_tempo_test = data
        
        self.semaforo_model = RandomForestClassifier(n_estimators=50, random_state=42)
        self.semaforo_model.fit(X_train, y_sem_train)
        
        self.tempo_model = RandomForestRegressor(n_estimators=50, random_state=42)
        self.tempo_model.fit(X_train, y_tempo_train)
        
        sem_pred = self.semaforo_model.predict(X_test)
        tempo_pred = self.tempo_model.predict(X_test)
        
        sem_accuracy = accuracy_score(y_sem_test, sem_pred)
        tempo_mse = mean_squared_error(y_tempo_test, tempo_pred)
        
        print(f"ML Treinado - Precisão: {sem_accuracy:.2f}, Erro: {tempo_mse:.2f}")
        
        self.is_trained = True
        return True
        
    def prever_melhor_acao(self, vias_dados, hora_atual, dia_semana):
        if not self.is_trained:
            return None, None
            
        features = np.array([[
            vias_dados.get('A', 0),
            vias_dados.get('B', 0),
            vias_dados.get('C', 0),
            vias_dados.get('D', 0),
            hora_atual,
            dia_semana,
            sum(vias_dados.values())
        ]])
        
        sem_pred = self.semaforo_model.predict(features)[0]
        tempo_pred = self.tempo_model.predict(features)[0]
        
        semaforo_map = {0: 'A', 1: 'B', 2: 'C', 3: 'D'}
        semaforo_escolhido = semaforo_map[sem_pred]
        tempo_escolhido = max(5, min(20, int(tempo_pred)))
        
        return semaforo_escolhido, tempo_escolhido

def decisao_baseada_regras(vias_dados):
    max_cars = 0
    melhor_semaforo = 'A'
    
    for semaforo, cars in vias_dados.items():
        if cars > max_cars:
            max_cars = cars
            melhor_semaforo = semaforo
    
    tempo = min(5 + max_cars * 2, 20)
    return melhor_semaforo, tempo

def registrar_resultado_ciclo(vias_dados_depois):
    global ultimo_record_id, estado_anterior, tempo_liberacao
    
    if ultimo_record_id and estado_anterior:
        cars_depois = sum(vias_dados_depois.values()) 
        cars_antes = sum(estado_anterior.values())
        cars_reduzidos = cars_antes - cars_depois
        eficiencia = cars_reduzidos / tempo_liberacao if tempo_liberacao > 0 else 0
        
        resultado_treinamento(ultimo_record_id, cars_depois, eficiencia)

# Inicialização e testes
print("\n=== INICIALIZAÇÃO DO SISTEMA ===")
print(f"Firebase TREINAMENTO: {'Ativo' if usar_db_treino else 'Inativo'}")
print(f"Firebase SEMÁFOROS: {'Ativo' if usar_db_semaforo else 'Inativo'}")

if usar_db_treino:
    if inicializar_firebase():
        print("Sistema de treinamento ML ativado")
    else:
        print("Problemas no Firebase TREINAMENTO")
        usar_db_treino = False

if usar_db_semaforo:
    if testar_firebase_semaforos():
        print("Sistema de dados dos semáforos ativado")  
    else:
        print("Problemas no Firebase SEMÁFOROS")
        usar_db_semaforo = False

# Resto da lógica MQTT e loop principal...
ml_controller = TrafficMLController()
usar_ml = False

estado_anterior = None
ultimo_record_id = None
ciclos_desde_treinamento = 0

broker = "localhost"
porta = 1883
topico_envia = "3105/comando"
topico_recepcao = "3105/confirmacao"
tempo_liberacao = 5
semaforos = ["A", "B", "C", "D"]
mensagem_recebida = ""
mensagem_final = ""
contador = 0
semaforo_escolhido_anterior = "A"
semaforo_escolhido = "C"

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Conectado ao broker MQTT!")
        client.subscribe(topico_recepcao)
    else:
        print(f"Falha na conexão MQTT. Continuando...")

def publica_mensagem(client, vias_dados):
    global semaforo_escolhido, semaforo_escolhido_anterior
    global ultimo_record_id, estado_anterior, usar_ml, tempo_liberacao

    estado_anterior = {
        'A': vias_dados.get('A', 0),
        'B': vias_dados.get('B', 0),
        'C': vias_dados.get('C', 0),
        'D': vias_dados.get('D', 0)
    }

    if usar_ml and ml_controller.is_trained:
        agora = datetime.now()
        semaforo_ml, tempo_ml = ml_controller.prever_melhor_acao(
            estado_anterior, agora.hour, agora.weekday()
        )
        
        if semaforo_ml and tempo_ml:
            semaforo_escolhido = semaforo_ml
            tempo_liberacao = tempo_ml
            estrategia = "ML"
        else:
            semaforo_escolhido, tempo_liberacao = decisao_baseada_regras(estado_anterior)
            estrategia = "Regras"
    else:
        if sum(vias_dados.values()) > 0:
            semaforo_escolhido, tempo_liberacao = decisao_baseada_regras(estado_anterior)
            estrategia = "Regras"
        else:
            while semaforo_escolhido == semaforo_escolhido_anterior:
                semaforo_escolhido = random.choice(semaforos)
            tempo_liberacao = random.randint(5, 15)
            estrategia = "Aleatório"
    
    semaforo_escolhido_anterior = semaforo_escolhido
    print(f"Decisão ({estrategia}): Semáforo {semaforo_escolhido}, Tempo {tempo_liberacao}s")
    
    # Salvar dados de treinamento
    timestamp = time.time()
    agora = datetime.fromtimestamp(timestamp)
    
    dados_treinamento = (
        timestamp, estado_anterior['A'], estado_anterior['B'],
        estado_anterior['C'], estado_anterior['D'], agora.hour,
        agora.weekday(), semaforo_escolhido, tempo_liberacao,
        sum(estado_anterior.values())
    )
    ultimo_record_id = enviardadosfirebase(dados_treinamento)
    
    # Publicar MQTT
    mensagem_liberacao = {"V": tempo_liberacao}
    modelo_mensagem = {"A": "AV", "B": "BV", "C": "CV", "D": "DV"}

    for semaforo in semaforos:
        if semaforo == semaforo_escolhido:
            modelo_mensagem[semaforo] = mensagem_liberacao
        else:
            modelo_mensagem[semaforo] = "L"

    mensagem = json.dumps(modelo_mensagem)
    
    try:
        client.subscribe(topico_recepcao)
        client.publish(topico_envia, mensagem, qos=2)        
        print(f"Mensagem MQTT enviada: {mensagem}")
    except:
        print(f"MQTT indisponível. Mensagem seria: {mensagem}")

def on_message(client, userdata, msg):
    global mensagem_recebida, mensagem_final
    mensagem_recebida = msg.payload.decode()
    print(f"Recebido MQTT: `{mensagem_recebida}`")

    if mensagem_recebida not in mensagem_final:
        mensagem_final += mensagem_recebida
        mensagem_final_lista = list(mensagem_final)
        mensagem_final_lista.sort()
        mensagem_final = "".join(mensagem_final_lista)

# Inicializar MQTT
try:
    cliente = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    cliente.on_connect = on_connect
    cliente.on_message = on_message
    cliente.connect(broker, porta, 10)
    cliente.loop_start()
    sleep(2)
    print("MQTT inicializado")
except:
    print("MQTT não disponível - continuando sem")
    cliente = None

tempo = 0
ciclo_contador = 0

print("\n=== INICIANDO SISTEMA DE CONTROLE DE TRÁFEGO ===")
print("Para usar os dois Firebase corretamente:")
print(f"1. Coloque a chave do Firebase de TREINAMENTO em: {FIREBASE_TRAINING_KEY}")
print(f"2. Coloque a chave do Firebase dos SEMÁFOROS em: {FIREBASE_SEMAFORO_KEY}")
print(f"3. Ajuste as URLs dos projetos no código")

while True:
    ciclos_desde_treinamento += 1
    ciclo_contador += 1
    
    print(f"\n=== CICLO {ciclo_contador} ===")
    
    # Obter dados (do Firebase dos semáforos ou simulados)
    vias = obter_dados_4_lanes()
    
    if vias is None or sum(vias.values()) == 0:
        print("Usando dados simulados...")
        vias = {
            'A': random.randint(0, 8), 
            'B': random.randint(0, 8), 
            'C': random.randint(0, 8), 
            'D': random.randint(0, 8)
        }
    
    print(f"DADOS DAS VIAS: {vias}")

    # Simular tempo de semáforo
    timeout_seconds = tempo_liberacao + 2
    for i in range(timeout_seconds):
        print(f"Tempo {i+1}/{timeout_seconds}...")
        sleep(1)
        
    # Registrar resultado
    registrar_resultado_ciclo(vias)
        
    # Verificar treinamento ML
    if ciclo_contador % 5 == 0:
        dados_disponiveis = verificar_dados_coletados()
        
        if dados_disponiveis >= 10 and not usar_ml:
            print("INICIANDO TREINAMENTO ML!")
            if ml_controller.treinar_modelos():
                usar_ml = True
                print("MACHINE LEARNING ATIVADO!")
            
    if usar_ml and ciclos_desde_treinamento >= 15:
        print("RETREINANDO MODELOS...")
        if ml_controller.treinar_modelos():
            print("Retreinamento concluído!")
        ciclos_desde_treinamento = 0

    # Reset
    mensagem_final = ""
    tempo = 0

    status_treino = "Ativo" if usar_db_treino else "Inativo"
    status_semaforo = "Ativo" if usar_db_semaforo else "Simulado"  
    status_ml = "Ativo" if usar_ml else "Desativado"
    
    print(f"Status: ML={status_ml}, Treinamento={status_treino}, Semáforos={status_semaforo}")
    
    if cliente:
        publica_mensagem(cliente, vias)
    
    sleep(2)
