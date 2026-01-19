from fastapi import FastAPI, UploadFile, File
from rapidocr_onnxruntime import RapidOCR
import uvicorn
import tempfile
import os

app = FastAPI()

print("正在加载 RapidOCR (ONNX) 模型...")
engine = RapidOCR()
print("✅ 模型加载完毕！")

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

        lines = []
        if result:
            for line in result:
                # line: [box, text, score]
                if len(line) >= 3:
                    lines.append({"text": line[1], "score": float(line[2])})
                elif len(line) >= 2:
                    lines.append({"text": line[1], "score": None})

        full_text = "\n".join([x["text"] for x in lines]) if lines else ""

        return {
            "status": "success",
            "text": full_text,              # ✅ 给项目用
            "lines": lines,                 # ✅ 给项目用
            "extracted_text": full_text,    # 兼容你原来的字段
            "elapse": elapse,
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
