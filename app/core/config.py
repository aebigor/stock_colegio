from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    # Aplicación
    APP_NAME: str
    APP_VERSION: str
    DEBUG: bool

    HOST: str
    PORT: int

    # Seguridad
    SECRET_KEY: str
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int

    # PostgreSQL
    DATABASE_HOST: str
    DATABASE_PORT: int
    DATABASE_NAME: str
    DATABASE_USER: str
    DATABASE_PASSWORD: str

    INITIAL_ADMIN_PASSWORD: str = "CambiarAdmin2026!"
    INITIAL_BADER_PASSWORD: str = "CambiarBader2026!"
    PLATFORM_ADMIN_EMAIL: str = "tecnologia@gimsau.edu.co"
    # URL pública/base para que los QR abran el sistema desde otro dispositivo.
    PUBLIC_BASE_URL: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )

    @property
    def DATABASE_URL(self):

        return (
            f"postgresql+psycopg://"
            f"{self.DATABASE_USER}:"
            f"{self.DATABASE_PASSWORD}@"
            f"{self.DATABASE_HOST}:"
            f"{self.DATABASE_PORT}/"
            f"{self.DATABASE_NAME}"
        )


settings = Settings()