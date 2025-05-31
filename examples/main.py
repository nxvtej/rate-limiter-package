from fastapi import FastAPI 
from fastapi.middleware.cors import CORSMiddleware 
from fastapi.responses import JSONResponse 
from fastapi import APIRouter
from fastapi import Request, Response 
from fastapi import HTTPException 
from .routers import users, products, orders
import logging

app = FastAPI(
    title = "Test Service",
    description="This is a test service for demonstrating my rate limiter capabilities.",
    version="1.0.0",
    contact={
        "name": "Navdeep Singh",
        "email": "navdeep.s@clear.com"
    }
    
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],  
    allow_headers=["*"],  
)

# logging configuration and indian time format and must print the filename and line number 
logging.basicConfig(level = logging.INFO, format= '%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)

app.include_router(users.router, prefix="/users", tags=["Users"])
app.include_router(products.router, prefix="/products", tags=["Products"])
app.include_router(orders.router, prefix="/orders", tags=["Orders"])


@app.get("/health", summary="Health Check", description="Check the health of the service")
async def health_check(request: Request):
    """
    Health check endpoint to verify the service is running.
    """
    logger.info("Health check endpoint called")
    return JSONResponse(content={"status": "ok"}, status_code=200)