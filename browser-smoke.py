#!/usr/bin/env python3
"""Echte Chromium-Rendering- und Interaktionstests für MEISTERWERK.

Benötigt: Python 3.10+, `pip install -r requirements-test.txt`,
`python -m playwright install chromium`.
Die HTML-Datei wird direkt in Chromium gerendert. Für Tests ohne HTTP-Origin
wird localStorage kontrolliert simuliert; echte Browser-Persistenz wird zusätzlich
von tests/app-smoke.test.cjs auf Speicher- und Neustartlogik geprüft.
"""
from pathlib import Path
import json
import re
import shutil
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "index.html").read_text(encoding="utf-8")
MATCH = re.search(r"<script>([\s\S]*?)</script>", HTML)
if not MATCH:
    raise SystemExit("FEHLER: App-Script fehlt.")
SCRIPT = MATCH.group(1)
STATIC_HTML = re.sub(r"<script>[\s\S]*?</script>", "", HTML, count=1)

SHIM = r"""(() => {
  window.__mwStore = window.__mwStore || {};
  window.__mwFailWrites = false;
  Object.defineProperty(window, 'localStorage', { configurable: true, value: {
    getItem(key) { return Object.prototype.hasOwnProperty.call(window.__mwStore, key) ? window.__mwStore[key] : null; },
    setItem(key, value) { if (window.__mwFailWrites) throw new Error('QuotaExceededError'); window.__mwStore[key] = String(value); },
    removeItem(key) { delete window.__mwStore[key]; }
  }});
})();"""

results = []
errors = {"desktop": [], "mobile": []}
def record(name, passed, detail=""):
    results.append({"test": name, "passed": bool(passed), "detail": detail})

def boot(page, initial_store=None):
    page.set_content(STATIC_HTML, wait_until="load")
    page.evaluate(SHIM)
    if initial_store:
        page.evaluate("value => { window.__mwStore['meisterwerk-demo-state'] = value; }", initial_store)
    page.add_script_tag(content=SCRIPT)

with sync_playwright() as p:
    chromium_path = shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome")
    browser = p.chromium.launch(headless=True, executable_path=chromium_path) if chromium_path else p.chromium.launch(headless=True)

    # Desktop: 1365 × 900
    desktop = browser.new_page(viewport={"width": 1365, "height": 900})
    desktop.on("pageerror", lambda error: errors["desktop"].append(str(error)))
    boot(desktop)
    record("Dashboard rendert", "Willkommen bei MEISTERWERK" in desktop.locator("#view").inner_text())

    desktop_targets = [
        ("dashboard", "Willkommen bei MEISTERWERK"),
        ("lernen", "Lernakademie"),
        ("pruefung", "Prüfungstraining"),
        ("karten", "Karteikarten"),
        ("fortschritt", "Lernfortschritt"),
        ("profil", "Mein Profil"),
        ("premium", "MEISTERWERK Premium"),
    ]
    for key, expected in desktop_targets:
        desktop.locator(f".sidebar [data-page='{key}']").click()
        record(f"Desktop-Navigation: {key}", expected in desktop.locator("#view").inner_text())

    desktop.locator(".sidebar [data-page='lernen']").click()
    desktop.locator(".lesson button").first.click()
    record("Lektion lässt sich öffnen", "Aufbau des menschlichen Haares" in desktop.locator("#view").inner_text())
    desktop.locator("button", has_text="Lerneinheit abschließen").click()
    record("Lektion lässt sich abschließen", "Als abgeschlossen markiert" in desktop.locator("#view").inner_text())
    stored = desktop.evaluate("JSON.parse(localStorage.getItem('meisterwerk-demo-state'))")
    record("Lernabschluss wird in localStorage geschrieben", "II-01" in stored.get("done", []))

    desktop.locator(".sidebar [data-page='pruefung']").click()
    desktop.locator("button", has_text="Training starten").first.click()
    desktop.locator(".answer").first.click()
    desktop.locator("button", has_text="Antwort überprüfen").click()
    record("Prüfungstraining zeigt Antwortfeedback", desktop.locator(".feedback").count() == 1)

    desktop.locator(".sidebar [data-page='karten']").click()
    question = desktop.locator(".flashcard .big").inner_text()
    desktop.locator(".flashcard").click()
    answer = desktop.locator(".flashcard .big").inner_text()
    record("Karteikarte lässt sich umdrehen", question != answer)
    desktop.locator("button", has_text="Weiter").click()
    record("Karteikarte lässt sich weiterblättern", "KARTE 2 VON" in desktop.locator("#view").inner_text())

    # Fehlerbehandlung: Storage-Schreibfehler darf Interaktion nicht abbrechen.
    desktop.evaluate("window.__mwFailWrites = true")
    desktop.locator(".sidebar [data-page='lernen']").click()
    desktop.locator(".lesson button").nth(1).click()
    desktop.locator("button", has_text="Lerneinheit abschließen").click()
    record("Nicht verfügbarer Speicher blockiert Lektion nicht", "Als abgeschlossen markiert" in desktop.locator("#view").inner_text())

    # Responsive Prüfung bei mehreren realen Chromium-Viewportgrößen.
    for width, height in [(320, 740), (360, 780), (375, 812), (390, 844), (430, 932), (768, 1024), (1024, 768), (1365, 900)]:
        desktop.set_viewport_size({"width": width, "height": height})
        dims = desktop.evaluate("({scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth})")
        record(f"Responsive Breite {width}px ohne horizontalen Überlauf", dims["scroll"] <= dims["client"], json.dumps(dims))

    # iPhone-nahe Touch-Emulation, 390 × 844 CSS-Pixel.
    mobile = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=3, is_mobile=True, has_touch=True)
    mobile.on("pageerror", lambda error: errors["mobile"].append(str(error)))
    boot(mobile)
    record("Mobile Bottom-Navigation sichtbar", mobile.locator("#mobileNav").is_visible())
    mobile_targets = [
        ("dashboard", "Willkommen bei MEISTERWERK"),
        ("lernen", "Lernakademie"),
        ("pruefung", "Prüfungstraining"),
        ("karten", "Karteikarten"),
        ("fortschritt", "Lernfortschritt"),
        ("profil", "Mein Profil"),
    ]
    for key, expected in mobile_targets:
        mobile.locator(f"#mobileNav [data-page='{key}']").click()
        record(f"iPhone-Touch-Navigation: {key}", expected in mobile.locator("#view").inner_text())
    record("Keine JavaScript-Laufzeitfehler Desktop", not errors["desktop"], "; ".join(errors["desktop"]))
    record("Keine JavaScript-Laufzeitfehler Mobile", not errors["mobile"], "; ".join(errors["mobile"]))

    browser.close()

failed = [item for item in results if not item["passed"]]
print(json.dumps({"browser": "Chromium", "tests": len(results), "passed": len(results)-len(failed), "failed": len(failed), "results": results}, ensure_ascii=False, indent=2))
if failed:
    raise SystemExit(1)
