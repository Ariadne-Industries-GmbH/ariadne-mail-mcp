# rthook_no_pyi.py
def _no_op(*a, **k):
    return None


try:
    import gradio.component_meta as cm

    # Gradio 5.x generiert zur Laufzeit pyi – das killen wir im Frozen-App-Kontext
    cm.create_or_modify_pyi = _no_op
except Exception:
    pass
