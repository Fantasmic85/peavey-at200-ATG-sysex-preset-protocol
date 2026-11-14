/*
ATGMiniController


*/

#include <avr/sleep.h>
#include "SSD1306Ascii.h"
#include "SSD1306AsciiAvrI2c.h"
#include <EEPROM.h>

// Endereços base da memória EEPROM
const int ADDR_CONFIG  = 0;
const int ADDR_PATCHES = 32;   // 0x020
const int ADDR_GROUPS  = 672;  // 32 + (64 * 10) = 672

// 0X3C+SA0 - 0x3C or 0x3D
#define I2C_ADDRESS 0x3C

SSD1306AsciiAvrI2c oled;

#define S1pin 2     // UP
#define S2pin 3     // Down
#define S3pin 4     // Right
#define S4pin 5     // Left
#define S5pin 7     // Cancel
#define S6pin 6     // Ok
#define Bat A0      // BAT level (voltage divider. Calibrate for your case)
#define Fx A1       // Expression poedal wiper (Voltage divider mode V+ W 0V)
                    // MIDI signal to TX

enum swIndex {
  UP,    // 0 Left
  DN,    // 1 Down
  RG,    // 2 Up
  LF,    // 3 Right
  CL,    // 7 Cancel
  OK     // 8 Ok
};

// MAPEAMENTO DE HARDWARE EM VETORES
const uint8_t NUM_BOTOES = 6;
const uint8_t btPin[NUM_BOTOES] = {S1pin, S2pin, S3pin, S4pin, S5pin, S6pin};

/*

              UP
                                Ok
        LF          RG  
                                CL
              DN


*/



// =============================================================================
struct Parametro {
  char nome[7];       // Nome a mostrar no cabeçalho do OLED (ex: "Capo  ")
  byte cc;            // Número do MIDI CC
  byte maxVal;        // Valor máximo do cursor (0 até maxVal)
  int8_t dispOffset;  // O que subtrair para mostrar no ecrã (se for numérico)
  byte midiOffset;    // O que somar para o byte MIDI real (0 a 127)
  byte val;           // O valor ativo atual em RAM
};

// =============================================================================
// 2. LISTAS DE TEXTO DEDICADAS (Substitutas do antigo Men2S2)
// =============================================================================

// Afinações alternativas (13 opções)
const char listaTunings[13][7] = {
  "Stand ", "Custom", "Bass  ", "DropD ", "2DropD", 
  "DADGAD", "Open G", "Open D", "Open E", "Open A", 
  "Open e", "Open d", "Open a"
};

// Modelos de Guitarras / Captadores modelados (11 opções)
const char listaModels[11][7] = {
  "Mod HB", "Vin HB", "MiniHB", "SBar  ", "CS HSH",
  "Nas SC", "Cal SC", "LStick", "Acstic", "Bass  ", 
  "Jp HSH"
};

// Seletor de Captadores Virtuais (5 opções)
const char listaPickups[5][7] = {
  "Neck  ", "N + M ", "Middle", "M + B ", "Bridge"
};

// Duplicações / Oitavações / Harmonizações (10 opções)
const char listaDoubles[10][7] = {
  "None  ", "8 Down", "8 Up  ", "4 Up  ", "5 Up  ", 
  "7Str  ", "7Str2 ", "12Str ", "12Str2", "Custom"
};

// Transposição Direta Global / DTrnsp (8 opções com nomes reais em vez de números!)
const char listaDTrnsp[8][7] = {
  "Stand ", "-1 Eb ", "-2 D  ", "-3 C# ", 
  "-4 C  ", "-5 B  ", "-1 Oct", "+1 Oct"
};

// Curvas de Pitch-Shift do Pedal de Expressão / Whammy (4 opções)


// Endereço da calibração nos 32 bytes de configuração inicial
const int ADDR_CALIB = ADDR_CONFIG + 4; // Ocupa 4 bytes (2 ints de 16 bits)

struct CalibPedal {
  int minRaw;
  int maxRaw;
};

// Variáveis ativas em RAM (com valores padrão seguros de contingência)
int potMinRaw = 30;
int potMaxRaw = 990;


// =============================================================================
// 3. DEFINIÇÃO DOS SUBMENUS COM A NOVA ORDEM ERGONÓMICA
// =============================================================================

// --- MENU CONF (7 parâmetros) ---
// Capo em 1º lugar, Solid-Tune empurrado para último!
Parametro menuConf[] = {
  // Nome     CC   maxVal DispOfs  MidiOfs    Val
  { "Capo  ", 11,  24,    12,      52,        12 }, // Posição 0: Capo (-12 a +12)
  { "Tuning",  7,  12,     0,       0,         0 }, // Posição 1: Afinações
  { "GModel", 14,  10,     0,       0,         0 }, // Posição 2: Modelos de Guitarra
  { "Pickup", 22,   4,     0,       0,         4 }, // Posição 3: Pickups (Inicia na Ponte)
  { "Double", 27,   9,     0,       0,         0 }, // Posição 4: 12-Cordas / Oitavas
  { "Gate  ", 25,  22,     0,       0,         0 }, // Posição 5: Noise Gate
  { "STune ",  3,   1,     0,       0,         0 }  // Posição 6: Solid-Tune (On/Off)
};
const byte TOTAL_CONF = sizeof(menuConf) / sizeof(menuConf[0]);

