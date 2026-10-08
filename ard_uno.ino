#include <Wire.h>
#include <LiquidCrystal_I2C.h>

LiquidCrystal_I2C lcd(0x27, 16, 2);

#define GSM_RX 16
#define GSM_TX 17
HardwareSerial gsm(2);

bool smsSent = false;

// -------- LCD HELPER --------
void updateLCD(String line1, String line2) {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print(line1.substring(0, 16));
  lcd.setCursor(0, 1);
  lcd.print(line2.substring(0, 16));
}

// -------- GSM HELPER --------
bool gsmWaitFor(const char* expected, unsigned long timeout_ms) {
  unsigned long start = millis();
  String response = "";
  while (millis() - start < timeout_ms) {
    while (gsm.available()) {
      char c = (char)gsm.read();
      response += c;
      Serial.write(c);
    }
    if (response.indexOf(expected) != -1) return true;
  }
  Serial.println("\nGSM TIMEOUT. Got: [" + response + "]");
  return false;
}

// -------- SEND AT COMMAND WITH RETRY --------
bool sendAT(String cmd, const char* expected, unsigned long timeout_ms, int retries = 3) {
  for (int i = 0; i < retries; i++) {
    while (gsm.available()) gsm.read(); // flush
    gsm.print(cmd + "\r");
    Serial.println(">> Sending: " + cmd);
    if (gsmWaitFor(expected, timeout_ms)) return true;
    delay(500);
  }
  return false;
}

// -------- SEND SMS --------
void sendSMS(String zoneMsg) {
  Serial.println(">> Sending SMS for zones: " + zoneMsg);

  // Flush buffer
  while (gsm.available()) gsm.read();

  // Step 1: Text mode
  if (!sendAT("AT+CMGF=1", "OK", 3000, 3)) {
    Serial.println("CMGF failed");
    updateLCD("SMS Error", "CMGF failed");
    return;
  }
  delay(500);

  // Step 2: Set recipient (CHANGE THIS NUMBER)
  gsm.print("AT+CMGS=\"+916383445022\"\r");
  Serial.println(">> Waiting for >...");

  if (!gsmWaitFor(">", 10000)) {
    Serial.println("No > prompt");
    updateLCD("SMS Error", "No prompt");
    gsm.write(27); // ESC
    return;
  }

  Serial.println(">> Got >. Sending body...");
  delay(500);

  // Step 3: Message body
  gsm.print("High Crowd Alert!\r\nZone = ");
  gsm.print(zoneMsg);

  delay(500);

  // Step 4: Ctrl+Z to transmit
  gsm.write(26);
  Serial.println(">> Ctrl+Z sent. Waiting for +CMGS...");

  // Step 5: Confirm
  if (gsmWaitFor("+CMGS:", 20000)) {
    Serial.println(">> SMS SENT SUCCESSFULLY!");
    updateLCD("SMS Sent!", "Zone:" + zoneMsg);
  } else {
    Serial.println(">> SMS FAILED");
    updateLCD("SMS Failed!", "No confirm");
    gsm.write(27); // ESC to cancel
  }
  delay(1000);
}

// -------- SETUP --------
void setup() {
  Serial.begin(115200);

  // *** FIX: Use 9600 baud for GSM (SIM800L/SIM900 default) ***
  gsm.begin(9600, SERIAL_8N1, GSM_RX, GSM_TX);

  lcd.init();
  lcd.backlight();
  updateLCD("System Boot...", "");
  delay(3000);

  updateLCD("GSM Init...", "Please wait");

  // *** FIX: Auto-baud sync — send AT until we get OK ***
  Serial.println(">> Trying to sync GSM baud...");
  bool gsmReady = false;
  for (int i = 0; i < 10; i++) {
    gsm.print("AT\r");
    if (gsmWaitFor("OK", 2000)) {
      gsmReady = true;
      Serial.println(">> GSM responded OK on attempt " + String(i + 1));
      break;
    }
    delay(1000);
  }

  if (!gsmReady) {
    Serial.println(">> GSM not responding! Check wiring/power.");
    updateLCD("GSM ERROR", "No response");
    // Don't halt — keep running so LCD still works
  }

  // Turn off echo
  sendAT("ATE0", "OK", 2000, 2);

  // Check SIM
  if (!sendAT("AT+CPIN?", "READY", 5000, 3)) {
    Serial.println("SIM not ready!");
    updateLCD("SIM ERROR", "Check SIM");
  } else {
    Serial.println(">> SIM Ready");
  }

  delay(1000);

  // Check network registration (try up to 15 seconds)
  bool netReady = false;
  for (int i = 0; i < 5; i++) {
    gsm.print("AT+CREG?\r");
    if (gsmWaitFor("0,1", 3000) || gsmWaitFor("0,5", 3000)) {
      netReady = true;
      Serial.println(">> Network registered");
      break;
    }
    delay(2000);
  }
  if (!netReady) {
    Serial.println("No network!");
    updateLCD("NO SIGNAL", "Check antenna");
  }

  // Set SMS mode — retry up to 5 times
  if (!sendAT("AT+CMGF=1", "OK", 3000, 5)) {
    Serial.println("CMGF init failed");
    updateLCD("SMS WARN", "CMGF retry later");
  } else {
    Serial.println(">> GSM Ready");
    updateLCD("GSM OK", "System Ready");
  }

  delay(1000);
  updateLCD("System Ready", "Monitoring...");
}

// -------- LOOP --------
void loop() {
  if (Serial.available()) {
    String data = Serial.readStringUntil('\n');
    data.trim();

    if (data.length() == 0) return;

    Serial.println("Received: [" + data + "]");

    // -------- HIGH ALERT --------
    if (data.startsWith("HIGH:")) {
      String zones = data.substring(5);

      // Strip anything after '|' (safety net)
      int pipeIdx = zones.indexOf('|');
      if (pipeIdx != -1) zones = zones.substring(0, pipeIdx);
      zones.trim();

      updateLCD("CROWD ALERT!", "Zone:" + zones);

      delay(500);
      sendSMS(zones);
    }

    // -------- NORMAL --------
    else if (data == "NORMAL") {
      updateLCD("Status: Normal", "Monitoring...");
      smsSent = false;
      Serial.println("State reset to NORMAL");
    }

    // -------- UNKNOWN --------
    else {
      Serial.println("Unknown: " + data);
    }
  }
}
