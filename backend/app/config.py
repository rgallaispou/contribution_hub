from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str = "sqlite:///./data/contributions.db"
    identities: str = "rgallaispou@gmail.com,raphael.gallais-pou@foss.st.com"
    import_dir: str = "./imports"
    lore_base_url: str = "https://lore.kernel.org/all/"
    app_env: str = "development"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def identity_emails(self) -> list[str]:
        return sorted({x.strip().lower() for x in self.identities.split(",") if x.strip()})

    @property
    def import_path(self) -> Path:
        p = Path(self.import_dir).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

settings = Settings()
