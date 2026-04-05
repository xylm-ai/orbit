from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str
    access_token_expire_minutes: int = 60
    environment: str = "development"

    # AWS S3
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "ap-south-1"
    s3_bucket_name: str = "orbit-documents"

    # OpenAI
    openai_api_key: str = ""

    # Postmark
    postmark_inbound_token: str = ""

settings = Settings()
