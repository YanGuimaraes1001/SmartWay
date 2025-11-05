import paho.mqtt.client as mqtt
import json
import time
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import accuracy_score, mean_squared_error
import psycopg2
import traceback

# Database configurations (unchanged)
CAR_DETECTION_CONFIG = {
    'host': 'localhost',
    'database': 'car_detection',
    'user': 'projete',
    'password': '12345678',
    'port': '5432'
}

MLDB_CONFIG = {
    'host': 'localhost',
    'database': 'mlrecords',
    'user': 'mldb',
    'password': '12345678',
    'port': '5432'
}

# Global variables
usar_db_treino = True
usar_ml = True
semaforos = ['A', 'B', 'C', 'D']
topico_envia = '3105/comando'
topico_recepcao = '3105/confirmacao'
semaforo_escolhido = None
semaforo_escolhido_anterior = None
ultimo_record_id = None
estado_anterior = None
tempo_liberacao = None
ciclos_desde_treinamento = 0
esperando_feedback = False
timestamp_comando = None
dados_antes_comando = None
feedbacks_recebidos = set()
proximo_semaforo_rotacao_forçada = 'A'
last_opened_cycles = {'A': 0, 'B': 0, 'C': 0, 'D': 0}
opened_this_round = set()

# TrafficMLController, criar_tabela_treinamento, pegardadostreinamento, 
# enviardadospsql, verificar_dados_coletados, get_vias_dados, 
# decisao_baseada_regras (unchanged for brevity, same as previous version)

