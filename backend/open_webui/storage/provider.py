import contextlib
import errno
import hashlib
import json
import logging
import os
import shutil
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO, Iterator

from open_webui.config import (
    S3_ACCESS_KEY_ID,
    S3_BUCKET_NAME,
    S3_ENDPOINT_URL,
    S3_KEY_PREFIX,
    S3_REGION_NAME,
    S3_SECRET_ACCESS_KEY,
    S3_USE_ACCELERATE_ENDPOINT,
    S3_ADDRESSING_STYLE,
    GCS_BUCKET_NAME,
    GOOGLE_APPLICATION_CREDENTIALS_JSON,
    AZURE_STORAGE_ENDPOINT,
    AZURE_STORAGE_CONTAINER_NAME,
    AZURE_STORAGE_KEY,
    ENABLE_UPLOAD_DEDUPE,
    STORAGE_PROVIDER,
    UPLOAD_DEDUPE_MIN_SIZE,
    UPLOAD_DEDUPE_STRATEGY,
    UPLOAD_DIR,
)
from open_webui.constants import ERROR_MESSAGES
from open_webui.env import SRC_LOG_LEVELS
from open_webui.utils.optional_dependencies import (
    OptionalDependencyError,
    require_module,
)

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MAIN"])

UPLOAD_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class UploadFileResult:
    size: int
    path: str
    meta: dict[str, Any] = field(default_factory=dict)

    def __iter__(self) -> Iterator[int | str]:
        yield self.size
        yield self.path

    def __len__(self) -> int:
        return 2

    def __getitem__(self, index: int) -> int | str:
        if index == 0:
            return self.size
        if index == 1:
            return self.path
        raise IndexError(index)