// --- MENU GLOBAL (10 parâmetros) ---
// Transpose e Boost no topo; calibrações de estúdio para o fim!
Parametro menuGlobal[] = {
  // Nome     CC   maxVal DispOfs  MidiOfs    Val
  { "DTrnsp", 28,   7,     0,       0,         0 }, // Posição 0: Drop Transpose direto
  { "Boost ", 18, 127,     0,       0,        64 }, // Posição 1: Volume Master
  { "TOfset",  8,  19,     7,      57,         7 }, // Posição 2: Desvio Lá 440Hz (-7 a +12)
  { "DTune ", 19, 127,    63,       0,        63 }, // Posição 3: Microafinação (-63 a +64)
  { "E3Gain", 29,  12,     6,      58,         6 }, // Posição 4: Ganho Corda 1 (Mi agudo)
  { "B2Gain", 30,  12,     6,      58,         6 }, // Posição 5: Ganho Corda 2 (Si)
  { "G2Gain", 31,  12,     6,      58,         6 }, // Posição 6: Ganho Corda 3 (Sol)
  { "D2Gain", 32,  12,     6,      58,         6 }, // Posição 7: Ganho Corda 4 (Ré)
  { "A1Gain", 33,  12,     6,      58,         6 }, // Posição 8: Ganho Corda 5 (Lá)
  { "E1Gain", 34,  12,     6,      58,         6 }  // Posição 9: Ganho Corda 6 (Mi grave)
};
const byte TOTAL_GLOBAL = sizeof(menuGlobal) / sizeof(menuGlobal[0]);

// --- MENU EXPRESSÃO / XP (5 parâmetros) ---
Parametro menuXp[] = {
  // Nome     CC   maxVal DispOfs  MidiOfs    Val
  { "FxPed ",  0,   1,     0,       0,         0 }, // 0: Pedal Off (0) / On (1)
  { "Modo  ",  0,   2,     0,       0,         0 }, // 1: 0=Whammy, 1=Capo, 2=Detune
  { "ShiftC", 20,   3,     0,       0,         0 }, // 2: Curva de Whammy (0 a 3)
  { "Min   ",  0, 127,     0,       0,         0 }, // 3: Calcanhar (0 a 127)
  { "Max   ",  0, 127,     0,       0,       127 }  // 4: Ponta do Pé (0 a 127)
};
const byte TOTAL_XP = sizeof(menuXp) / sizeof(menuXp[0]);

// Os 3 Modos reais e os respetivos códigos MIDI CC
const char listaXpModo[3][7] = { "Whammy", "Capo  ", "Detune" };
const byte ccXpModo[3]        = { 20,       11,       19       };

// Curvas de Whammy da Antares (usadas quando Modo == Whammy)
const char listaShiftC[4][7] = { "0 > 8 ", "0 > -8", "-8 > 8", "-1 > 1" };

// Variáveis de controlo do pedal de expressão (anti-ruído e taxa de envio)
int lastFxVal = -1;              // Último valor MIDI enviado (-1 para forçar primeiro envio)
unsigned long timerLeituraFx = 0; // Taxa de amostragem

// --- VARIÁVEIS ---
uint8_t btSt[NUM_BOTOES] =  {0};
uint8_t btFunc[NUM_BOTOES] = {0};

int8_t curGroup = 0; // Grupo actualmente selecionado
int8_t curPreset = 0; // Preset actualmente carregado
uint8_t grPresets[4] =  {0};

int8_t subMenu = 10; // Nível dos menus

int BLev;
int8_t BLev2;
boolean Lbat = 0;
boolean RefLCD = 0;
int8_t M1 = 0;
//int8_t M2 = 0;

