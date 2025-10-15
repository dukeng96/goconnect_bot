import io, mimetypes
import boto3
from botocore.client import Config as BotoConfig
from config import (
    logger, MINIO_SERVICE_URL, MINIO_ACCESS_KEY, MINIO_SECRET_KEY, MINIO_FOLDER_NAME,
    MINIO_PUBLIC_HOST, MINIO_EXPIRE_TIME
)

s3 = None
if MINIO_SERVICE_URL and MINIO_ACCESS_KEY and MINIO_SECRET_KEY and MINIO_FOLDER_NAME:
    s3 = boto3.client('s3', endpoint_url=MINIO_SERVICE_URL,
                      aws_access_key_id=MINIO_ACCESS_KEY, aws_secret_access_key=MINIO_SECRET_KEY,
                      config=BotoConfig(signature_version='s3v4'))
    logger.info("MinIO configured: %s bucket=%s", MINIO_SERVICE_URL, MINIO_FOLDER_NAME)
else:
    logger.warning("MinIO is not fully configured. Attachments will not be uploaded.")


def upload_bytes(data: bytes, key: str, content_type: str | None = None) -> str | None:
    if not s3:
        return None
    try:
        s3.put_object(Bucket=MINIO_FOLDER_NAME, Key=key, Body=data, ContentType=content_type or 'application/octet-stream')
        return s3.generate_presigned_url('get_object', Params={'Bucket': MINIO_FOLDER_NAME, 'Key': key}, ExpiresIn=MINIO_EXPIRE_TIME)
    except Exception:
        logger.exception("MinIO upload failed")
        return f"{MINIO_PUBLIC_HOST}/{MINIO_FOLDER_NAME}/{key}"


def guess_content_type(filename: str) -> str:
    return mimetypes.guess_type(filename)[0] or 'application/octet-stream'