class TrafficMLController:
    def __init__(self):
        self.semaforo_model = None
        self.tempo_model = None
        self.is_trained = False
        self.feature_columns = ['semaforo_a_cars', 'semaforo_b_cars', 'semaforo_c_cars',
                               'semaforo_d_cars', 'hora_dia', 'dia_semana', 'cars_antes',
                               'cars_target_lane', 'relative_density', 'cycles_since_open']

    def preparar_dados_treinamento(self):
        dados_completos = pegardadostreinamento()
        print(f"Dados obtidos para treinamento: {len(dados_completos)}")

        if len(dados_completos) < 10:
            print(f"Poucos dados para treinamento: {len(dados_completos)}")
            return None, None, None, None, None, None

        colunas = ['id', 'timestamp', 'semaforo_a_cars', 'semaforo_b_cars',
                   'semaforo_c_cars', 'semaforo_d_cars', 'hora_dia', 'dia_semana',
                   'semaforo_escolhido', 'tempo_verde', 'cars_antes', 'cars_depois', 'eficiencia']

        df = pd.DataFrame(dados_completos, columns=colunas)
        print(f"DataFrame criado com {len(df)} registros")

        def extract_target_cars(row):
            sem_map = {'A': 'semaforo_a_cars', 'B': 'semaforo_b_cars', 
                      'C': 'semaforo_c_cars', 'D': 'semaforo_d_cars'}
            return row[sem_map[row['semaforo_escolhido'].strip()]]

        df['cars_target_lane'] = df.apply(extract_target_cars, axis=1)
        df['relative_density'] = df['cars_target_lane'] / (df['cars_antes'] + 1)
        df['cycles_since_open'] = np.random.randint(0, 10, size=len(df))

        X = df[self.feature_columns].copy()
        semaforo_map = {'A': 0, 'B': 1, 'C': 2, 'D': 3}
        y_semaforo = df['semaforo_escolhido'].str.strip().map(semaforo_map)
        y_tempo = df['tempo_verde']

        return train_test_split(X, y_semaforo, y_tempo, test_size=0.2, random_state=42)

    def treinar_modelos(self):
        try:
            data = self.preparar_dados_treinamento()
            if data[0] is None:
                return False

            X_train, X_test, y_sem_train, y_sem_test, y_tempo_train, y_tempo_test = data
            print(f"Treinando com {len(X_train)} amostras...")

            self.semaforo_model = RandomForestClassifier(n_estimators=50, random_state=42)
            self.semaforo_model.fit(X_train, y_sem_train)
            self.tempo_model = RandomForestRegressor(n_estimators=100, 
                                                     max_depth=10,
                                                     min_samples_split=5,
                                                     random_state=42)
            self.tempo_model.fit(X_train, y_tempo_train)

            sem_pred = self.semaforo_model.predict(X_test)
            tempo_pred = self.tempo_model.predict(X_test)

            sem_accuracy = accuracy_score(y_sem_test, sem_pred)
            tempo_mse = mean_squared_error(y_tempo_test, tempo_pred)

            print(f"Precisão do modelo de semáforo: {sem_accuracy:.2f}")
            print(f"MSE do modelo de tempo: {tempo_mse:.2f}")

            self.is_trained = True
            return True

        except Exception as e:
            print(f"Erro ao treinar modelos: {e}")
            traceback.print_exc()
            return False

    def prever_melhor_acao(self, vias_dados, hora_atual, dia_semana, exclude=None, candidates=None):
        if not self.is_trained:
            print("Modelos não estão treinados")
            return None, None

        try:
            features_dict = {
                'semaforo_a_cars': [vias_dados.get('A', 0)],
                'semaforo_b_cars': [vias_dados.get('B', 0)],
                'semaforo_c_cars': [vias_dados.get('C', 0)],
                'semaforo_d_cars': [vias_dados.get('D', 0)],
                'hora_dia': [hora_atual],
                'dia_semana': [dia_semana],
                'cars_antes': [sum(vias_dados.values())],
                'cars_target_lane': [0],
                'relative_density': [0],
                'cycles_since_open': [0]
            }

            probs = self.semaforo_model.predict_proba(
                pd.DataFrame({k: v for k, v in features_dict.items() 
                            if k in ['semaforo_a_cars', 'semaforo_b_cars', 'semaforo_c_cars',
                                   'semaforo_d_cars', 'hora_dia', 'dia_semana', 'cars_antes']})
            )[0]
            
            sem_map = {0: 'A', 1: 'B', 2: 'C', 3: 'D'}
            sem_map_inv = {'A': 0, 'B': 1, 'C': 2, 'D': 3}

            bonus = 0.1
            log_probs = np.log(probs + 1e-10)
            for i in range(4):
                lane = sem_map[i]
                log_probs[i] += bonus * last_opened_cycles[lane]

            if exclude:
                excl_idx = sem_map_inv[exclude]
                log_probs[excl_idx] = -np.inf

            if candidates:
                for i in range(4):
                    if sem_map[i] not in candidates:
                        log_probs[i] = -np.inf

            if np.all(log_probs == -np.inf):
                sem_idx = 0
            else:
                log_probs -= np.max(log_probs)
                probs_adjusted = np.exp(log_probs) / np.sum(np.exp(log_probs))
                sem_idx = np.argmax(probs_adjusted)

            semaforo_escolhido = sem_map[sem_idx]

            cars_target = vias_dados.get(semaforo_escolhido, 0)
            total_cars = sum(vias_dados.values())
            
            features_dict['cars_target_lane'] = [cars_target]
            features_dict['relative_density'] = [cars_target / (total_cars + 1)]
            features_dict['cycles_since_open'] = [last_opened_cycles[semaforo_escolhido]]

            features = pd.DataFrame(features_dict)
            tempo_pred = self.tempo_model.predict(features)[0]
            
            tempo_escolhido = self._calcular_tempo_adaptativo(
                cars_target, total_cars, tempo_pred, semaforo_escolhido
            )

            print(f"ML predição: Semáforo {semaforo_escolhido}, Tempo {tempo_escolhido}s")
            print(f"  └─ Carros na via: {cars_target}, Densidade relativa: {cars_target/(total_cars+1):.2%}")
            return semaforo_escolhido, tempo_escolhido

        except Exception as e:
            print(f"Erro na predição ML: {e}")
            traceback.print_exc()
            return None, None

    def _calcular_tempo_adaptativo(self, cars_target, total_cars, tempo_pred, semaforo):
        tempo_base = max(5, min(30, int(tempo_pred)))
        
        if total_cars > 0:
            density_ratio = cars_target / total_cars
            
            if cars_target == 0:
                tempo_escolhido = 5
            elif cars_target <= 2:
                tempo_escolhido = min(8, tempo_base)
            elif cars_target <= 5:
                tempo_escolhido = min(12, tempo_base)
            elif cars_target <= 10:
                tempo_escolhido = min(18, tempo_base)
            else:
                tempo_escolhido = tempo_base
            
            if density_ratio > 0.5 and cars_target >= 5:
                tempo_escolhido = min(30, int(tempo_escolhido * 1.2))
            
            cycles = last_opened_cycles[semaforo]
            if cycles >= 5 and cars_target >= 3:
                tempo_escolhido = min(30, tempo_escolhido + 3)
            
        else:
            tempo_escolhido = 5
        
        return max(5, min(30, int(tempo_escolhido)))