void setup() {

  Serial.begin(31250);

  oled.begin(&Adafruit128x32, I2C_ADDRESS);
  oled.setFont(Verdana12_bold);

  for (uint8_t i = 0; i < NUM_BOTOES; i++) {
    pinMode (btPin[i], INPUT_PULLUP);
  }

  
  pinMode (DN, INPUT_PULLUP);
  pinMode (RG, INPUT_PULLUP);
  pinMode (LF, INPUT_PULLUP);
  pinMode (CL, INPUT_PULLUP);
  pinMode (OK, INPUT_PULLUP);

  pinMode(Bat, INPUT);
  pinMode(Fx, INPUT);


  oled.clear();
  oled.setCursor(28, 1);
  oled.println("POWER ON");
  delay(500);

  oled.clear();
  oled.setCursor(28, 1);
  oled.print("Bat ");

  BLev = analogRead(Bat);

  BLev2 = map(BLev, 555, 630, 0, 100);
  if (BLev > 630)BLev2 = 100;
  if (BLev < 555)BLev2 = 0;

  //oled.print(BLev);

  oled.print(BLev2);
  oled.print(" %");

  // --- MODO DE CALIBRAÇÃO (Se ligar a caixa com o OK premido) ---
  if (digitalRead(btPin[OK]) == LOW) {
    calibrarPedal();
  }

  // Carrega os valores calibrados da EEPROM (se existirem)
  CalibPedal cal;
  EEPROM.get(ADDR_CALIB, cal);
  // Se a memória for válida (amplitude mínima de 150), aplica:
  if (abs(cal.maxRaw - cal.minRaw) >= 150 && abs(cal.maxRaw - cal.minRaw) <= 1023) {
    potMinRaw = cal.minRaw;
    potMaxRaw = cal.maxRaw;
  }

  // JANELA DE ESCUTA durante 2000
  
  unsigned long tempoLimite = millis() + 2000;
  boolean entrarSync = false;

  while (millis() < tempoLimite) {
    if (Serial.available()) {
      // Se a app mandar o byte mágico 0x55 (ou 'S')
      if (Serial.read() == 0x55) { 
        entrarSync = true;
        //break; // Sai do temporizador imediatamente!
      }
    }
  }

  // SE DETETOU O PC: Fica preso no Modo Sync antes de ir para o loop!
  if (entrarSync) {
    ModoSync();
  }

  // carregar o patch default
  curPreset = EEPROM.read(1); // 0x01 é endereço do StandardPreset
  patch (curPreset);

  // carregar o primeiro grupo
  getGroupPresets(0, grPresets); // Inicia no primeiro grupo

  oled.clear();
  oled.ssd1306WriteCmd(SSD1306_DISPLAYOFF);

}

void loop() {

  Readbt();

  dirBtns();
  okclBtns();

  // Processa o pedal de expressão em segundo plano
  tratarPedalExpressao();

}


void Readbt() {
  for (uint8_t i = 0; i < NUM_BOTOES; i++) {
    btFunc[i] = 0; // Reset
    btSt[i] = digitalRead(btPin[i]);
    if(!btSt[i]) btFunc[i] = checkBtn(btPin[i]);
  }
}

byte checkBtn(byte pin) {
  // 1. Filtro anti-ruído mecânico rápido (Debounce de 25ms)
  delay(100);
  if (digitalRead(pin) != LOW) return 0; // Foi só ruído

  unsigned long t0 = millis();

  // 3. Monitoriza enquanto estiver pressionado
  while (digitalRead(pin) == LOW) {
    if (millis() - t0 >= 700) { // 700ms é o "doce" para Hold
      
      visualFeedbackHold(pin); 
      
      while (digitalRead(pin) == LOW); 
      delay(50); // Debounce ao soltar
      return 2;  // RETORNA HOLD
    }    
  }

  delay(50); // Debounce ao soltar
  return 1;   // RETORNA TOQUE CURTO
}

void dirBtns() { // Carregar o preset respectivo e mostrar as informações no LCD
  for (uint8_t i = 0; i < NUM_BOTOES - 2; i++) { // Só os botões direccionais
    
    char nomeP[11];
    char nomeG[11];
    
    if(btFunc[i] == 1){

      curPreset = grPresets[i];      
      
      patch (curPreset);
      
      getPatchName(curPreset, nomeP);      // Lê nome do preset da EEPROM
      getGroupName(curGroup, nomeG);    // Lê nome do grupo da EEPROM

      visualDispararPreset(nomeG, nomeP);

    }

    if(btFunc[i] == 2){ // Fazer assign do patch corrente ao botão e ao grupo
            
      if (curGroup >= 10 || curPreset >= 64) return;

      int endAtalho = ADDR_GROUPS + (curGroup * 14) + 10 + i;
      EEPROM.update(endAtalho, curPreset);
 
      getPatchName(curPreset, nomeP);      // Lê nome do preset da EEPROM
      getGroupName(curGroup, nomeG);    // Lê nome do grupo da EEPROM

      visualDispararPreset(nomeG, nomeP);
      
    }

  }
}

