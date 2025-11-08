#include <ArduinoJson.h>
#include <WiFi.h>
#include <PubSubClient.h>

#define ssid "Casa"
#define password "dice0212"

#define ssid1 "SmartWay"
#define password1 "4ipaipara"

const char* mqtt_server1 = "192.168.1.10";

const char* mqtt_server = "192.168.0.9";

const int mqtt_port = 1883;

const char* topico_comando = "3105/comando";
const char* topico_confirmacao = "3105/confirmacao";
const char* topico_acionado = "3105/acionado";

bool led_ligado = false;
//bool amarelo_piscante = false;
int tempo_inicializacao = 0;
int z = 0;
int quant_falha = 0;
int quant_mensagem_falha = 0;
int quant_mensagens = 0;
int tempo_decorrido = 0;
int tempo_inicial = 0;
bool mensagem_recebida = false;
int resultado = 0;
bool falha_mqtt = false;
int tempo_acionado = 0;

WiFiClient espClient;
PubSubClient client(espClient);

//String mensagem;

void setup() {
  Serial.begin(9600);
  #define luz_vermelha 14
  #define luz_amarela 12
  #define luz_verde 13

  pinMode(luz_verde, OUTPUT);
  pinMode(luz_amarela, OUTPUT);
  pinMode(luz_vermelha, OUTPUT);

  digitalWrite(luz_vermelha, 1);
  Serial.println("resultado antes setupwifi");
  Serial.print(resultado);
  setup_wifi();
  Serial.println("resultado depois setupwifi");
  Serial.print(resultado);
  if (resultado == 1){
    Serial.println(mqtt_server);
    client.setServer(mqtt_server, mqtt_port);
  }
  else{
    Serial.println("Chegou aqui");
    Serial.println(mqtt_server1);
    client.setServer(mqtt_server1, mqtt_port);
  }
  client.setCallback(callback);
}

void loop() {
  if (z == 0){
    tempo_inicializacao = millis();
    z += 1;
  } else {
    tempo_decorrido = millis() - tempo_inicializacao;
  }

  if(!client.connected()){
    //digitalWrite(luz_vermelha, 0);
    while (WiFi.status() != WL_CONNECTED){
      setup_wifi();
    }
    reconnect();
  }

  Serial.println(round((millis() - tempo_acionado) / 1000));
  falha_mqtt = false;
  if(tempo_decorrido - tempo_inicial > 30000){
    modo_automatico();
  }
  client.loop();

  /*Serial.print("Tempo decorrido: ");
  Serial.println(tempo_decorrido);
  Serial.print("Tempo inicial: ");
  Serial.println(tempo_inicial);
  Serial.print("Tempo que não chega uma mensagem: ");
  Serial.println(tempo_decorrido - tempo_inicial);*/
}

void modo_automatico(){
  tempo_decorrido = millis() - tempo_inicializacao;

  if(tempo_decorrido - tempo_inicial > 30000){
    Serial.println("Uma nova mensagem não chegou no tempo esperado. (1)");
    quant_mensagem_falha += 1;
  }

  //Serial.println(millis());

  if (quant_mensagem_falha == 1 || (falha_mqtt == true && (int(round((millis() - tempo_acionado) / 1000)) % 30 == 0 || int(round((millis() - tempo_acionado) / 1000)) % 31 == 0 || int(round((millis() - tempo_acionado)/ 1000)) % 32 == 0 || int(round((millis() - tempo_acionado) / 1000)) % 33 == 0)) || (falha_mqtt == false && (int(round((millis() - tempo_acionado) / 1000)) % 30 == 0))){
    tempo_acionado = millis();

    int x = 0;
    while (x < 2) {
      client.loop();
      if (tempo_decorrido - tempo_inicial > 30000){
        client.publish(topico_confirmacao, "C");
        delay(5000);
        quant_mensagem_falha = 0;
        x += 1;
      } else {
        break;
      }
    }
    if (tempo_decorrido - tempo_inicial > 30000){
      Serial.println("Uma nova mensagem não chegou no tempo esperado. (2)");
      luzes_semaforo(5);
      client.publish(topico_confirmacao, "C");
      client.loop();

      if (tempo_decorrido - tempo_inicial > 30000){
          delay(5000);
          client.publish( topico_confirmacao, "C");
          client.loop();
          quant_mensagem_falha = 0;
      }
    }
  }

}

void reconnect() {
  //int tentativa = 0;
  while (!client.connected()) {
    while (WiFi.status() != WL_CONNECTED){
      setup_wifi();
    }
    Serial.println("Tentando conexão MQTT...");
    if (client.connect("SemaforoC_ESP")) {
      Serial.println("conectado");
      client.subscribe(topico_comando);
      Serial.print("Inscrito no tópico: ");
      Serial.println(topico_comando);
      quant_falha = 0;
      client.publish(topico_confirmacao, "C");

    } else {
      Serial.print("Falha na conexão. Estado: ");
      Serial.print(client.state());
      Serial.println(" Tentando novamente em 5 segundos");
      quant_falha += 1;
      if (quant_falha <= 2){
        digitalWrite(luz_vermelha, 1);
        delay(5000);
      } else {
        amarelo_piscante(3);
      } /*else {
        falha_mqtt = true;
        Serial.println(millis());
        Serial.println(round((millis() - tempo_acionado) / 1000));
        modo_automatico();
      }*/
    }
  }
  digitalWrite(luz_vermelha, 1);
  quant_falha = 0;
  //tentativa += 1;
}

