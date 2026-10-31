from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.auth.router import router as auth_router

app = FastAPI(title="DocBro backend api")

origins = [
    "http://localhost:5173",  # Vite React default
    "http://127.0.0.1:5173",
    "http://localhost:3000",  # CRA default
    "http://127.0.0.1:3000",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # Production me ["*"] mat karna, yahan list de
    allow_credentials=True,
    allow_methods=["*"],  # GET, POST, PUT, DELETE sab allow
    allow_headers=["*"],  # Authorization, Content-Type sab allow
)



app.include_router(auth_router)