"""Convocações: detecção de cartazes/postagens que convocam para atos (em especial não pacíficos).

Pipeline por imagem (CPU, sem login, só fontes públicas):
  Pillow → pHash/dHash (imagem.py) → OpenCV (pré-processamento + QR) → OCR (rapidocr, opcional)
  → léxico ponderado (lexico_mobilizacao.py) + queries dos monitores (radar.Matcher)
  → CLIP zero-shot/similaridade (clip.py, opcional) → score 0-100 + severidade (score.py).
"""