ml_controller = TrafficMLController()

def criar_tabela_treinamento():
    try:
        conn = psycopg2.connect(**MLDB_CONFIG)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'ml_training_data' AND column_name = 'feedback_recebido'
        """)
        if cursor.fetchone() is None:
            print("Adicionando coluna feedback_recebido...")
            cursor.execute("""
                ALTER TABLE ml_training_data
                ADD COLUMN IF NOT EXISTS feedback_recebido BOOLEAN DEFAULT FALSE
            """)
            conn.commit()
            print("✓ Coluna adicionada")

        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Erro ao verificar/criar tabela: {e}")

def pegardadostreinamento():
    try:
        conn = psycopg2.connect(**MLDB_CONFIG)
        cursor = conn.cursor()

        print("=== DEBUG DADOS DE TREINAMENTO ===")

        cursor.execute("SELECT COUNT(*) FROM ml_training_data")
        total_registros = cursor.fetchone()[0]
        print(f"Total de registros na tabela: {total_registros}")

        cursor.execute("SELECT COUNT(*) FROM ml_training_data WHERE cars_depois IS NOT NULL")
        registros_completos = cursor.fetchone()[0]
        print(f"Registros com cars_depois: {registros_completos}")

        cursor.execute("""
            SELECT id, timestamp, semaforo_a_cars, semaforo_b_cars, semaforo_c_cars, semaforo_d_cars,
                   hora_dia, dia_semana, semaforo_escolhido, tempo_verde, cars_antes, cars_depois, eficiencia
            FROM ml_training_data
            WHERE cars_depois IS NOT NULL AND eficiencia IS NOT NULL
            ORDER BY timestamp DESC
            LIMIT 1000
        """)

        dados = cursor.fetchall()
        cursor.close()
        conn.close()

        print(f"Dados retornados para treinamento: {len(dados)} registros")
        print("="*40)
        return dados

    except Exception as e:
        print(f"Erro ao buscar dados de treinamento: {e}")
        return []

def enviardadospsql(dados_treinamento):
    try:
        conn = psycopg2.connect(**MLDB_CONFIG)
        cursor = conn.cursor()
        query = """
            INSERT INTO ml_training_data
            (timestamp, semaforo_a_cars, semaforo_b_cars, semaforo_c_cars, semaforo_d_cars,
             hora_dia, dia_semana, semaforo_escolhido, tempo_verde, cars_antes)
            VALUES (to_timestamp(%s), %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """

        cursor.execute(query, dados_treinamento)
        record_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        conn.close()
        print(f"Dados de treinamento salvos, ID: {record_id}")
        return record_id
    except Exception as e:
        print(f"Erro ao salvar dados no PostgreSQL: {e}")
        return None

def verificar_dados_coletados():
    if usar_db_treino:
        try:
            conn = psycopg2.connect(**MLDB_CONFIG)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM ml_training_data")
            total = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM ml_training_data WHERE cars_depois IS NOT NULL")
            completos = cursor.fetchone()[0]
            cursor.close()
            conn.close()
            print(f"Registros totais: {total}, Registros completos: {completos}")
            return completos
        except Exception as e:
            print(f"Erro ao verificar dados: {e}")
            return 0
    return 0

def get_vias_dados():
    lane_mapping = {
        'lane_1': 'A',
        'lane_2': 'B',
        'lane_3': 'C',
        'lane_4': 'D'
    }
    vias_dados = {'A': 0, 'B': 0, 'C': 0, 'D': 0}

    try:
        conn = psycopg2.connect(**CAR_DETECTION_CONFIG)
        cursor = conn.cursor()

        query = """
SELECT lane_id, current_cars, timestamp
FROM (
    SELECT id, lane_id, current_cars, timestamp,
           ROW_NUMBER() OVER (PARTITION BY lane_id ORDER BY id DESC) AS rn
    FROM veiculos
) sub
WHERE rn = 1
ORDER BY id DESC;
"""

        cursor.execute(query)
        rows = cursor.fetchall()

        print(f"Resultados da query: {rows}")

        latest_timestamp = None

        for row in rows:
            lane_id = row[0]
            current_cars = row[1] if row[1] is not None else 0
            timestamp = row[2] if len(row) > 2 else None

            if timestamp:
                if latest_timestamp is None or timestamp > latest_timestamp:
                    latest_timestamp = timestamp
            if lane_id in lane_mapping:
                vias_dados[lane_mapping[lane_id]] = current_cars

        cursor.close()
        conn.close()

        if sum(vias_dados.values()) > 0:
            print(f"✓ Dados reais das vias: {vias_dados}")
            if latest_timestamp:
                age_seconds = (datetime.now() - latest_timestamp).total_seconds()
                print(f"📊 Idade dos dados: {age_seconds:.1f}s atrás")
                if age_seconds > 10:
                    print(f"⚠️ AVISO: Dados podem estar desatualizados!")
                    return vias_dados
        else:
            print("⚠ Nenhum dado encontrado, aguardando novos dados...")
            return None

        return vias_dados

    except Exception as e:
        print(f"Erro ao buscar dados das vias: {e}")
        return None

def decisao_baseada_regras(vias_dados, exclude=None, candidates=None):
    if not vias_dados or sum(vias_dados.values()) == 0:
        return 'A', 10

    if candidates is None:
        candidates = semaforos

    candidates = [c for c in candidates if c != exclude] if exclude else candidates

    if not candidates:
        return 'A', 10

    bonus = 2.0
    effective = {k: vias_dados[k] + bonus * last_opened_cycles[k] for k in candidates}

    melhor_semaforo = max(effective, key=effective.get)
    cars_target = vias_dados[melhor_semaforo]
    total_cars = sum(vias_dados.values())

    if cars_target == 0:
        tempo = 5
    elif cars_target <= 2:
        tempo = 8
    elif cars_target <= 5:
        tempo = 12
    elif cars_target <= 10:
        tempo = 18
    else:
        tempo = 25

    if total_cars > 0 and cars_target / total_cars > 0.5 and cars_target >= 5:
        tempo = min(30, int(tempo * 1.2))

    if last_opened_cycles[melhor_semaforo] >= 5 and cars_target >= 3:
        tempo = min(30, tempo + 3)

    tempo = max(5, min(30, int(tempo)))
    print(f"  └─ Regras: {cars_target} carros → {tempo}s (densidade: {cars_target/(total_cars+0.001):.1%})")
    
    return melhor_semaforo, tempo

def envia_comando_mqtt(client, semaforo_verde, tempo_verde, estrategia):
    """Send MQTT commands with minimal gap between red-all and green"""
    global topico_envia, semaforos, esperando_feedback, feedbacks_recebidos, timestamp_comando

    # Step 1: Red all
    red_all_command = {sem: "L" for sem in semaforos}
    red_all_message = json.dumps(red_all_command)

    try:
        print("--- PASSO 1: Enviando RED-ALL (L) para todas as vias ---")
        client.publish(topico_envia, red_all_message, qos=1)
        # Removed time.sleep(0.1) to minimize gap
    except Exception as e:
        print(f"Erro ao publicar comando RED-ALL: {e}")
        return

    # Step 2: Green for chosen semaphore
    green_command = {sem: "L" for sem in semaforos}
    green_command[semaforo_verde] = {"V": tempo_verde}
    green_message = json.dumps(green_command)

    try:
        result = client.publish(topico_envia, green_message, qos=1)
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print(f"--- PASSO 2: Enviando comando GREEN ({semaforo_verde}) ---")
            print(f"✓ Comando enviado ao ESP32: {green_message}")
            esperando_feedback = True
            feedbacks_recebidos.clear()
            timestamp_comando = time.time()  # Record when command was sent
            print(f"⏳ Aguardando confirmação de todos os semáforos (4/4)...")
        else:
            print(f"✗ Erro ao enviar comando GREEN: {result.rc}")
    except Exception as e:
        print(f"Erro ao publicar mensagem GREEN: {e}")

def publica_mensagem(client, vias_dados):
    """Publish traffic light command via MQTT with forced rotation"""
    global semaforo_escolhido, semaforo_escolhido_anterior
    global ultimo_record_id, estado_anterior, usar_ml, tempo_liberacao
    global esperando_feedback, timestamp_comando, dados_antes_comando, feedbacks_recebidos
    global proximo_semaforo_rotacao_forçada, opened_this_round

    print(f"\n=== CICLO DE DECISÃO ===")

    # Handle no data case
    if vias_dados is None or sum(vias_dados.values()) == 0:
        print(f"⚠️ AVISO: Nenhum dado válido disponível. Usando rotação forçada padrão.")
        semaforo_escolhido = proximo_semaforo_rotacao_forçada
        tempo_liberacao = 10
        estrategia = "FALHA DE DADOS / Rotação"

        current_index = semaforos.index(proximo_semaforo_rotacao_forçada)
        proximo_semaforo_rotacao_forçada = semaforos[(current_index + 1) % len(semaforos)]

        print(f"Decisão ({estrategia}): Semáforo {semaforo_escolhido}, Tempo {tempo_liberacao}s")
        envia_comando_mqtt(client, semaforo_escolhido, tempo_liberacao, estrategia)
        semaforo_escolhido_anterior = semaforo_escolhido

        for s in semaforos:
            if s == semaforo_escolhido:
                last_opened_cycles[s] = 0
            else:
                last_opened_cycles[s] += 1

        opened_this_round.add(semaforo_escolhido)
        if len(opened_this_round) == 4:
            opened_this_round.clear()

        return

    # Decision logic
    estado_anterior = vias_dados.copy()
    dados_antes_comando = vias_dados.copy()
    estrategia = "Regras"
    agora = datetime.now()
    exclude = semaforo_escolhido_anterior

    print(f"Estado atual das vias: {vias_dados}")
    print(f"Ciclos desde última abertura: {last_opened_cycles}")

    # Forced rotation logic
    if len(opened_this_round) == 4:
        opened_this_round.clear()
        print("✓ Rodada completa, reiniciando ciclo de rotação")

    if opened_this_round:
        candidates = [s for s in semaforos if s not in opened_this_round]
        print(f"Forçando rotação: Candidatos restantes {candidates}")
    else:
        candidates = semaforos
        print(f"Rodada completa, escolhendo livremente")

    if usar_ml and ml_controller.is_trained:
        semaforo_ml, tempo_ml = ml_controller.prever_melhor_acao(
            estado_anterior, agora.hour, agora.weekday(), exclude=exclude, candidates=candidates
        )
        if semaforo_ml and tempo_ml:
            semaforo_escolhido = semaforo_ml
            tempo_liberacao = tempo_ml
            estrategia = "ML Adaptativo"
        else:
            semaforo_escolhido, tempo_liberacao = decisao_baseada_regras(estado_anterior, exclude=exclude, candidates=candidates)
            estrategia = "Regras Adaptativas (ML falhou)"
    else:
        semaforo_escolhido, tempo_liberacao = decisao_baseada_regras(estado_anterior, exclude=exclude, candidates=candidates)
        estrategia = "Regras Adaptativas"

    tempo_liberacao = max(5, min(30, int(tempo_liberacao)))

    print(f"\n🚦 Decisão Final ({estrategia}):")
    print(f"   Semáforo: {semaforo_escolhido}")
    print(f"   Tempo: {tempo_liberacao}s")
    print(f"   Carros na via escolhida: {vias_dados[semaforo_escolhido]}")

    # Save training data
    if usar_db_treino:
        agora = datetime.fromtimestamp(time.time())
        dados_treinamento = (
            time.time(),
            estado_anterior.get('A', 0),
            estado_anterior.get('B', 0),
            estado_anterior.get('C', 0),
            estado_anterior.get('D', 0),
            agora.hour,
            agora.weekday(),
            semaforo_escolhido,
            tempo_liberacao,
            sum(estado_anterior.values())
        )
        ultimo_record_id = enviardadospsql(dados_treinamento)

    # Publish command
    envia_comando_mqtt(client, semaforo_escolhido, tempo_liberacao, estrategia)

    # Update state
    semaforo_escolhido_anterior = semaforo_escolhido
    current_index = semaforos.index(semaforo_escolhido)
    proximo_semaforo_rotacao_forçada = semaforos[(current_index + 1) % len(semaforos)]

    for s in semaforos:
        if s == semaforo_escolhido:
            last_opened_cycles[s] = 0
        else:
            last_opened_cycles[s] += 1

    opened_this_round.add(semaforo_escolhido)

def on_connect(client, userdata, flags, rc):
    print(f"\n=== MQTT CONNECTION ===")
    if rc == 0:
        print("✓ Conectado ao broker MQTT")
        client.subscribe(topico_recepcao)
        print(f"✓ Inscrito no tópico: {topico_recepcao}")
    else:
        print(f"✗ Falha na conexão MQTT, código: {rc}")

def on_message(client, userdata, message):
    """Process feedback and only proceed after green duration"""
    global ultimo_record_id, esperando_feedback, dados_antes_comando, feedbacks_recebidos, semaforo_escolhido
    global proximo_semaforo_rotacao_forçada, tempo_liberacao, timestamp_comando

    try:
        payload_str = message.payload.decode().strip()
        print(f"\n=== FEEDBACK ESP32 ===")
        print(f"Mensagem recebida: {payload_str}")

        if not esperando_feedback:
            print(f"⚠ Feedback recebido mas não estava esperando feedback (ignorando)")
            return

        semaforo_confirmado = None
        tempo_confirmado = None

        try:
            dados_json = json.loads(payload_str)
            if isinstance(dados_json, dict) and len(dados_json) == 1:
                semaforo_confirmado = list(dados_json.keys())[0]
                tempo_confirmado = dados_json[semaforo_confirmado]
                print(f"✓ Confirmação do semáforo VERDE: {semaforo_confirmado} ({tempo_confirmado}s)")
        except json.JSONDecodeError:
            if payload_str in ['A', 'B', 'C', 'D']:
                semaforo_confirmado = payload_str
                print(f"✓ Confirmação do semáforo VERMELHO: {semaforo_confirmado}")
            else:
                print(f"⚠ Formato de mensagem não reconhecido: {payload_str}")
                return

        if semaforo_confirmado and semaforo_confirmado in semaforos:
            feedbacks_recebidos.add(semaforo_confirmado)
            print(f"📊 Status: {len(feedbacks_recebidos)}/4 semáforos confirmados {sorted(feedbacks_recebidos)}")

            if len(feedbacks_recebidos) == 4:
                print(f"✅ TODOS OS 4 SEMÁFOROS CONFIRMARAM!")

                # Wait for the green light duration
                time_since_command = time.time() - timestamp_comando
                remaining_time = max(0, tempo_liberacao - time_since_command)
                if remaining_time > 0:
                    print(f"⏳ Aguardando duração restante do verde ({remaining_time:.1f}s)...")
                    time.sleep(remaining_time)

                # Update training data
                if ultimo_record_id and dados_antes_comando:
                    cars_antes_total = sum(dados_antes_comando.values())
                    vias_dados_novos = get_vias_dados()
                    if vias_dados_novos and sum(vias_dados_novos.values()) > 0:
                        cars_depois = sum(vias_dados_novos.values())
                        eficiencia = (cars_antes_total - cars_depois) / max(cars_antes_total, 1)
                        eficiencia = min(max(eficiencia, 0.0), 9.9999)
                        try:
                            conn = psycopg2.connect(**MLDB_CONFIG)
                            cursor = conn.cursor()
                            cursor.execute("""
                                UPDATE ml_training_data
                                SET cars_depois = %s, eficiencia = %s, feedback_recebido = TRUE
                                WHERE id = %s
                            """, (cars_depois, eficiencia, ultimo_record_id))
                            conn.commit()
                            cursor.close()
                            conn.close()

                            print(f"✓ Registro {ultimo_record_id} atualizado:")
                            print(f"  Carros antes: {cars_antes_total}")
                            print(f"  Carros depois: {cars_depois}")
                            print(f"  Eficiência: {eficiencia:.2f}")

                        except Exception as e:
                            print(f"✗ Erro ao atualizar registro: {e}")

                esperando_feedback = False
                feedbacks_recebidos.clear()
                print("✓ Ciclo de feedback completo, pronto para próximo comando")
        else:
            print(f"⚠ Semáforo confirmado inválido: {semaforo_confirmado}")

    except Exception as e:
        print(f"✗ Erro ao processar feedback: {e}")
        traceback.print_exc()

def on_subscribe(client, userdata, mid, granted_qos):
    print(f"✓ Inscrição confirmada com QoS {granted_qos}")

def on_publish(client, userdata, mid):
    pass

# Configurar cliente MQTT
client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
client.on_subscribe = on_subscribe
client.on_publish = on_publish

def inicializar_sistema():
    print("=== INICIALIZANDO SISTEMA DE CONTROLE DE TRÁFEGO ===")
    print("🚀 Versão: ML Adaptativo com Tempo Dinâmico e Rotação Forçada")

    criar_tabela_treinamento()

    try:
        client.connect("192.168.0.9", 1883, 60)
        client.loop_start()
        print("✓ Cliente MQTT iniciado")
    except Exception as e:
        print(f"✗ Erro ao conectar ao broker MQTT: {e}")

    dados_disponiveis = verificar_dados_coletados()
    print(f"=== VERIFICAÇÃO DE TREINAMENTO ===")
    print(f"Dados disponíveis para treinamento: {dados_disponiveis}")

    if dados_disponiveis >= 10:
        print(f"Iniciando treinamento com {dados_disponiveis} registros...")
        sucesso_treinamento = ml_controller.treinar_modelos()
        if sucesso_treinamento:
            global usar_ml
            usar_ml = True
            print("✓ ML Adaptativo ativado!")
            print("  └─ Sistema irá ajustar tempos baseado no fluxo de carros")
        else:
            print("⚠ Falha no treinamento inicial")
    else:
        print(f"⚠ Poucos dados para treinamento: {dados_disponiveis}")
        print("Sistema funcionará com regras adaptativas até coletar mais dados")

    print(f"Status final: usar_ml={usar_ml}, is_trained={ml_controller.is_trained}")
    print("="*50)

# Inicializar sistema
inicializar_sistema()

# Loop principal
print("\n=== INICIANDO LOOP PRINCIPAL ===")
print("💡 Sistema com tempo adaptativo e rotação forçada ativo!")
print("   - Mais carros = Mais tempo verde")
print("   - Menos carros = Menos tempo verde")
print("   - Rotação garante todas as vias abertas por ciclo")
print("="*50)

try:
    while True:
        if not esperando_feedback:
            ciclos_desde_treinamento += 1

            # Small delay to prevent tight looping
            time.sleep(0.5)

            vias_dados = get_vias_dados()
            publica_mensagem(client, vias_dados)

            if not usar_ml and verificar_dados_coletados() >= 10:
                print("\n=== PRIMEIRO TREINAMENTO ===")
                if ml_controller.treinar_modelos():
                    usar_ml = True
                    print("✓ ML Adaptativo ativado!")

            if usar_ml and ciclos_desde_treinamento >= 20:
                print("\n=== RETREINAMENTO ===")
                if ml_controller.treinar_modelos():
                    print("✓ Modelos retreinados com dados mais recentes")
                ciclos_desde_treinamento = 0
        else:
            # Minimal sleep to check for feedback frequently
            time.sleep(0.1)

except KeyboardInterrupt:
    print("\n=== FINALIZANDO SISTEMA ===")
    client.loop_stop()
    client.disconnect()
    print("✓ Sistema finalizado")
except Exception as e:
    print(f"✗ Erro no loop principal: {e}")
    traceback.print_exc()
    client.loop_stop()
    client.disconnect()
