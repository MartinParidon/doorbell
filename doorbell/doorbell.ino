#include <BLEDevice.h>
#include <BLEUtils.h>
#include <BLEServer.h>
#include <BLE2902.h>

// ===== Konfiguration =====
const char* deviceName = "ESP32-BLE-PIN";
const uint32_t richtigePIN = 659432;  // Als Zahl, nicht String!
const int outputPin = 2;
const int outputDauerMs = 5000;

// UUIDs
#define SERVICE_UUID           "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
#define CHARACTERISTIC_UUID_RX "beb5483e-36e1-4688-b7f5-ea07361b26a8"
#define CHARACTERISTIC_UUID_TX "beb5483e-36e1-4688-b7f5-ea07361b26a9"

BLECharacteristic *pTxCharacteristic;
bool deviceConnected = false;
bool istAuthentifiziert = false;

// WICHTIG: Security Callbacks für PIN-Popup
class MySecurity : public BLESecurityCallbacks {
    uint32_t onPassKeyRequest() {
        return richtigePIN;
    }

    void onPassKeyNotify(uint32_t pass_key) {
        Serial.print("Gebe ein auf dem Handy: ");
        Serial.println(pass_key);
    }

    bool onConfirmPIN(uint32_t pass_key) {
        Serial.print("✅ PIN bestätigt: ");
        Serial.println(pass_key);
        return true;
    }

    bool onSecurityRequest() {
        return true;
    }

    void onAuthenticationComplete(esp_ble_auth_cmpl_t cmpl) {
        if(cmpl.success) {
            Serial.println("✅ Authentifizierung erfolgreich! Schalte Ausgang ein.");
            istAuthentifiziert = true;
            digitalWrite(outputPin, HIGH);
            delay(outputDauerMs);
            Serial.println("Timeout vorbei. Schalte Ausang aus.");
            digitalWrite(outputPin, LOW);
        } else {
            Serial.println("❌ Authentifizierung fehlgeschlagen!");
        }
    }
};

// Callbacks für Verbindungsereignisse
class MyServerCallbacks: public BLEServerCallbacks {
    void onConnect(BLEServer* pServer) {
        deviceConnected = true;
        Serial.println("✅ Gerät verbunden!");
    }

    void onDisconnect(BLEServer* pServer) {
        deviceConnected = false;
        istAuthentifiziert = false;
        digitalWrite(outputPin, LOW);
        Serial.println("❌ Verbindung getrennt");
        BLEDevice::startAdvertising();
    }
};

void setup() {
    Serial.begin(9600);
    pinMode(outputPin, OUTPUT);
    digitalWrite(outputPin, LOW);
    
    // BLE initialisieren
    BLEDevice::init(deviceName);
    
    // WICHTIG: Security mit den RICHTIGEN Methoden für deine Version
    BLEDevice::setSecurityCallbacks(new MySecurity());
    
    // Security-Konfiguration über BLESecurity-Objekt (nicht direkt über BLEDevice)
    BLESecurity *pSecurity = new BLESecurity();
    pSecurity->setAuthenticationMode(ESP_LE_AUTH_REQ_SC_MITM_BOND); // Secure Connections + MITM + Bonding
    pSecurity->setCapability(ESP_IO_CAP_OUT); // Display Only - zeigt PIN an
    pSecurity->setInitEncryptionKey(ESP_BLE_ENC_KEY_MASK | ESP_BLE_ID_KEY_MASK);
    pSecurity->setRespEncryptionKey(ESP_BLE_ENC_KEY_MASK | ESP_BLE_ID_KEY_MASK);
    pSecurity->setPassKey(true, richtigePIN);
    
    BLEServer *pServer = BLEDevice::createServer();
    pServer->setCallbacks(new MyServerCallbacks());
    
    // Service erstellen
    BLEService *pService = pServer->createService(SERVICE_UUID);
    
    // TX Characteristic mit Security
    pTxCharacteristic = pService->createCharacteristic(
        CHARACTERISTIC_UUID_TX,
        BLECharacteristic::PROPERTY_NOTIFY
    );
    pTxCharacteristic->addDescriptor(new BLE2902());
    
    // RX Characteristic mit Security
    BLECharacteristic *pRxCharacteristic = pService->createCharacteristic(
        CHARACTERISTIC_UUID_RX,
        BLECharacteristic::PROPERTY_WRITE
    );
    // Zugriffsberechtigung: Nur verschlüsselt schreibbar
    pRxCharacteristic->setAccessPermissions(ESP_GATT_PERM_WRITE_ENCRYPTED);
    
    // Service starten
    pService->start();
    
    // Advertising starten
    BLEAdvertising *pAdvertising = BLEDevice::getAdvertising();
    pAdvertising->addServiceUUID(SERVICE_UUID);
    pAdvertising->setScanResponse(true);
    pAdvertising->setMinPreferred(0x06);
    pAdvertising->setMinPreferred(0x12); 
    
    BLEDevice::startAdvertising();
    
    Serial.println("\n\n=================================");
    Serial.print("📡 Connect to: "); Serial.println(deviceName);
    Serial.println("=================================\n");
}

void loop() {
    delay(100);
}