void okclBtns() { // Group + / -

  if(btFunc[OK] == 1){

    curGroup = curGroup + 1;
    if(curGroup > 9)curGroup = 0; // Overflow / lista circular

    // carregar o grupo
    getGroupPresets(curGroup, grPresets);

    char nomeG[11];
    getGroupName(curGroup, nomeG);    // Lê nome do grupo da EEPROM

    visualMudarGrupo(curGroup, nomeG);

  }

  if(btFunc[CL] == 1){ // Fazer assign do patch corrente ao botão e ao grupo
          
    curGroup = curGroup - 1;
    if(curGroup < 0)curGroup = 9; // Overflow / lista circular

    // carregar o grupo
    getGroupPresets(curGroup, grPresets);

    char nomeG[11];
    getGroupName(curGroup, nomeG);    // Lê nome do grupo da EEPROM

    visualMudarGrupo(curGroup, nomeG);
    
  }

  if(btFunc[OK] == 2){ // Entrar no Menu

    Menu1();

  }

  if(btFunc[CL] == 2){ // CArregar o Patch Standard

    // carregar o patch default
    curPreset = EEPROM.read(1); // 0x01 é endereço do StandardPreset
    patch (curPreset);
    
  }
  
}

void Menu1() {

  oled.ssd1306WriteCmd(SSD1306_DISPLAYON); // <-- Acorda o OLED ao entrar
  subMenu = 9;
  RefLCD = 1; // Garante que o menu se desenha logo à primeira

  while (subMenu < 10) {

    Readbt();

    if (btFunc[UP] == 1) {
      M1 = M1 - 1;
      RefLCD = 1;
    }
    if (btFunc[DN] == 1) {
      M1 = M1 + 1;
      RefLCD = 1;
    }

    // --- SETA ESQUERDA (Diminuir Valor) ---
    if (btFunc[LF] == 1) {
      RefLCD = 1;
      if (subMenu == 0) { // Conf
        if (menuConf[M1].val == 0) menuConf[M1].val = menuConf[M1].maxVal; // Wrap circular
        else menuConf[M1].val--;
      }
      else if (subMenu == 1) { // Global
        if (menuGlobal[M1].val == 0) menuGlobal[M1].val = menuGlobal[M1].maxVal;
        else menuGlobal[M1].val--;
      }
      else if (subMenu == 4) {
        if (menuXp[M1].val == 0) menuXp[M1].val = menuXp[M1].maxVal;
        else menuXp[M1].val--;
      }
      else{
        M1 = M1 - 10;
      }
    }

    // --- SETA DIREITA (Aumentar Valor) ---
    if (btFunc[RG] == 1) {
      RefLCD = 1;
      if (subMenu == 0) { // Conf
        if (menuConf[M1].val >= menuConf[M1].maxVal) menuConf[M1].val = 0; // Wrap circular
        else menuConf[M1].val++;
      }
      else if (subMenu == 1) { // Global
        if (menuGlobal[M1].val >= menuGlobal[M1].maxVal) menuGlobal[M1].val = 0;
        else menuGlobal[M1].val++;
      }
      else if (subMenu == 4) {
        if (menuXp[M1].val >= menuXp[M1].maxVal) menuXp[M1].val = 0;
        else menuXp[M1].val++;
      }
      else{
        M1 = M1 + 10;
      }
    }

    // --- BOTÃO OK (Confirmar / Enviar MIDI / Entrar) ---
    if (btFunc[OK] == 1) {
      RefLCD = 1;
      switch (subMenu) {
        case 0:
          // Envia o parâmetro selecionado no menu Conf
          Serial.println("val");
          enviarParametro(menuConf[M1]);
          break;

        case 1:
          // Envia o parâmetro selecionado no menu Global
          enviarParametro(menuGlobal[M1]);
          break;

        case 2: // Call Patch
          M1 = constrain(M1, 0, 63);
          curPreset = M1;
          patch(curPreset);
          subMenu = 10; // Sai do menu e volta ao palco
          break;

        case 3: // Save Patch
          M1 = constrain(M1, 0, 63);
          controller(23, M1); // CC 23 queima o estado atual no Slot M1 da guitarra
          subMenu = 10; // Sai do menu e volta ao palco
          break;

        case 4: // Xp
          enviarParametro(menuXp[M1]);
          break;

        case 9: // Menu Principal -> Entra no submenu escolhido
          M1 = constrain(M1, 0, 4);
          subMenu = M1; // subMenu passa a 0 (Conf), 1 (Global), 2 (Call), 3 (Save) ou 4 (Xp)
          M1 = 0;       // Faz reset ao cursor para começar no primeiro item do submenu!
          break;
      }
    }

    if (btFunc[OK] == 2) btFunc[OK] = 0;

    if (RefLCD == 1) {

      char nomeP[11];

      switch (subMenu) {
        case 0:
          M1 = constrain(M1, 0, TOTAL_CONF - 1);
          // M2 =  constrain(M2, 0, menuConf[M1].maxVal);
          // menuConf[M1].val = M2;
          desenharMenuConf(M1);
          break;
        case 1:        
          M1 = constrain(M1, 0, TOTAL_GLOBAL - 1);
          // M2 =  constrain(M2, 0, menuConf[M1].maxVal);
          // menuConf[M1].val = M2;
          desenharMenuGlobal(M1);
          break;
        case 2:
          M1 = constrain(M1, 0, 63);
          oled.clear();
          oled.print("Call Preset ");
          oled.print(M1);
          oled.setCursor(0, 2);
          //char nomeP[11];
          getPatchName(M1, nomeP); // Lê nome do preset da EEPROM
          oled.print(nomeP);
          break;
        case 3:
          M1 = constrain(M1, 0, 63);
          oled.clear();
          oled.print("Save Preset ");
          oled.print(M1);
          oled.setCursor(0, 2);
          //char nomeP[11];
          getPatchName(M1, nomeP); // Lê nome do preset da EEPROM
          oled.print(nomeP);
          break;
        case 4:
          desenharMenuXp(M1);
          break;
        case 9:
          M1 = constrain(M1, 0, 4);
          desenharMenu(M1);
          break;
      }
      //delay(75);
      RefLCD = 0;
    }

    if (btFunc[CL] == 1) {
      switch (subMenu) {
        case 9:
          subMenu = 10;
          RefLCD = 1;
          break;
        default: subMenu = 9; RefLCD = 1;
      }
    }

    if (btFunc[CL] == 2) btFunc[CL] = 0;

  }// While end

  // --- SAÍDA DO MENU / ADORMECER OLED ---
  oled.clear();
  oled.setCursor(0, 0); oled.print(F("STAGE MODE"));
  delay(800); // Breve aviso visual antes de apagar

  oled.clear();
  oled.ssd1306WriteCmd(SSD1306_DISPLAYOFF); // Desliga a alta tensão (0 mA)

}

