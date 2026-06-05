from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import ClientError

_client: Any | None = None
_client_lock = threading.Lock()


def _get_bucket_name() -> str:
    bucket = os.getenv("R2_BUCKET_NAME", "").strip()
    if not bucket:
        raise RuntimeError("R2_BUCKET_NAME not configured")
    return bucket


def _get_client() -> Any:
    global _client
    if _client is not None:
        return _client

    with _client_lock:
        if _client is not None:
            return _client

        endpoint = os.getenv("R2_ENDPOINT_URL", "").strip()
        access_key = os.getenv("R2_ACCESS_KEY_ID", "").strip()
        secret_key = os.getenv("R2_SECRET_ACCESS_KEY", "").strip()

        if not endpoint or not access_key or not secret_key:
            raise RuntimeError("R2 credentials not configured")

        _client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )

    return _client


def build_r2_key(doc_id: str, filename: str) -> str:
    safe_name = Path(filename).name
    return f"{doc_id}/{safe_name}"


def upload_pdf_to_r2(local_path: Path, doc_id: str, filename: str) -> str:
    client = _get_client()
    bucket = _get_bucket_name()
    key = build_r2_key(doc_id, filename)
    client.upload_file(str(local_path), bucket, key)
    return key


def s3_key_exists(s3_key: str) -> bool:
    client = _get_client()
    bucket = _get_bucket_name()
    try:
        client.head_object(Bucket=bucket, Key=s3_key)
        return True
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code", ""))
        if code in {"404", "NoSuchKey", "NotFound"}:
            return False
        raise


def download_pdf_from_r2(s3_key: str, local_path: Path) -> None:
    client = _get_client()
    bucket = _get_bucket_name()
    client.download_file(bucket, s3_key, str(local_path))


def delete_pdf_from_r2(s3_key: str) -> None:
    client = _get_client()
    bucket = _get_bucket_name()
    client.delete_object(Bucket=bucket, Key=s3_key)


def list_all_pdfs_in_r2() -> list[str]:
    client = _get_client()
    bucket = _get_bucket_name()

    keys: list[str] = []
    continuation_token: str | None = None

    while True:
        kwargs: dict[str, Any] = {"Bucket": bucket}
        if continuation_token:
            kwargs["ContinuationToken"] = continuation_token

        response = client.list_objects_v2(**kwargs)
        contents = response.get("Contents") or []
        for item in contents:
            key = str(item.get("Key", ""))
            if key.lower().endswith(".pdf"):
                keys.append(key)

        if response.get("IsTruncated"):
            continuation_token = response.get("NextContinuationToken")
            continue
        break

    return keys
