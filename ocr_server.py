import os
import tempfile

import uvicorn
from fastapi import FastAPI, File, UploadFile
from rapidocr_onnxruntime import RapidOCR


app = FastAPI()

print("Loading RapidOCR (ONNX) model...")
engine = RapidOCR()
print("RapidOCR model loaded.")


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
        if result:
            txts = [line[1] for line in result if len(line) > 1]
            full_text = "\n".join(txts)

        return {"status": "success", "extracted_text": full_text, "elapse": elapse}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