def _write_upload_stream(
    file: BinaryIO, file_path: Path, *, calculate_hash: bool = True
) -> tuple[int, str | None]:
    file_size = 0
    digest = hashlib.sha256() if calculate_hash else None

    try:
        with file_path.open("wb") as output_file:
            while True:
                chunk = file.read(UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                output_file.write(chunk)
                file_size += len(chunk)
                if digest:
                    digest.update(chunk)
    except Exception:
        with contextlib.suppress(FileNotFoundError):
            file_path.unlink()
        raise

    if file_size == 0:
        with contextlib.suppress(FileNotFoundError):
            file_path.unlink()
        raise ValueError(ERROR_MESSAGES.EMPTY_CONTENT)

    return file_size, digest.hexdigest() if digest else None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while True:
            chunk = file.read(UPLOAD_CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except ValueError:
        return False


def _build_storage_meta(
    *,
    sha256: str,
    size: int,
    dedupe_strategy: str,
    linked: bool,
    canonical_file_id: str | None = None,
    fallback_reason: str | None = None,
) -> dict[str, Any]:
    dedupe: dict[str, Any] = {
        "strategy": dedupe_strategy,
        "linked": linked,
    }
    if canonical_file_id:
        dedupe["canonical_file_id"] = canonical_file_id
    if fallback_reason:
        dedupe["fallback_reason"] = fallback_reason

    return {
        "storage_sha256": sha256,
        "storage_size": size,
        "dedupe": dedupe,
    }


def _find_verified_local_dedupe_candidate(
    *,
    sha256: str,
    size: int,
    destination: Path,
    upload_dir: Path,
) -> tuple[str, Path] | None:
    from open_webui.models.files import Files

    for file in Files.get_files_by_storage_hash_and_size(sha256, size):
        if not file.path:
            continue

        candidate = Path(file.path)
        if not candidate.is_absolute():
            candidate = upload_dir / candidate.name

        if candidate == destination:
            continue
        if not _is_relative_to(candidate, upload_dir):
            continue
        if not candidate.is_file() or candidate.is_symlink():
            continue

        try:
            stat = candidate.stat()
        except OSError:
            continue
        if stat.st_size != size:
            continue
        if _sha256_file(candidate) != sha256:
            continue

        return file.id, candidate

    return None


class StorageProvider(ABC):
    @abstractmethod
    def get_file(self, file_path: str) -> str:
        pass

    @abstractmethod
    def upload_file(self, file: BinaryIO, filename: str) -> UploadFileResult:
        pass

    @abstractmethod
    def delete_all_files(self) -> None:
        pass

    @abstractmethod
    def delete_file(self, file_path: str) -> None:
        pass


class UnavailableStorageProvider(StorageProvider):
    def __init__(self, error: str):
        self.error = error

    def get_file(self, file_path: str) -> str:
        raise RuntimeError(self.error)

    def upload_file(self, file: BinaryIO, filename: str) -> UploadFileResult:
        raise RuntimeError(self.error)

    def delete_all_files(self) -> None:
        raise RuntimeError(self.error)

    def delete_file(self, file_path: str) -> None:
        raise RuntimeError(self.error)


class LocalStorageProvider(StorageProvider):
    @staticmethod
    def upload_file(
        file: BinaryIO, filename: str, dedupe: bool | None = None
    ) -> UploadFileResult:
        upload_dir = Path(UPLOAD_DIR)
        upload_dir.mkdir(parents=True, exist_ok=True)

        destination = upload_dir / filename
        should_dedupe = ENABLE_UPLOAD_DEDUPE if dedupe is None else dedupe
        if not should_dedupe:
            file_size, _sha256 = _write_upload_stream(
                file, destination, calculate_hash=False
            )
            return UploadFileResult(file_size, str(destination))

        incoming_dir = upload_dir / ".incoming"
        incoming_dir.mkdir(parents=True, exist_ok=True)
        temp_path = incoming_dir / f"{uuid.uuid4().hex}_{filename}"

        file_size, sha256 = _write_upload_stream(file, temp_path)
        if sha256 is None:
            with contextlib.suppress(FileNotFoundError):
                temp_path.unlink()
            raise RuntimeError("Upload hash calculation failed")

        meta = _build_storage_meta(
            sha256=sha256,
            size=file_size,
            dedupe_strategy=UPLOAD_DEDUPE_STRATEGY,
            linked=False,
        )

        if UPLOAD_DEDUPE_STRATEGY != "hardlink":
            log.warning(
                "Unsupported upload dedupe strategy %s; storing %s independently.",
                UPLOAD_DEDUPE_STRATEGY,
                destination,
            )
            meta = _build_storage_meta(
                sha256=sha256,
                size=file_size,
                dedupe_strategy=UPLOAD_DEDUPE_STRATEGY,
                linked=False,
                fallback_reason="unsupported_strategy",
            )
            should_dedupe = False
        else:
            should_dedupe = file_size >= UPLOAD_DEDUPE_MIN_SIZE

        if should_dedupe:
            candidate = _find_verified_local_dedupe_candidate(
                sha256=sha256,
                size=file_size,
                destination=destination,
                upload_dir=upload_dir,
            )
            if candidate:
                canonical_file_id, canonical_path = candidate
                try:
                    os.link(canonical_path, destination)
                    temp_path.unlink()
                    meta = _build_storage_meta(
                        sha256=sha256,
                        size=file_size,
                        dedupe_strategy="hardlink",
                        linked=True,
                        canonical_file_id=canonical_file_id,
                    )
                    return UploadFileResult(file_size, str(destination), meta)
                except OSError as exc:
                    if exc.errno == errno.EXDEV:
                        log.warning(
                            "Upload hardlink dedupe crossed filesystems; storing %s independently.",
                            destination,
                        )
                        meta = _build_storage_meta(
                            sha256=sha256,
                            size=file_size,
                            dedupe_strategy="hardlink",
                            linked=False,
                            fallback_reason="EXDEV",
                        )
                    else:
                        temp_path.unlink()
                        raise

        try:
            os.replace(temp_path, destination)
        except Exception:
            with contextlib.suppress(FileNotFoundError):
                temp_path.unlink()
            raise

        return UploadFileResult(file_size, str(destination), meta)

    @staticmethod
    def get_file(file_path: str) -> str:
        """Handles downloading of the file from local storage."""
        return file_path

    @staticmethod
    def delete_file(file_path: str) -> None:
        """Handles deletion of the file from local storage."""
        filename = file_path.split("/")[-1]
        file_path = f"{UPLOAD_DIR}/{filename}"
        if os.path.isfile(file_path):
            os.remove(file_path)
        else:
            log.warning(f"File {file_path} not found in local storage.")

    @staticmethod
    def delete_all_files() -> None:
        """Handles deletion of all files from local storage."""
        if os.path.exists(UPLOAD_DIR):
            for filename in os.listdir(UPLOAD_DIR):
                file_path = os.path.join(UPLOAD_DIR, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)  # Remove the file or link
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)  # Remove the directory
                except Exception as e:
                    log.exception(f"Failed to delete {file_path}. Reason: {e}")
        else:
            log.warning(f"Directory {UPLOAD_DIR} not found in local storage.")


class S3StorageProvider(StorageProvider):
    def __init__(self):
        boto3 = require_module(
            "boto3",
            feature="S3 storage provider",
            packages=["boto3", "botocore"],
            install_profiles=["storage-cloud", "full"],
        )
        botocore_config = require_module(
            "botocore.config",
            feature="S3 storage provider",
            packages=["boto3", "botocore"],
            install_profiles=["storage-cloud", "full"],
        )
        botocore_exceptions = require_module(
            "botocore.exceptions",
            feature="S3 storage provider",
            packages=["boto3", "botocore"],
            install_profiles=["storage-cloud", "full"],
        )

        config = botocore_config.Config(
            s3={
                "use_accelerate_endpoint": S3_USE_ACCELERATE_ENDPOINT,
                "addressing_style": S3_ADDRESSING_STYLE,
            },
        )
        self.client_error = botocore_exceptions.ClientError

        # If access key and secret are provided, use them for authentication
        if S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY:
            self.s3_client = boto3.client(
                "s3",
                region_name=S3_REGION_NAME,
                endpoint_url=S3_ENDPOINT_URL,
                aws_access_key_id=S3_ACCESS_KEY_ID,
                aws_secret_access_key=S3_SECRET_ACCESS_KEY,
                config=config,
            )
        else:
            # If no explicit credentials are provided, fall back to default AWS credentials
            # This supports workload identity (IAM roles for EC2, EKS, etc.)
            self.s3_client = boto3.client(
                "s3",
                region_name=S3_REGION_NAME,
                endpoint_url=S3_ENDPOINT_URL,
                config=config,
            )

        self.bucket_name = S3_BUCKET_NAME
        self.key_prefix = S3_KEY_PREFIX if S3_KEY_PREFIX else ""

    def upload_file(self, file: BinaryIO, filename: str) -> UploadFileResult:
        """Handles uploading of the file to S3 storage."""
        local_result = LocalStorageProvider.upload_file(file, filename, dedupe=False)
        try:
            s3_key = os.path.join(self.key_prefix, filename)
            self.s3_client.upload_file(local_result.path, self.bucket_name, s3_key)
            return UploadFileResult(
                local_result.size,
                "s3://" + self.bucket_name + "/" + s3_key,
                local_result.meta,
            )
        except self.client_error as e:
            raise RuntimeError(f"Error uploading file to S3: {e}")

    def get_file(self, file_path: str) -> str:
        """Handles downloading of the file from S3 storage."""
        try:
            s3_key = self._extract_s3_key(file_path)
            local_file_path = self._get_local_file_path(s3_key)
            self.s3_client.download_file(self.bucket_name, s3_key, local_file_path)
            return local_file_path
        except self.client_error as e:
            raise RuntimeError(f"Error downloading file from S3: {e}")

    def delete_file(self, file_path: str) -> None:
        """Handles deletion of the file from S3 storage."""
        try:
            s3_key = self._extract_s3_key(file_path)
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=s3_key)
        except self.client_error as e:
            raise RuntimeError(f"Error deleting file from S3: {e}")

        # Always delete from local storage
        LocalStorageProvider.delete_file(file_path)

    def delete_all_files(self) -> None:
        """Handles deletion of all files from S3 storage."""
        try:
            response = self.s3_client.list_objects_v2(Bucket=self.bucket_name)
            if "Contents" in response:
                for content in response["Contents"]:
                    # Skip objects that were not uploaded from open-webui in the first place
                    if not content["Key"].startswith(self.key_prefix):
                        continue

                    self.s3_client.delete_object(
                        Bucket=self.bucket_name, Key=content["Key"]
                    )
        except self.client_error as e:
            raise RuntimeError(f"Error deleting all files from S3: {e}")

        # Always delete from local storage
        LocalStorageProvider.delete_all_files()

    # The s3 key is the name assigned to an object. It excludes the bucket name, but includes the internal path and the file name.
    def _extract_s3_key(self, full_file_path: str) -> str:
        return "/".join(full_file_path.split("//")[1].split("/")[1:])

    def _get_local_file_path(self, s3_key: str) -> str:
        return f"{UPLOAD_DIR}/{s3_key.split('/')[-1]}"


