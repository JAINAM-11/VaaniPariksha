"""
VaaniPariksha - AWS S3 Utilities
Upload/download PDFs from S3 with local fallback.
"""
import os
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def get_s3_client():
    """Create and return a boto3 S3 client using env credentials."""
    try:
        import boto3
        return boto3.client(
            "s3",
            region_name=os.getenv("AWS_S3_REGION", "ap-south-1"),
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        )
    except Exception as e:
        logger.error(f"Failed to create S3 client: {e}")
        return None


def upload_pdf_to_s3(local_path: str, s3_key: str, bucket: str = None) -> Optional[str]:
    """
    Upload a PDF file to S3.
    Returns the S3 key on success, None on failure.
    """
    from backend.config.settings import Config
    bucket = bucket or Config.AWS_S3_BUCKET
    client = get_s3_client()
    if not client:
        return None
    try:
        client.upload_file(
            local_path, bucket, s3_key,
            ExtraArgs={"ContentType": "application/pdf"}
        )
        logger.info(f"Uploaded {local_path} → s3://{bucket}/{s3_key}")
        return s3_key
    except Exception as e:
        logger.error(f"S3 upload failed: {e}")
        return None


def download_pdf_from_s3(s3_key: str, dest_path: str, bucket: str = None) -> bool:
    """
    Download a PDF from S3 to local path.
    Returns True on success.
    """
    from backend.config.settings import Config
    bucket = bucket or Config.AWS_S3_BUCKET
    client = get_s3_client()
    if not client:
        return False
    try:
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        client.download_file(bucket, s3_key, dest_path)
        logger.info(f"Downloaded s3://{bucket}/{s3_key} → {dest_path}")
        return True
    except Exception as e:
        logger.error(f"S3 download failed: {e}")
        return False


def get_presigned_url(s3_key: str, bucket: str = None, expires: int = 3600) -> Optional[str]:
    """Generate a presigned URL for temporary PDF access."""
    from backend.config.settings import Config
    bucket = bucket or Config.AWS_S3_BUCKET
    client = get_s3_client()
    if not client:
        return None
    try:
        url = client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": s3_key},
            ExpiresIn=expires,
        )
        return url
    except Exception as e:
        logger.error(f"Presigned URL failed: {e}")
        return None