void luzes_semaforo(float tempo_calculado){
  digitalWrite(luz_vermelha, 0);
  digitalWrite(luz_amarela, 0);

  digitalWrite(luz_verde, 1);
  float tempo = (tempo_calculado - 1) * 1000;
  delay(tempo);
  digitalWrite(luz_verde, 0);
  digitalWrite(luz_amarela, 1);
  delay(1000);
  digitalWrite(luz_amarela, 0);
  digitalWrite(luz_vermelha, 1);
}

void amarelo_piscante(int quant_repet){
  digitalWrite(luz_verde, 0);
  digitalWrite(luz_vermelha, 0);

  int quant_pisca = 0;

  while (quant_pisca <= quant_repet){
  digitalWrite(luz_amarela, 1);
  delay(1000);
  digitalWrite(luz_amarela, 0);
  delay(1000);
  quant_pisca += 1;
  }
}

void setup_wifi() {
  delay(10);
  Serial.println();
  Serial.print("Conectando-se a ");

  if (resultado == 0) {
    Serial.println(ssid);
    WiFi.config(IPAddress(192,168,1,30), IPAddress(192,168,1,1), IPAddress(255,255,255,0));
    WiFi.begin(ssid, password);
    Serial.println("resultado if == 0");
    Serial.print(resultado);
  } else {
    Serial.println(ssid1);
    WiFi.config(IPAddress(192,168,0,13), IPAddress(192,168,0,1), IPAddress(255,255,224,0));
    WiFi.begin(ssid1, password1);
    Serial.println("resultado else");
    Serial.print(resultado);
  }

  int tempo_reconexao = 0;
  digitalWrite(luz_vermelha, 0);

  while (WiFi.status() != WL_CONNECTED && tempo_reconexao <= 20) {
    if (led_ligado == false){
      digitalWrite(luz_amarela, 1);
      led_ligado = true;
    } else {
      digitalWrite(luz_amarela, 0);
      led_ligado = false;
    }
    delay(500);
    Serial.print(".");
    tempo_reconexao += 1;
  }
  Serial.println("resultado antes if wifistatus");
  Serial.print(resultado);
  if (WiFi.status() != WL_CONNECTED) {
    resultado = 1 - resultado; // alterna entre 0 e 1 para tentar outra rede na próxima vez
  }

  digitalWrite(luz_amarela, 0);
  digitalWrite(luz_vermelha, 0);

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("");
    Serial.println("WiFi conectado");
    Serial.print("Endereço IP: ");
    Serial.println(WiFi.localIP());
    digitalWrite(luz_vermelha, 1);
    delay(5000);
  } else {
    Serial.println("");
    Serial.println("Falha ao conectar WiFi");
    digitalWrite(luz_vermelha, 0);
    amarelo_piscante(3);
  }
}

void callback(char* topic, byte* payload, unsigned int length) {
  tempo_inicial = millis() - tempo_inicializacao;

  quant_mensagens += 1;

  mensagem_recebida = false;

  Serial.print("Mensagem recebida no tópico: ");
  Serial.println(topic);

  //client.publish(topico_confirmacao, "C");

  //Serial.println(payload)
  String mensagem;
  String mensagem1;

  for (int i = 0; i < length; i++) {
    mensagem1 += (char)payload[i];
  }

  Serial.print("Essa mensagem é a original: ");
  Serial.println(mensagem1);
  
  if (mensagem1.indexOf("irmacaoCV\"") != -1) {
    Serial.println("Encontrado!");
    mensagem1.replace("irmacaoCV", "{\"A\": {\"V");
    mensagem = mensagem1; 
  }
  
  if (mensagem1.indexOf("irmacaoC\"") != -1) {
    Serial.println("Encontrado!");
    // substitui "irmacaoB\"" por {"A": "L"
    mensagem1.replace("irmacaoC\"", "{\"A\": \"L\"");
    mensagem = mensagem1;
  } else{
    mensagem = mensagem1;
  }

  Serial.print("Mensagem: ");
  Serial.println(mensagem);

  JsonDocument doc;
  deserializeJson(doc, mensagem);

  JsonVariant variant = doc["C"];

  if (variant.is<JsonObject>()) {
    mensagem_recebida = true;

    JsonObject objetoC = variant.as<JsonObject>();

    String chaveInterna = "";
    double valor = 0;

    for (JsonPair kv : objetoC) {
      chaveInterna = kv.key().c_str();
      valor = kv.value().as<double>();
    }

  Serial.println(chaveInterna);
  Serial.println(valor);

  
  if (chaveInterna == "V"){
    String liberacao = "{\"C\": " + String(valor) + "}";
    client.publish(topico_confirmacao, liberacao.c_str());
    luzes_semaforo(valor);
  }

  } else {
    digitalWrite(luz_vermelha, 1);
    client.publish(topico_confirmacao, "C");

  }
}
 