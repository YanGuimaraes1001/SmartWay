#include <ArduinoJson.h>
#include <WiFi.h>
#include <PubSubClient.h>

#define ssid "Casa"
#define password "dice0212"

#define ssid1 "SmartWay"
#define password1 "4ipaipara"

//#define ssid1 "alunos"
//#define password1 "etefmc123"

const char* mqtt_server1 = "192.168.1.10";

const char* mqtt_server = "192.168.0.9";

//const char* mqtt_server = "192.168.15.210";

//const char* mqtt_server2 = "192.168.0.100";

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
int erro_forcado = 0;

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

  setup_wifi();

  if (resultado == 1){
    Serial.println(mqtt_server);
    client.setServer(mqtt_server, mqtt_port);
  }
  else{
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

  //erro_forcado += 1;

  /*if (int(round((millis() - tempo_acionado)/ 1000)) == 30){
    Serial.println(mqtt_server2);
    client.setServer(mqtt_server2, mqtt_port);
    client.disconnect();
  }*/

  //Serial.print()
  Serial.println(round((millis() - tempo_acionado)/ 1000));
  falha_mqtt = false;
  if(tempo_decorrido - tempo_inicial > 30000){
    modo_automatico();
  }
  /*Serial.print("Tempo decorrido: ");
  Serial.println(tempo_decorrido);
  Serial.print("Tempo inicial: ");
  Serial.println(tempo_inicial);
  Serial.print("Tempo que não chega uma mensagem: ");
  Serial.println(tempo_decorrido - tempo_inicial);*/

  client.loop();  
}

void modo_automatico(){
  tempo_decorrido = millis() - tempo_inicializacao;

  if(tempo_decorrido - tempo_inicial > 30000){
    Serial.println("Uma nova mensagem não chegou no tempo esperado. (1)");
    quant_mensagem_falha += 1;
  }

  if (quant_mensagem_falha == 1 || (falha_mqtt == true && (int(round((millis() - tempo_acionado)/ 1000)) % 20 == 0 || int(round((millis() - tempo_acionado) / 1000)) % 21 == 0 || int(round((millis() - tempo_acionado) / 1000)) % 22 == 0 || int(round((millis() - tempo_acionado) / 1000)) % 23 == 0)) || (falha_mqtt == false && (int(round((millis() - tempo_acionado) / 1000)) % 20 == 0))){
    tempo_acionado = millis();
    client.publish(topico_confirmacao, "A");
    luzes_semaforo(5);
    quant_mensagem_falha = 0;
    client.loop();

    if (tempo_decorrido - tempo_inicial > 30000){
    //  Serial.println("Uma nova mensagem não chegou no tempo esperado. (2)");
      //quant_mensagem_falha = 1;
      //amarelo_piscante(1);
    //} else {
      int repet = 0;
      while (repet < 3){
        delay(5000);
        client.publish( topico_confirmacao, "A");
        client.loop();
        repet += 1;
        if(tempo_decorrido - tempo_inicial > 30000){
          Serial.println("Uma nova mensagem não chegou no tempo esperado. (3)");
          client.loop();
          //quant_mensagem_falha += 1;
          //amarelo_piscante(1);
        } else {
          quant_mensagem_falha = 0;
          break;
        }
      }
    }
  }
}

void reconnect() {
  //int tentativa = 0;
  while (!client.connected()) {
    /*Serial.print(int(round((millis())/ 1000)));
    if (int(round((millis())/ 1000)) >= 100){
      Serial.println(mqtt_server);
      client.setServer(mqtt_server, mqtt_port);
      client.disconnect();
    }*/

    while (WiFi.status() != WL_CONNECTED){
      setup_wifi();
    }
    Serial.print("Tentando conexão MQTT...");
    if (client.connect("SemaforoA_ESP")) {
      Serial.println("conectado");
      client.subscribe(topico_comando);
      Serial.print("Inscrito no tópico: ");
      Serial.println(topico_comando);
      quant_falha = 0;
      client.publish(topico_confirmacao, "A");

    } else {
      //if (erro_forcado >+ 2 && erro_forcado < 5) {
      //  client.disconnect();
      //} else if (erro_forcado < 2) {
      //  erro_forcado += 1;
      //}//} else {
      //  client.connect("");
      //}

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
        Serial.println(round((millis() - tempo_acionado) / 1000));
        modo_automatico();
      }*/
      amarelo_piscante(3);
    }
    //tentativa += 1;
  }
  quant_falha = 0;
  digitalWrite(luz_vermelha, 1);
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
    WiFi.config(IPAddress(192,168,1,20), IPAddress(192,168,1,1), IPAddress(255,255,255,0));
    WiFi.begin(ssid, password);
  } else {
    Serial.println(ssid1);
    WiFi.config(IPAddress(192,168,0,10), IPAddress(192,168,0,1), IPAddress(255,255,224,0));
    //WiFi.config(IPAddress(192,168,0,211), IPAddress(192,168,15,1), IPAddress(255,255,224,0));
    WiFi.begin(ssid1, password1);
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

  //client.publish(topico_confirmacao, "A");

  //Serial.println(payload)
  String mensagem;
  String mensagem1;

  for (int i = 0; i < length; i++) {
    mensagem1 += (char)payload[i];
  }

  Serial.print("Essa mensagem é a original: ");
  Serial.println(mensagem1);
  
  if (mensagem1.indexOf("irmacao") != -1) {
    // A substring "mundo" foi encontrada
    Serial.println("Encontrado!");
    mensagem1.replace("irmacao", "{\"");
    mensagem = mensagem1; 
  if (mensagem1.indexOf("AV") != -1){
    // A substring "mundo" não foi encontrada
    Serial.println("Não encontrado.");
    mensagem1.replace("\"AV\":", "\"A\": {\"V\":");
    mensagem1.replace(", \"B\"", "}, \"B\"");
    mensagem = mensagem1;
  }} else{
    mensagem = mensagem1;
  }

  Serial.print("Mensagem: ");
  Serial.println(mensagem);

  JsonDocument doc;
  deserializeJson(doc, mensagem);

  JsonVariant variant = doc["A"];

  if (variant.is<JsonObject>()) {
    mensagem_recebida = true;

    JsonObject objetoA = variant.as<JsonObject>();

    String chaveInterna = "";
    double valor = 0;

    for (JsonPair kv : objetoA) {
      chaveInterna = kv.key().c_str();
      valor = kv.value().as<double>();
    }

  Serial.println(chaveInterna);
  Serial.println(valor);

  
  
  if (chaveInterna == "V"){
    String liberacao = "{\"A\": " + String(valor) + "}";
    client.publish(topico_confirmacao, liberacao.c_str());
    luzes_semaforo(valor);
  }

  } else {
    digitalWrite(luz_vermelha, 1);
    client.publish(topico_confirmacao, "A");
  }
}
 