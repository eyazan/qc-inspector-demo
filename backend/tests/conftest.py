import os

# Force mock providers for the whole unit suite (no GPU/SAP/LLM/OCR needed).
os.environ.setdefault("RUN_MODE", "mock")
