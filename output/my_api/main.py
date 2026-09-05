
from fastapi import FastAPI

app = FastAPI(title="my_api")

@app.get("/")
def root():
    return {"message": "Hello from my_api"}

@app.get("/health")
def health():
    return {"status": "healthy"}