import logging
import os
import tempfile
import time
import zipfile
from typing import List, Optional

import requests
from fastapi import HTTPException, status
from langchain_core.documents import Document

log = logging.getLogger(__name__)


class MinerULoader:
    def __init__(
        self,
        file_path: str,
        api_mode: str = "local",
        api_url: str = "http://localhost:8000",
        api_key: str = "",
        params: dict = None,
        timeout: Optional[int] = 300,
    ):
        self.file_path = file_path
        self.api_mode = api_mode.lower()
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.params = params or {}
        self.enable_ocr = self.params.get("enable_ocr", False)
        self.page_ranges = self.params.pop("page_ranges", "")

        if self.api_mode not in ["local", "cloud"]:
            raise ValueError(
                f"Invalid API mode: {self.api_mode}. Must be 'local' or 'cloud'"
            )
        if self.api_mode == "cloud" and not self.api_key:
            raise ValueError("API key is required for Cloud API mode")

    def load(self) -> List[Document]:
        if self.api_mode == "cloud":
            return self._load_cloud_api()
        return self._load_local_api()

    def _load_local_api(self) -> List[Document]:
        filename = os.path.basename(self.file_path)
        form_data = {**self.params, "return_md": "true"}

        try:
            with open(self.file_path, "rb") as file_handle:
                files = {"files": (filename, file_handle, "application/octet-stream")}
                response = requests.post(
                    f"{self.api_url}/file_parse",
                    data=form_data,
                    files=files,
                    timeout=self.timeout,
                )
                response.raise_for_status()
        except FileNotFoundError:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail=f"File not found: {self.file_path}"
            )
        except requests.Timeout:
            raise HTTPException(
                status.HTTP_504_GATEWAY_TIMEOUT,
                detail="MinerU Local API request timed out",
            )
        except requests.HTTPError as exc:
            error_detail = f"MinerU Local API request failed: {exc}"
            if exc.response is not None:
                try:
                    error_detail += f" - {exc.response.json()}"
                except Exception:
                    error_detail += f" - {exc.response.text}"
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, detail=error_detail
            ) from exc

        try:
            result = response.json()
        except ValueError as exc:
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY,
                detail=f"Invalid JSON response from MinerU Local API: {exc}",
            ) from exc

        results = result.get("results")
        if not results:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="MinerU returned empty results",
            )

        file_result = list(results.values())[0]
        markdown_content = file_result.get("md_content", "")
        if not markdown_content:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="MinerU returned empty markdown content",
            )

        return [
            Document(
                page_content=markdown_content,
                metadata={
                    "source": filename,
                    "api_mode": "local",
                    "backend": result.get("backend", "unknown"),
                    "version": result.get("version", "unknown"),
                },
            )
        ]

    def _load_cloud_api(self) -> List[Document]:
        filename = os.path.basename(self.file_path)
        batch_id, upload_url = self._request_upload_url(filename)
        self._upload_to_presigned_url(upload_url)
        result = self._poll_batch_status(batch_id, filename)
        markdown_content = self._download_and_extract_zip(
            result["full_zip_url"], filename
        )

        return [
            Document(
                page_content=markdown_content,
                metadata={
                    "source": filename,
                    "api_mode": "cloud",
                    "batch_id": batch_id,
                },
            )
        ]

    def _request_upload_url(self, filename: str) -> tuple[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        request_body = {
            **self.params,
            "files": [{"name": filename, "is_ocr": self.enable_ocr}],
        }
        if self.page_ranges:
            request_body["files"][0]["page_ranges"] = self.page_ranges

        try:
            response = requests.post(
                f"{self.api_url}/file-urls/batch",
                headers=headers,
                json=request_body,
                timeout=30,
            )
            response.raise_for_status()
            result = response.json()
        except Exception as exc:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to request upload URL: {exc}",
            ) from exc

        if result.get("code") != 0:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f'MinerU Cloud API error: {result.get("msg", "Unknown error")}',
            )

        data = result.get("data", {})
        batch_id = data.get("batch_id")
        file_urls = data.get("file_urls", [])
        if not batch_id or not file_urls:
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY,
                detail="MinerU Cloud API response missing batch_id or file_urls",
            )

        return batch_id, file_urls[0]

    def _upload_to_presigned_url(self, upload_url: str) -> None:
        try:
            with open(self.file_path, "rb") as file_handle:
                response = requests.put(
                    upload_url, data=file_handle, timeout=self.timeout
                )
                response.raise_for_status()
        except Exception as exc:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to upload file to presigned URL: {exc}",
            ) from exc

    def _poll_batch_status(self, batch_id: str, filename: str) -> dict:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        poll_url = f"{self.api_url}/extract-results/batch/{batch_id}"
        start_time = time.time()

        while time.time() - start_time < self.timeout:
            try:
                response = requests.get(poll_url, headers=headers, timeout=30)
                response.raise_for_status()
                result = response.json()
            except Exception as exc:
                raise HTTPException(
                    status.HTTP_502_BAD_GATEWAY,
                    detail=f"Failed to poll batch status: {exc}",
                ) from exc

            if result.get("code") != 0:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail=f'MinerU Cloud API error: {result.get("msg", "Unknown error")}',
                )

            extract_results = result.get("data", {}).get("extract_result", [])
            if extract_results:
                for item in extract_results:
                    if item.get("file_name") == filename:
                        state = item.get("state")
                        if state == "done":
                            return item
                        if state == "failed":
                            raise HTTPException(
                                status.HTTP_400_BAD_REQUEST,
                                detail=f'MinerU processing failed: {item.get("err_msg", "Unknown error")}',
                            )
            time.sleep(2)

        raise HTTPException(
            status.HTTP_504_GATEWAY_TIMEOUT,
            detail="MinerU processing timed out",
        )

    def _download_and_extract_zip(self, zip_url: str, filename: str) -> str:
        try:
            response = requests.get(zip_url, timeout=60)
            response.raise_for_status()
        except Exception as exc:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to download result ZIP: {exc}",
            ) from exc

        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as temp_zip:
            temp_zip.write(response.content)
            temp_zip_path = temp_zip.name

        try:
            with zipfile.ZipFile(temp_zip_path, "r") as zip_ref:
                markdown_files = [
                    name for name in zip_ref.namelist() if name.endswith(".md")
                ]
                if not markdown_files:
                    raise HTTPException(
                        status.HTTP_502_BAD_GATEWAY,
                        detail="No markdown file found in MinerU result ZIP",
                    )
                with zip_ref.open(markdown_files[0]) as md_file:
                    markdown_content = md_file.read().decode("utf-8")
        finally:
            try:
                os.remove(temp_zip_path)
            except OSError:
                pass

        return markdown_content
