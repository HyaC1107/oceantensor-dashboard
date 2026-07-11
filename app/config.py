from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://oceantensor_user:<REDACTED>@localhost:5433/oceantensor_db"
    # NIFS 개별 키
    nifs_api_key_femosealist: str = ""
    nifs_api_key_risalist: str = ""
    nifs_api_key_soolist: str = ""
    nifs_api_key_sois: str = ""
    nifs_api_key_redtidelist: str = ""
    # 공공데이터포털 공통 키 — .env의 'ServiceKey' 매핑
    service_key: str = Field(default="", alias="ServiceKey")
    # 수온/염분 15분 격자 전용 키 (일일 트래픽 50 제한)
    service_key_temp: str = Field(default="", alias="ServiceKey_temp")
    # 기타
    anthropic_api_key: str = ""
    # Google AI Studio (Gemini) — XAI 자연어 보고서 LLM
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.5-flash", alias="GEMINI_MODEL")
    use_mock_data: bool = True

    class Config:
        env_file = ".env"
        extra = "ignore"
        populate_by_name = True


settings = Settings()
