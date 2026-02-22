from fastapi import APIRouter

router = APIRouter(prefix="/auth", tags=["Autenticação"])

@router.post("/login")
async def login():
    return {"message": "Not implemented yet"}

@router.post("/refresh")
async def refresh():
    return {"message": "Not implemented yet"}

@router.get("/me")
async def get_me():
    return {"message": "Not implemented yet"}
