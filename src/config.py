from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_path: str = "data/legal.db"
    opencode_zen_api_key: str = ""
    opencode_zen_base_url: str = "https://opencode.ai/zen/v1"
    opencode_zen_model: str = "deepseek-v4-flash-free"
    telegram_bot_token: str = ""
    parallel_search_mcp_url: str = "https://search.parallel.ai/mcp"
    admin_telegram_id: int = 0
    support_contact: str = "https://t.me/your_support_bot"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
