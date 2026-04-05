import pytest
import boto3
from moto import mock_aws
from app.services.storage import upload_file, get_file_url


@pytest.fixture
def s3(monkeypatch):
    with mock_aws():
        import app.config
        app.config.settings.aws_access_key_id = "test"
        app.config.settings.aws_secret_access_key = "test"
        app.config.settings.aws_region = "ap-south-1"
        app.config.settings.s3_bucket_name = "test-orbit-documents"

        client = boto3.client("s3", region_name="ap-south-1")
        client.create_bucket(
            Bucket="test-orbit-documents",
            CreateBucketConfiguration={"LocationConstraint": "ap-south-1"},
        )
        yield client

        # Reset
        app.config.settings.aws_access_key_id = ""
        app.config.settings.aws_secret_access_key = ""


def test_upload_and_url(s3):
    key = upload_file(b"hello pdf", "documents/fam1/doc1/test.pdf", "application/pdf")
    assert key == "documents/fam1/doc1/test.pdf"
    url = get_file_url("documents/fam1/doc1/test.pdf")
    assert "test-orbit-documents" in url
    assert "documents/fam1/doc1/test.pdf" in url
