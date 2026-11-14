import asyncio
import logging
from datetime import date
from typing import Any

import httpx

from app.core.errors import CollegeAPIError

logger = logging.getLogger(__name__)

Json = Any


class CollegeClient:
    """Typed access to the provided KIT college system. All endpoint paths live here."""

    def __init__(
        self, base_url: str, participant_key: str, timeout: float, transport: httpx.AsyncBaseTransport | None = None
    ):
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"X-Participant-Key": participant_key, "Accept": "application/json"},
            timeout=timeout,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        params: dict[str, Any] | None = None,
        json: Json = None,
        idempotency_key: str | None = None,
        raw: bool = False,
    ) -> Json:
        headers: dict[str, str] = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        clean_params = {k: v for k, v in (params or {}).items() if v not in (None, "")}
        retries = 1 if method == "GET" else 0
        for attempt in range(retries + 1):
            try:
                response = await self._http.request(method, path, params=clean_params, json=json, headers=headers)
            except httpx.TimeoutException as exc:
                if attempt < retries:
                    continue
                raise CollegeAPIError("The college system is taking too long to respond.", upstream_status=504) from exc
            except httpx.HTTPError as exc:
                if attempt < retries:
                    await asyncio.sleep(0.3)
                    continue
                raise CollegeAPIError("The college system is not reachable right now.") from exc
            if response.status_code >= 500 and attempt < retries:
                await asyncio.sleep(0.3)
                continue
            return self._parse(response, raw)
        raise CollegeAPIError("The college system is not reachable right now.")

    @staticmethod
    def _parse(response: httpx.Response, raw: bool) -> Json:
        if response.status_code >= 400:
            code, message = None, f"College system returned {response.status_code}"
            try:
                err = response.json().get("error") or {}
                code, message = err.get("code"), err.get("message") or message
            except ValueError:
                pass
            logger.info(
                "College API %s %s -> %s %s",
                response.request.method,
                response.request.url.path,
                response.status_code,
                code,
            )
            raise CollegeAPIError(message, upstream_status=response.status_code, upstream_code=code)
        if raw:
            return response.content
        return response.json() if response.content else None

    # Public
    async def health(self) -> Json:
        return await self._request("GET", "/v1/health")

    async def today(self) -> Json:
        return await self._request("GET", "/v1/today")

    async def college(self) -> Json:
        return await self._request("GET", "/v1/college")

    async def courses(self) -> Json:
        return await self._request("GET", "/v1/courses")

    async def documents(self) -> Json:
        return await self._request("GET", "/v1/documents")

    async def document_file(self, document_id: int) -> bytes:
        return await self._request("GET", f"/v1/documents/{document_id}/file", raw=True)

    async def submit_admission(self, payload: dict, idempotency_key: str) -> Json:
        return await self._request("POST", "/v1/admissions/applications", json=payload, idempotency_key=idempotency_key)

    async def placement_drives(self) -> Json:
        return await self._request("GET", "/v1/placements/drives")

    # Auth
    async def login(self, login_id: str, password: str) -> Json:
        return await self._request("POST", "/v1/auth/login", json={"login_id": login_id, "password": password})

    async def me(self, token: str) -> Json:
        return await self._request("GET", "/v1/me", token=token)

    # Student
    async def academics(self, token: str) -> Json:
        return await self._request("GET", "/v1/me/academics", token=token)

    async def subjects(self, token: str) -> Json:
        return await self._request("GET", "/v1/me/subjects", token=token)

    async def timetable(self, token: str) -> Json:
        return await self._request("GET", "/v1/me/timetable", token=token)

    async def calendar(self, token: str, start: date | None = None, end: date | None = None) -> Json:
        params = {"from": start.isoformat() if start else None, "to": end.isoformat() if end else None}
        return await self._request("GET", "/v1/calendar", token=token, params=params)

    async def attendance(self, token: str) -> Json:
        return await self._request("GET", "/v1/me/attendance", token=token)

    async def attendance_sessions(
        self, token: str, subject: str | None = None, start: date | None = None, end: date | None = None
    ) -> Json:
        params = {
            "subject": subject,
            "from": start.isoformat() if start else None,
            "to": end.isoformat() if end else None,
        }
        return await self._request("GET", "/v1/me/attendance/sessions", token=token, params=params)

    async def my_requests(self, token: str) -> Json:
        return await self._request("GET", "/v1/me/requests", token=token)

    async def my_request(self, token: str, request_id: int) -> Json:
        return await self._request("GET", f"/v1/me/requests/{request_id}", token=token)

    async def create_request(self, token: str, payload: dict, idempotency_key: str) -> Json:
        return await self._request(
            "POST", "/v1/me/requests", token=token, json=payload, idempotency_key=idempotency_key
        )

    async def cancel_request(self, token: str, request_id: int) -> Json:
        return await self._request("POST", f"/v1/me/requests/{request_id}/cancel", token=token)

    async def register_placement(self, token: str, drive_id: int) -> Json:
        return await self._request("POST", f"/v1/placements/drives/{drive_id}/register", token=token)

    async def my_placements(self, token: str) -> Json:
        return await self._request("GET", "/v1/me/placements", token=token)

    # Teacher
    async def teacher_classes(self, token: str) -> Json:
        return await self._request("GET", "/v1/teacher/classes", token=token)

    async def teacher_requests(self, token: str, status: str | None = None) -> Json:
        return await self._request("GET", "/v1/teacher/requests", token=token, params={"status": status})

    async def class_attendance(self, token: str, class_id: int) -> Json:
        return await self._request("GET", f"/v1/teacher/classes/{class_id}/attendance", token=token)

    async def approve_request(self, token: str, request_id: int, comment: str | None) -> Json:
        body = {"comment": comment} if comment else None
        return await self._request("POST", f"/v1/teacher/requests/{request_id}/approve", token=token, json=body)

    async def reject_request(self, token: str, request_id: int, reason: str) -> Json:
        return await self._request(
            "POST", f"/v1/teacher/requests/{request_id}/reject", token=token, json={"reason": reason}
        )
