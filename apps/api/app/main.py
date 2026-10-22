from fastapi import FastAPI

app = FastAPI(title="SteelOS API", version="0.1.0")


@app.get("/api/v1/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "steelos-api"}
