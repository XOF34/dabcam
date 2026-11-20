"""
Configuration management for Dabcam backend
"""

from pydantic_settings import BaseSettings
from typing import Optional
import os

class Settings(BaseSettings):
    """Application settings from environment variables"""

    # Application
    APP_NAME: str = "Dabcam API"
    APP_VERSION: str = "2.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-me-in-production")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://dabcam_user:changeme123@localhost:5432/dabcam")

    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://:redis123@localhost:6379/0")

    # Metasploit RPC
    MSF_RPC_HOST: str = os.getenv("MSF_RPC_HOST", "localhost")
    MSF_RPC_PORT: int = int(os.getenv("MSF_RPC_PORT", 55553))
    MSF_RPC_USER: str = os.getenv("MSF_RPC_USER", "msf")
    MSF_RPC_PASS: str = os.getenv("MSF_RPC_PASS", "changeme123")

    # CORS
    CORS_ORIGINS: list = ["http://localhost:3000", "http://localhost:80"]
    ALLOWED_HOSTS: list = ["localhost", "127.0.0.1", "dabcam.local"]

    # Upload Configuration
    MAX_FILE_SIZE: int = 5 * 1024 * 1024  # 5MB
    MAX_STORAGE: int = 10 * 1024 * 1024 * 1024  # 10GB
    STORAGE_DIR: str = "/secure/storage"
    BINARIES_DIR: str = "/secure/binaries"

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