// -----------------------------------------------------------------------------
// Exibição do Menu
// -----------------------------------------------------------------------------
void desenharMenu(byte index) {
    
  oled.clear();
  oled.println(F("MENU"));
  oled.print("> ");

  switch (index) {
    case 0:
      oled.print(F("Conf"));
      break;
    case 1:
      oled.print(F("Global"));
      break;
    case 2:
      oled.print(F("Call Preset"));      
      break;
    case 3:
      oled.print(F("Save Preset"));
      break;
    case 4:
      oled.print(F("Xp"));
      break;

  }


}


// -----------------------------------------------------------------------------
// Exibição do Menu CONF
// -----------------------------------------------------------------------------
void desenharMenuConf(byte index) {
  Parametro &p = menuConf[index];
  
  oled.clear();
  oled.println(p.nome);
  oled.print(F("> "));

  switch (index) {
    case 0: // Capo: mostra o valor relativo (-12 a +12)
      oled.print(p.val - p.dispOffset);
      break;

    case 1: // Tuning
      oled.print(listaTunings[p.val]);
      break;

    case 2: // GModel
      oled.print(listaModels[p.val]);
      break;

    case 3: // Pickup
      oled.print(listaPickups[p.val]);
      break;

    case 4: // Double
      oled.print(listaDoubles[p.val]);
      break;

    case 5: // Gate
      oled.print(F("TH "));
      oled.print(p.val);
      break;

    case 6: // Solid-Tune
      oled.print(p.val == 0 ? F("On") : F("Off"));
      break;
  }
}

// -----------------------------------------------------------------------------
// Exibição do Menu GLOBAL
// -----------------------------------------------------------------------------
void desenharMenuGlobal(byte index) {
  Parametro &p = menuGlobal[index];
  
  oled.clear();
  oled.println(p.nome);
  oled.print(F("> "));

  switch (index) {
    case 0: // Drop Transpose direto
      oled.print(listaDTrnsp[p.val]);
      break;

    case 1: { // Boost: Mostra em Decibéis (-12 dB a +12 dB)
      int db = map(p.val, 0, 127, -12, 12);
      if (db > 0) oled.print(F("+"));
      oled.print(db);
      oled.print(F(" dB"));
      break;
    }

    case 2: { // Tone Offset: Mostra em Hertz reais (ex: 440 Hz)
      int hz = 440 + (p.val - p.dispOffset);
      oled.print(hz);
      oled.print(F(" Hz"));
      break;
    }

    case 3: { // Detune: Mostra em Cents (ex: +12 c)
      int cents = p.val - p.dispOffset;
      if (cents > 0) oled.print(F("+"));
      oled.print(cents);
      oled.print(F(" c"));
      break;
    }

    default: { // Casos 4 a 9 (Ganhos individuais dos piezos)
      int ganhoCorda = p.val - p.dispOffset;
      if (ganhoCorda > 0) oled.print(F("+"));
      oled.print(ganhoCorda);
      oled.print(F(" dB"));
      break;
    }
  }
}

