#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Bluetooth Türsteuerung mit PIN-Pairing
Verhalten: Handy klickt auf Gerät -> PIN-Dialog erscheint -> Tür öffnet sich
"""

import dbus
import dbus.service
import dbus.mainloop.glib
import threading
import time
import signal
import sys
from gi.repository import GLib
from gpiozero import LED
from enum import Enum

# GPIO Pin für Türöffner (BCM 27)
DOOR_PIN = 27
PIN_CODE = 1234  # 4-stellige PIN
DEVICE_NAME = "Jazz Club Tür"

class BluetoothAgent(dbus.service.Object):
    """
    Bluetooth Agent für Passkey Entry (PIN-Eingabe)
    Wird aufgerufen, wenn ein Handy Pairing anfordert
    """
    
    def __init__(self, bus, path, door_controller):
        self.door = door_controller
        dbus.service.Object.__init__(self, bus, path)
        print(f"✅ Bluetooth Agent gestartet mit PIN {PIN_CODE}")
    
    @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="u")
    def RequestPasskey(self, device):
        """Wird aufgerufen, wenn Passkey benötigt wird"""
        device_obj = bus.get_object("org.bluez", device)
        device_props = dbus.Interface(device_obj, "org.freedesktop.DBus.Properties")
        dev_name = device_props.Get("org.bluez.Device1", "Name")
        
        print(f"\n🔑 Passkey requested for device: {dev_name} ({device})")
        print(f"   Bitte PIN {PIN_CODE} auf dem Handy eingeben...")
        
        # Hier können wir schon mal den Tür-Thread vorbereiten
        self.door.arm_for_pairing()
        
        # PIN zurückgeben (wird vom Handy erwartet)
        return dbus.UInt32(PIN_CODE)
    
    @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="")
    def RequestConfirmation(self, device, passkey):
        """Für Numeric Comparison (nicht verwendet)"""
        pass
    
    @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="")
    def AuthorizeService(self, device, uuid):
        """Service-Autorisierung"""
        return
    
    @dbus.service.method("org.bluez.Agent1", in_signature="", out_signature="")
    def Cancel(self):
        """Pairing wurde abgebrochen"""
        print("❌ Pairing cancelled by remote device")
        self.door.disarm()
    
    @dbus.service.method("org.bluez.Agent1", in_signature="", out_signature="")
    def Release(self):
        """Agent wird freigegeben"""
        print("Agent released")

class DoorController:
    """Steuert den Türöffner und Pairing-Events"""
    
    def __init__(self, pin):
        self.pin = pin
        self.led = LED(DOOR_PIN)
        self.led.off()
        self.pairing_armed = False
        self.lock = threading.Lock()
        
        # Bluetooth-Event-Handler
        self.setup_bluetooth_callbacks()
        
        print(f"🚪 Türsteuerung initialisiert (GPIO {DOOR_PIN})")
    
    def setup_bluetooth_callbacks(self):
        """Registriert Bluetooth-Event-Callbacks"""
        bus.add_signal_receiver(
            self.on_device_connected,
            signal_name="PropertiesChanged",
            dbus_interface="org.freedesktop.DBus.Properties",
            path_keyword="path"
        )
    
    def on_device_connected(self, interface, changed, invalidated, path):
        """Wird bei Änderungen von Bluetooth-Geräten aufgerufen"""
        if "org.bluez.Device1" in interface:
            if "Connected" in changed and changed["Connected"] == 1:
                # Ein Gerät hat sich verbunden (nach erfolgreichem Pairing)
                self.on_pairing_complete(path)
    
    def on_pairing_complete(self, device_path):
        """Wird nach erfolgreichem Pairing aufgerufen"""
        with self.lock:
            if self.pairing_armed:
                print("\n✅ Pairing erfolgreich! Öffne Tür...")
                self.pairing_armed = False
                # Tür in eigenem Thread öffnen (blockiert nicht)
                threading.Thread(target=self.open_door, daemon=True).start()
    
    def arm_for_pairing(self):
        """Aktiviert den Türöffner für den nächsten Pairing-Erfolg"""
        with self.lock:
            self.pairing_armed = True
            print("🔫 Bereit für Pairing...")
    
    def disarm(self):
        """Deaktiviert den Türöffner (bei Abbruch)"""
        with self.lock:
            self.pairing_armed = False
    
    def open_door(self):
        """Öffnet die Tür für 3 Sekunden"""
        print("🔓 Tür wird geöffnet...")
        self.led.on()
        time.sleep(3)
        self.led.off()
        print("🔒 Tür geschlossen")

def setup_bluetooth_adapter():
    """Konfiguriert den Bluetooth-Adapter für Pairing"""
    adapter_obj = bus.get_object("org.bluez", "/org/bluez/hci0")
    adapter = dbus.Interface(adapter_obj, "org.bluez.Adapter1")
    
    # Adapter-Konfiguration
    adapter.Set("org.bluez.Adapter1", "Powered", dbus.Boolean(1))
    adapter.Set("org.bluez.Adapter1", "Discoverable", dbus.Boolean(1))
    adapter.Set("org.bluez.Adapter1", "Pairable", dbus.Boolean(1))
    adapter.Set("org.bluez.Adapter1", "Alias", DEVICE_NAME)
    
    # Pairing-Timeout deaktivieren (0 = unbegrenzt)
    adapter.Set("org.bluez.Adapter1", "PairableTimeout", dbus.UInt32(0))
    adapter.Set("org.bluez.Adapter1", "DiscoverableTimeout", dbus.UInt32(0))
    
    # Geräte-Liste leeren (optional)
    # adapter.RemoveDevice(device_path) für jedes gepaarte Gerät
    
    print(f"📡 Bluetooth-Adapter konfiguriert: {DEVICE_NAME}")
    return adapter

def register_agent(bus, door):
    """Registriert den Agenten bei BlueZ"""
    # Agent-Pfad
    agent_path = "/test/agent"
    
    # Agent registrieren
    agent = BluetoothAgent(bus, agent_path, door)
    
    # Agent-Manager holen
    manager = dbus.Interface(
        bus.get_object("org.bluez", "/org/bluez"),
        "org.bluez.AgentManager1"
    )
    
    # Agent mit Passkey Entry registrieren
    manager.RegisterAgent(agent_path, "KeyboardOnly")
    manager.RequestDefaultAgent(agent_path)
    
    print("✅ Agent bei BlueZ registriert")
    return agent

def main_loop():
    """Hauptschleife für GLib"""
    loop = GLib.MainLoop()
    
    def signal_handler(sig, frame):
        print("\n👋 Programm wird beendet...")
        loop.quit()
    
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        loop.run()
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    print("=" * 50)
    print("🔐 JAZZ CLUB TÜRSTEUERUNG")
    print("=" * 50)
    print(f"PIN: {PIN_CODE}")
    print(f"Device Name: {DEVICE_NAME}")
    print("=" * 50)
    
    # D-Bus Mainloop initialisieren
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    
    # System-Bus verbinden
    global bus
    bus = dbus.SystemBus()
    
    # Türsteuerung initialisieren
    door = DoorController(PIN_CODE)
    
    # Bluetooth konfigurieren
    adapter = setup_bluetooth_adapter()
    
    # Agent registrieren
    agent = register_agent(bus, door)
    
    print("\n🚀 Server läuft! Jetzt im Handy:")
    print(f"   1. Bluetooth-Einstellungen öffnen")
    print(f"   2. Nach '{DEVICE_NAME}' suchen")
    print(f"   3. Draufklicken")
    print(f"   4. PIN '{PIN_CODE}' eingeben")
    print(f"   5. Tür öffnet sich")
    print("\n   Drücke Strg+C zum Beenden")
    print("-" * 50)
    
    # Hauptschleife starten
    main_loop()