class GCSStorageProvider(StorageProvider):
    def __init__(self):
        google_storage = require_module(
            "google.cloud.storage",
            feature="Google Cloud Storage provider",
            packages=["google-cloud-storage"],
            install_profiles=["storage-cloud", "full"],
        )
        google_exceptions = require_module(
            "google.cloud.exceptions",
            feature="Google Cloud Storage provider",
            packages=["google-cloud-storage"],
            install_profiles=["storage-cloud", "full"],
        )

        self.bucket_name = GCS_BUCKET_NAME
        self.google_cloud_error = google_exceptions.GoogleCloudError
        self.not_found_error = google_exceptions.NotFound

        if GOOGLE_APPLICATION_CREDENTIALS_JSON:
            self.gcs_client = google_storage.Client.from_service_account_info(
                info=json.loads(GOOGLE_APPLICATION_CREDENTIALS_JSON)
            )
        else:
            # if no credentials json is provided, credentials will be picked up from the environment
            # if running on local environment, credentials would be user credentials
            # if running on a Compute Engine instance, credentials would be from Google Metadata server
            self.gcs_client = google_storage.Client()
        self.bucket = self.gcs_client.bucket(GCS_BUCKET_NAME)

    def upload_file(self, file: BinaryIO, filename: str) -> UploadFileResult:
        """Handles uploading of the file to GCS storage."""
        local_result = LocalStorageProvider.upload_file(file, filename, dedupe=False)
        try:
            blob = self.bucket.blob(filename)
            blob.upload_from_filename(local_result.path)
            return UploadFileResult(
                local_result.size,
                "gs://" + self.bucket_name + "/" + filename,
                local_result.meta,
            )
        except self.google_cloud_error as e:
            raise RuntimeError(f"Error uploading file to GCS: {e}")

    def get_file(self, file_path: str) -> str:
        """Handles downloading of the file from GCS storage."""
        try:
            filename = file_path.removeprefix("gs://").split("/")[1]
            local_file_path = f"{UPLOAD_DIR}/{filename}"
            blob = self.bucket.get_blob(filename)
            blob.download_to_filename(local_file_path)

            return local_file_path
        except self.not_found_error as e:
            raise RuntimeError(f"Error downloading file from GCS: {e}")

    def delete_file(self, file_path: str) -> None:
        """Handles deletion of the file from GCS storage."""
        try:
            filename = file_path.removeprefix("gs://").split("/")[1]
            blob = self.bucket.get_blob(filename)
            blob.delete()
        except self.not_found_error as e:
            raise RuntimeError(f"Error deleting file from GCS: {e}")

        # Always delete from local storage
        LocalStorageProvider.delete_file(file_path)

    def delete_all_files(self) -> None:
        """Handles deletion of all files from GCS storage."""
        try:
            blobs = self.bucket.list_blobs()

            for blob in blobs:
                blob.delete()

        except self.not_found_error as e:
            raise RuntimeError(f"Error deleting all files from GCS: {e}")

        # Always delete from local storage
        LocalStorageProvider.delete_all_files()