// -----------------------------------------------------------------------------
// Exibição do Menu XP
// -----------------------------------------------------------------------------
void desenharMenuXp(byte index) {
  Parametro &p = menuXp[index];

  oled.clear();
  oled.println(p.nome);
  oled.print(F("> "));

  switch (index) {
    case 0: // FxPed: On / Off
      oled.print(p.val == 1 ? F("On") : F("Off"));
      break;

    case 1: // Modo: Whammy, Capo ou Detune
      oled.print(listaXpModo[p.val]);
      break;

    case 2: // ShiftC: Mostra a curva selecionada
      oled.print(listaShiftC[p.val]);
      break;

    case 3: // Min (Calcanhar)
    case 4: // Max (Ponta)
      oled.print(p.val);
      break;
  }
}


void enviarParametro(Parametro &p) { // acho que preciso de indicar um índice nesta função para indicar a linha da matriz
  byte valorMIDI = p.val + p.midiOffset;
  Serial.println(p.val);
  Serial.println(p.midiOffset);
  Serial.println(valorMIDI);
  controller(p.cc, valorMIDI);
}

void patch (byte instrument) {
  Serial.write(0xC0);
  Serial.write(instrument);
}

void controller (byte function, byte value) {
  Serial.write(0xB0);
  Serial.write(function);
  Serial.write(value);
  delay(100);
}

// -----------------------------------------------------------------------------
// Função auxiliar de leitura com Timeout (evita bloqueios infinitos se o cabo falhar)
// -----------------------------------------------------------------------------
int readSerialTimeout(unsigned long timeoutMs = 1000) {
  unsigned long start = millis();
  while (!Serial.available()) {
    if (millis() - start > timeoutMs) return -1; // Erro de timeout
  }
  return Serial.read();
}

// -----------------------------------------------------------------------------
// MODO SYNC / SERVIÇO PC
// -----------------------------------------------------------------------------
void ModoSync() {
  oled.ssd1306WriteCmd(SSD1306_DISPLAYON);
  oled.clear();
  oled.setCursor(0, 0); oled.print(F("PC LINK"));
  oled.setCursor(0, 2); oled.print(F("CL: Exit"));

  // Fica bloqueado neste ciclo até o utilizador pressionar o botão CL (Cancelar)
  while (digitalRead(btPin[CL]) == HIGH) {

    if (Serial.available()) {
      byte b = Serial.read();

      // CASO 1: CABEÇALHO 0xEE -> INÍCIO DA SINCRONIZAÇÃO DA EEPROM
      if (b == 0xEE) {
        oled.clear();
        oled.setCursor(0, 0); oled.print(F("WRITING EEPROM"));
        oled.setCursor(0, 2); oled.print(F("Please wait..."));

        boolean erroSync = false;

        // 1. Gravar os 640 bytes dos nomes dos Patches
        for (int i = 0; i < 640; i++) {
          int dado = readSerialTimeout(1000);
          if (dado < 0) { erroSync = true; break; }
          EEPROM.update(ADDR_PATCHES + i, (byte)dado);
        }

        // 2. Gravar os 140 bytes dos 10 Grupos
        if (!erroSync) {
          for (int i = 0; i < 140; i++) {
            int dado = readSerialTimeout(1000);
            if (dado < 0) { erroSync = true; break; }
            EEPROM.update(ADDR_GROUPS + i, (byte)dado);
          }
        }

        // 3. Gravar o Default / Panic Preset (no endereço 1)
        if (!erroSync) {
          int defPreset = readSerialTimeout(1000);
          if (defPreset < 0) {
            erroSync = true;
          } else {
            EEPROM.update(ADDR_CONFIG + 1, (byte)defPreset);
            // Grava a assinatura mágica no byte 0 para validar a memória
            EEPROM.update(ADDR_CONFIG, 0xA5);
          }
        }

        // Feedback no ecrã OLED
        oled.clear();
        if (erroSync) {
          oled.setCursor(0, 0); oled.print(F("! SYNC ERROR !"));
          oled.setCursor(0, 2); oled.print(F("Data Timeout"));
        } else {
          oled.setCursor(0, 0); oled.print(F("EEPROM SYNC OK"));
          oled.setCursor(0, 2); oled.print(F("Ready to Play!"));
        }
        
        delay(2000);
        oled.clear();
        oled.setCursor(0, 0); oled.print(F("PC LINK"));
        oled.setCursor(0, 2); oled.print(F("CL: Exit"));
      }
        // 2. Comando 0xED: Atualizar 1 único nome (12 bytes: 0xED, Slot, 10 bytes texto)
      else if (b == 0xED) {
        if (Serial.available() >= 12) {
            Serial.read(); // Descarta o 0xED
            byte slot = Serial.read(); // Lê o número do slot (0 a 63)
            
            // Cada nome ocupa 10 bytes na EEPROM (endereço = slot * 10)
            int eepromAddr = slot * 10;
            for (int i = 0; i < 10; i++) {
                byte c = Serial.read();
                EEPROM.update(eepromAddr + i, c);
            }            
        }
      }
      // CASO 3: COMANDOS MIDI NORMAIS (Audition em tempo real ou Flash da Guitarra)
      else {
        // Retransmite imediatamente para o TX da guitarra!
        Serial.write(b);
      }
    }
  }

  // Ao premir o botão CL para sair do modo PC:
  oled.clear();
  oled.setCursor(0, 0); oled.print(F("EXITING SYNC"));
  oled.setCursor(0, 2); oled.print(F("Starting..."));
  delay(500);

  // Recarrega o default preset e o primeiro grupo gravados de fresco
  curPreset = EEPROM.read(ADDR_CONFIG + 1);
  if (curPreset >= 64) curPreset = 0;
  patch(curPreset);

  curGroup = 0;
  getGroupPresets(0, grPresets);
}


