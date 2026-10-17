from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    
    DATABASE_URL: str
    DIRECT_URL: str
    
    class Config:
        # Specify the path to your .env file
        env_file = ".env"

# Instantiate the settings object
settings = Settings()