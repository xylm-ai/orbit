import boto3
from app.config import settings


def _client():
    return boto3.client(
        "s3",
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.aws_region,
    )


def upload_file(file_bytes: bytes, s3_key: str, content_type: str = "application/octet-stream") -> str:
    """Upload bytes to S3 and return the S3 key."""
    _client().put_object(
        Bucket=settings.s3_bucket_name,
        Key=s3_key,
        Body=file_bytes,
        ContentType=content_type,
    )
    return s3_key


def get_file_bytes(s3_key: str) -> bytes:
    """Download a file from S3 and return its bytes."""
    resp = _client().get_object(Bucket=settings.s3_bucket_name, Key=s3_key)
    return resp["Body"].read()


def get_file_url(s3_key: str) -> str:
    """Generate a presigned URL valid for 1 hour (for display/download)."""
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket_name, "Key": s3_key},
        ExpiresIn=3600,
    )