// -----------------------------------------------------------------------------
// 1. FEEDBACK DO HOLD
// -----------------------------------------------------------------------------
void visualFeedbackHold(uint8_t btnIndex) {
  oled.ssd1306WriteCmd(SSD1306_DISPLAYON);


  if(subMenu > 9){
    if (btnIndex == btPin[CL]) {
      oled.setCursor(0, 0); oled.print(F("RESET STANDARD"));
    } 
    else if (btnIndex == btPin[OK]) {
      oled.setCursor(0, 0); oled.print(F("MENU"));    
    } 
    else {
      // Foi uma das setas direcionais (UP, DN, RG, LF)
      oled.setCursor(0, 0); oled.print(F("ASSIGNED"));  
    }

    delay(1000);
    oled.clear();
    oled.ssd1306WriteCmd(SSD1306_DISPLAYOFF);
  }

}

// -----------------------------------------------------------------------------
// 2. MOSTRAR MUDANÇA DE GRUPO
// -----------------------------------------------------------------------------
void visualMudarGrupo(uint8_t idGrupo, char* nomeGrupo) {
  oled.ssd1306WriteCmd(SSD1306_DISPLAYON);
  
  // Linha 0: Número do Grupo (ex: "GRP 02/10")
  oled.setCursor(0, 0);
  oled.print(F("GRP "));
  if (idGrupo + 1 < 10) oled.print(F("0"));
  oled.print(idGrupo + 1);
  oled.print(F("/10"));

  // Linha 2: Nome do Grupo (ex: "METAL")
  oled.setCursor(0, 2);
  oled.print(nomeGrupo);

  delay(1500);
  oled.clear();
  oled.ssd1306WriteCmd(SSD1306_DISPLAYOFF);

}

// -----------------------------------------------------------------------------
// 3. MOSTRAR PRESET DISPARADO
// -----------------------------------------------------------------------------


void visualDispararPreset(char* nomeGrupo, char* nomePreset) {
  oled.ssd1306WriteCmd(SSD1306_DISPLAYON);
  
  // Linha 0: Botão e Grupo (ex: "[UP] METAL")
  oled.setCursor(0, 0);
  oled.print(nomeGrupo);

  // Linha 2: Nome do Preset (ex: "> ESP DropD")
  oled.setCursor(0, 2);
  oled.print(F("> "));
  oled.print(nomePreset);

  delay(1500);
  oled.clear();
  oled.ssd1306WriteCmd(SSD1306_DISPLAYOFF);
}

// =============================================================================
// 1. LER O NOME DE UM PRESET (0 a 63)
// =============================================================================
// dest deve ter pelo menos 11 bytes declarados: char nomeP[11];
void getPatchName(uint8_t idPreset, char* dest) {
  // Trava de segurança: garante que não passa do preset 63
  if (idPreset >= 64) idPreset = 0;

  // Cada preset ocupa 10 bytes:
  int endBase = ADDR_PATCHES + (idPreset * 10);

  // Lê os 10 caracteres gravados na EEPROM
  for (uint8_t i = 0; i < 10; i++) {
    dest[i] = EEPROM.read(endBase + i);
  }
  
  // Injeta o terminador em RAM para ser uma string válida de C/C++
  dest[10] = '\0';
}

// =============================================================================
// 2. LER O NOME DE UM GRUPO (0 a 9)
// =============================================================================
// dest deve ter pelo menos 11 bytes declarados: char nomeG[11];
void getGroupName(uint8_t idGrupo, char* dest) {
  // Trava de segurança: garante que não passa do grupo 9
  if (idGrupo >= 10) idGrupo = 0;

  // Cada grupo ocupa 14 bytes (o nome são os primeiros 10 bytes):
  int endBase = ADDR_GROUPS + (idGrupo * 14);

  // Lê os 10 caracteres do nome
  for (uint8_t i = 0; i < 10; i++) {
    dest[i] = EEPROM.read(endBase + i);
  }

  // Injeta o terminador em RAM
  dest[10] = '\0';
}