class AzureStorageProvider(StorageProvider):
    def __init__(self):
        azure_identity = require_module(
            "azure.identity",
            feature="Azure Blob Storage provider",
            packages=["azure-storage-blob", "azure-identity"],
            install_profiles=["storage-cloud", "full"],
        )
        azure_blob = require_module(
            "azure.storage.blob",
            feature="Azure Blob Storage provider",
            packages=["azure-storage-blob", "azure-identity"],
            install_profiles=["storage-cloud", "full"],
        )
        azure_exceptions = require_module(
            "azure.core.exceptions",
            feature="Azure Blob Storage provider",
            packages=["azure-storage-blob", "azure-identity"],
            install_profiles=["storage-cloud", "full"],
        )

        self.endpoint = AZURE_STORAGE_ENDPOINT
        self.container_name = AZURE_STORAGE_CONTAINER_NAME
        storage_key = AZURE_STORAGE_KEY
        self.resource_not_found_error = azure_exceptions.ResourceNotFoundError

        if storage_key:
            # Configure using the Azure Storage Account Endpoint and Key
            self.blob_service_client = azure_blob.BlobServiceClient(
                account_url=self.endpoint, credential=storage_key
            )
        else:
            # Configure using the Azure Storage Account Endpoint and DefaultAzureCredential
            # If the key is not configured, then the DefaultAzureCredential will be used to support Managed Identity authentication
            self.blob_service_client = azure_blob.BlobServiceClient(
                account_url=self.endpoint,
                credential=azure_identity.DefaultAzureCredential(),
            )
        self.container_client = self.blob_service_client.get_container_client(
            self.container_name
        )

    def upload_file(self, file: BinaryIO, filename: str) -> UploadFileResult:
        """Handles uploading of the file to Azure Blob Storage."""
        local_result = LocalStorageProvider.upload_file(file, filename, dedupe=False)
        try:
            blob_client = self.container_client.get_blob_client(filename)
            with open(local_result.path, "rb") as upload_file:
                blob_client.upload_blob(upload_file, overwrite=True)
            return UploadFileResult(
                local_result.size,
                f"{self.endpoint}/{self.container_name}/{filename}",
                local_result.meta,
            )
        except Exception as e:
            raise RuntimeError(f"Error uploading file to Azure Blob Storage: {e}")

    def get_file(self, file_path: str) -> str:
        """Handles downloading of the file from Azure Blob Storage."""
        try:
            filename = file_path.split("/")[-1]
            local_file_path = f"{UPLOAD_DIR}/{filename}"
            blob_client = self.container_client.get_blob_client(filename)
            with open(local_file_path, "wb") as download_file:
                download_file.write(blob_client.download_blob().readall())
            return local_file_path
        except self.resource_not_found_error as e:
            raise RuntimeError(f"Error downloading file from Azure Blob Storage: {e}")

    def delete_file(self, file_path: str) -> None:
        """Handles deletion of the file from Azure Blob Storage."""
        try:
            filename = file_path.split("/")[-1]
            blob_client = self.container_client.get_blob_client(filename)
            blob_client.delete_blob()
        except self.resource_not_found_error as e:
            raise RuntimeError(f"Error deleting file from Azure Blob Storage: {e}")

        # Always delete from local storage
        LocalStorageProvider.delete_file(file_path)

    def delete_all_files(self) -> None:
        """Handles deletion of all files from Azure Blob Storage."""
        try:
            blobs = self.container_client.list_blobs()
            for blob in blobs:
                self.container_client.delete_blob(blob.name)
        except Exception as e:
            raise RuntimeError(f"Error deleting all files from Azure Blob Storage: {e}")

        # Always delete from local storage
        LocalStorageProvider.delete_all_files()


def get_storage_provider(storage_provider: str):
    try:
        if storage_provider == "local":
            storage = LocalStorageProvider()
        elif storage_provider == "s3":
            storage = S3StorageProvider()
        elif storage_provider == "gcs":
            storage = GCSStorageProvider()
        elif storage_provider == "azure":
            storage = AzureStorageProvider()
        else:
            raise RuntimeError(f"Unsupported storage provider: {storage_provider}")
        return storage
    except OptionalDependencyError as exc:
        log.warning("%s", exc)
        return UnavailableStorageProvider(str(exc))


Storage = get_storage_provider(STORAGE_PROVIDER)
