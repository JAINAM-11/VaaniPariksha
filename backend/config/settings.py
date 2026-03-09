"""
VaaniPariksha - Application Settings
Loads all configuration from environment variables.
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Flask
    SECRET_KEY = os.getenv("SECRET_KEY", "vaanipariksha-dev-secret-key")
    DEBUG = os.getenv("FLASK_DEBUG", "False").lower() == "true"
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", 5000))

    # Storage mode: 'local' or 'aws'
    STORAGE_MODE = os.getenv("STORAGE_MODE", "local")

    # --- Database ---
    @staticmethod
    def get_db_url():
        mode = os.getenv("STORAGE_MODE", "local")
        if mode == "aws":
            return (
                f"postgresql://{os.getenv('AWS_RDS_USER')}:{os.getenv('AWS_RDS_PASSWORD')}"
                f"@{os.getenv('AWS_RDS_HOST')}:{os.getenv('AWS_RDS_PORT', 5432)}"
                f"/{os.getenv('AWS_RDS_NAME')}"
            )
        elif mode == "postgres":
            return (
                f"postgresql://{os.getenv('DB_USER', 'postgres')}:{os.getenv('DB_PASSWORD', 'password')}"
                f"@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', 5432)}"
                f"/{os.getenv('DB_NAME', 'vaanipariksha_db')}"
            )
        # Default local mode uses SQLite (zero-config)
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        db_path = os.path.join(base_dir, "vaanipariksha.db")
        return f"sqlite:///{db_path}"

    SQLALCHEMY_DATABASE_URI = get_db_url.__func__()  # type: ignore
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size": 10,
        "pool_recycle": 3600,
        "pool_pre_ping": True,
    }

    # --- AWS ---
    AWS_S3_BUCKET = os.getenv("AWS_S3_BUCKET", "vaanipariksha-pdfs")
    AWS_S3_REGION = os.getenv("AWS_S3_REGION", "ap-south-1")
    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")

    # --- File Paths ---
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
    GENERATED_PDF_FOLDER = os.path.join(BASE_DIR, "generated_pdfs")
    VOSK_MODEL_PATH = os.getenv(
        "VOSK_MODEL_PATH",
        os.path.join(BASE_DIR, "models_vosk", "vosk-model-small-en-us-0.15")
    )
    MAX_PDF_SIZE_BYTES = int(os.getenv("MAX_PDF_SIZE_MB", 50)) * 1024 * 1024

    # --- Tesseract ---
    TESSERACT_CMD = os.getenv(
        "TESSERACT_CMD",
        r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    )

    # --- Voice ---
    STT_CONFIDENCE_THRESHOLD = float(os.getenv("STT_CONFIDENCE_THRESHOLD", 0.75))
    TTS_RATE = int(os.getenv("TTS_RATE", 150))
    TTS_VOLUME = float(os.getenv("TTS_VOLUME", 1.0))

    # --- Security ---
    ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "VaaniPariksha2024KeyChangeInProd!")

    # --- Session ---
    AUTO_SAVE_INTERVAL = int(os.getenv("AUTO_SAVE_INTERVAL_SECONDS", 30))
    DEFAULT_EXAM_DURATION = int(os.getenv("DEFAULT_EXAM_DURATION_MINUTES", 60))

    # --- CORS ---
    CORS_ORIGINS = ["http://localhost:5000", "http://127.0.0.1:5000"]


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
