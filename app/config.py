from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    aws_region:str = ""
    aws_access_key_id:str=""
    aws_secret_access_key:str=""

    s3_bucket:str=""
    s3_prefix:str="documents"

    kb_id:str=""
    top_k:int=4

    groq_api_key:str=""
    groq_model:str="openai/gpt-oss-120b"

    database_url:str=""

    max_upload_mb:int=50
    
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24
    
    NS: str = "jkbdfsjkbdk"


@lru_cache
def get_settings() -> Settings:
    return Settings()
