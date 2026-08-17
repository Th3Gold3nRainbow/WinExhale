"""
smoke_test.py — frozen-GUI harness for WinExhale's first-launch flow.

Builds/runs like the real app (--onefile --windowed, no UAC so it can run
unattended): shows the language dialog, auto-picks English after 3 s, closes
after 7 s, and writes smoke_result.txt next to the exe with OK or the traceback.
"""

import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else HERE
RESULT = os.path.join(OUT_DIR, "smoke_result.txt")
sys.path.insert(0, HERE)


def report(text):
    with open(RESULT, "w", encoding="utf-8") as fh:
        fh.write(text)


def run():
    import main as m
    m.ctk.set_appearance_mode("dark")
    m.ctk.set_default_color_theme("dark-blue")
    app = m.WinExhaleApp()
    state = {"stage": "constructed"}

    def pick():
        state["stage"] = "picked"
        app._pick_language("en")                     # simulates clicking English

    def finish():
        state["stage"] = "closing"
        app.destroy()

    app.after(3000, pick)
    app.after(7000, finish)
    app.mainloop()
    startup_items = m.scan_startup_items()           # startup manager logic works frozen
    return (f"OK stage={state['stage']} lang={app.lang} "
            f"header={getattr(app, 'header', None) is not None} "
            f"bloat_items={len(getattr(app, '_debloat_vars', None) or [])} "
            f"startup_items={len(startup_items)} "
            f"config={m.load_config()}")


if __name__ == "__main__":
    report("STARTED")
    try:
        out = run()
    except Exception:
        out = "FAIL\n" + traceback.format_exc()
    report(out)
