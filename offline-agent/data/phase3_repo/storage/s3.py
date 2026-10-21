"""Amazon S3 presigned URL generation."""
def generate_presigned_upload_url(bucket: str, object_key: str) -> str:
    """Generate presigned S3 upload URL for media and PDFs."""
    return f"https://{bucket}.s3.amazonaws.com/{object_key}?signature=mock_sig"