// =============================================================================
// BÓNUS: LER OS 4 PRESETS ATRIBUÍDOS AO GRUPO (UP, DN, RG, LF)
// =============================================================================
// destPresets deve ser um vetor de 4 bytes: uint8_t grPresets[4];
void getGroupPresets(uint8_t idGrupo, uint8_t* destPresets) {
  if (idGrupo >= 10) idGrupo = 0;

  // Os 4 atalhos começam logo a seguir aos 10 bytes do nome:
  int endPresets = ADDR_GROUPS + (idGrupo * 14) + 10;

  for (uint8_t i = 0; i < 4; i++) {
    destPresets[i] = EEPROM.read(endPresets + i);
    // Validação extra: se o valor for inválido (> 63), assume 0
    if (destPresets[i] >= 64) destPresets[i] = 0;
  }
}

// Função de envio rápido sem delays bloqueantes
void sendMidiFast(byte cmd, byte data1, byte data2) {
  Serial.write(cmd);
  Serial.write(data1);
  Serial.write(data2);
}

void tratarPedalExpressao() {
  // 1. Só processa se o pedal estiver ligado (FxPed == 0 significa "On")
  if (menuXp[0].val != 1) return;

  // 2. Taxa de amostragem: lê a cada 5ms
  if (millis() - timerLeituraFx < 5) return;
  timerLeituraFx = millis();

  // Limites definidos pelo utilizador no menu
  byte minVal = menuXp[3].val;
  byte maxVal = menuXp[4].val;

  // 3. Lê o pino analógico Fx (A1)
  int leituraADC = analogRead(Fx);

  // Constringe entre os limites reais calibrados (mesmo se o pedal tiver polaridade invertida)
  if (potMinRaw < potMaxRaw) {
    leituraADC = constrain(leituraADC, potMinRaw, potMaxRaw);
  } else {
    leituraADC = constrain(leituraADC, potMaxRaw, potMinRaw);
  }

  // 4. Mapeia do curso mecânico real para o intervalo MIDI desejado (ex: 0 a 127)
  byte fxVal = map(leituraADC, potMinRaw, potMaxRaw, minVal, maxVal);

  // 5. Só dispara mensagem MIDI se o valor realmente mudou (elimina ruído)
  if (fxVal != lastFxVal) {
    lastFxVal = fxVal;

    // Identifica qual o CC de destino conforme o Modo (Whammy=20, Capo=11, Detune=19)
    byte modoAtivo = menuXp[1].val;
    byte ccDestino = ccXpModo[modoAtivo];

    // Envia o comando MIDI CC de imediato!
    sendMidiFast(0xB0, ccDestino, fxVal);
  }
}

void calibrarPedal() {
  
  oled.clear();
  oled.setCursor(0, 0); oled.print(F("XP TRAVEL"));

  // Espera que o utilizador solte o OK que usou no arranque
  while (digitalRead(btPin[OK]) == LOW);
  delay(100);

  // PASSO 1: CALCANHAR (Posição Mínima)
  oled.clear();
  oled.setCursor(0, 0); oled.print(F("CALIB: HEEL (MIN)"));
  oled.setCursor(0, 2); oled.print(F("Set & Press OK"));

  // Espera que o utilizador coloque o pedal no calcanhar e clique OK
  while (digitalRead(btPin[OK]) == HIGH);
  delay(50);
  int rawMin = analogRead(Fx);  

  // PASSO 2: PONTA DO PÉ (Posição Máxima)
  oled.clear();
  oled.setCursor(0, 0); oled.print(F("CALIB: TOE (MAX)"));
  oled.setCursor(0, 2); oled.print(F("Set & Press OK"));

  // Espera que solte o OK
  while (digitalRead(btPin[OK]) == LOW);
  delay(100);

  while (digitalRead(btPin[OK]) == HIGH);
  delay(50);  
  int rawMax = analogRead(Fx);
  
  while (digitalRead(btPin[OK]) == LOW);
  delay(100);

  // VALIDAÇÃO: Verifica se a amplitude mecânica é suficiente (mínimo 150 pontos ADC)
  oled.clear();
  if (abs(rawMax - rawMin) >= 150) {
    // Aplica margem de segurança de 15 pontos para garantir o 0 e o 127
    if (rawMin < rawMax) {
      rawMin += 15;
      rawMax -= 15;
    } else {
      rawMin -= 15;
      rawMax += 15;
    }

    // Grava na EEPROM
    CalibPedal cal = { rawMin, rawMax };
    EEPROM.put(ADDR_CALIB, cal);

    // Atualiza as variáveis em RAM
    potMinRaw = rawMin;
    potMaxRaw = rawMax;

    oled.setCursor(0, 0); oled.print(F("CALIB SUCCESS!"));
    oled.setCursor(0, 2); oled.print(F("Saved to Memory"));
  } else {
    oled.setCursor(0, 0); oled.print(F("! CALIB ERROR !"));
    oled.setCursor(0, 2); oled.print(F("Range too small"));
  }

  delay(2000);
  oled.clear();
}
