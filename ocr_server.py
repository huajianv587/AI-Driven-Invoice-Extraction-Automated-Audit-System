import os
import tempfile
from urllib.parse import urlparse

import uvicorn
from fastapi import FastAPI, File, UploadFile
from rapidocr_onnxruntime import RapidOCR

from src.config import load_env


app = FastAPI()

print("Loading RapidOCR (ONNX) model...")
engine = RapidOCR()
print("RapidOCR model loaded.")


def _resolve_ocr_bind() -> tuple[str, int, str]:
    load_env()
    base_url = (os.getenv("OCR_BASE_URL") or "http://127.0.0.1:8001").strip() or "http://127.0.0.1:8001"
    if "://" not in base_url:
        base_url = f"http://{base_url}"

    parsed = urlparse(base_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 8001
    return host, port, base_url.rstrip("/")


@app.post("/ocr")
async def ocr_endpoint(file: UploadFile = File(...)):
    tmp_path = None
    try:
        suffix = os.path.splitext(file.filename or "")[1] or ".jpg"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp_path = tmp.name
            content = await file.read()
            tmp.write(content)

        result, elapse = engine(tmp_path)
        full_text = ""
        ocr_lines = []
        if result:
            txts = []
            for line in result:
                if len(line) < 2:
                    continue
                box = []
                for point in line[0] or []:
                    if isinstance(point, (list, tuple)) and len(point) >= 2:
                        box.append([float(point[0]), float(point[1])])
                text = str(line[1] or "").strip()
                score = float(line[2]) if len(line) > 2 and line[2] is not None else None
                if text:
                    txts.append(text)
                ocr_lines.append({"box": box, "text": text, "score": score})
            full_text = "\n".join(txts)

        return {
            "status": "success",
            "extracted_text": full_text,
            "elapse": elapse,
            "lines": ocr_lines,
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


if __name__ == "__main__":
    bind_host, bind_port, base_url = _resolve_ocr_bind()
    print(f"Starting OCR service at {base_url} ...")
    uvicorn.run(app, host=bind_host, port=bind_port)
