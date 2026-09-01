import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from ..auth.dependencies import get_current_official
from ..database import get_db
from ..services.manual_uploads import (
    ManualUploadError,
    get_dataset_spec,
    management_payload,
    max_upload_bytes,
    safe_filename,
    store_validated_upload,
    upload_root,
)
from ..services.operational_data import (
    batch_detail,
    current_data_summary,
    operational_batches,
)


router = APIRouter(
    prefix="/api/data-management",
    tags=["data-management"],
    dependencies=[Depends(get_current_official)],
)


@router.get("")
def get_data_management(db: Session = Depends(get_db)):
    """운영 반영 현황 + 업로드 스테이징 현황을 한 번에 내려준다.

    화면이 두 번 조회하지 않도록 합친다. ``current_data``와
    ``operational_batches``는 DB만, ``datasets``·``uploads``는 업로드
    디렉터리만 읽으므로 반영된 것과 대기 중인 것이 섞이지 않는다.
    """
    return {
        "current_data": current_data_summary(db),
        "operational_batches": operational_batches(db),
        **management_payload(),
    }


@router.get("/batches/{batch_key}")
def get_batch_detail(batch_key: str, db: Session = Depends(get_db)):
    """이력표에서 배치 한 건을 펼칠 때만 부른다.

    목록 조회에 붙이지 않는 이유는 배치마다 분기별 집계를 도는 비용이 있고,
    화면은 대개 한 건만 펼치기 때문이다.
    """
    detail = batch_detail(db, batch_key)
    if detail is None:
        raise HTTPException(status_code=404, detail="해당 적재 배치를 찾을 수 없습니다")
    return detail


@router.post("/uploads/{dataset_type}", status_code=201)
async def upload_manual_dataset(
    dataset_type: str,
    request: Request,
    filename: str = Query(..., min_length=1, max_length=255),
    official: dict = Depends(get_current_official),
):
    try:
        get_dataset_spec(dataset_type)
        safe_filename(dataset_type, filename)
    except ManualUploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    limit = max_upload_bytes()
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > limit:
                raise HTTPException(
                    status_code=413,
                    detail=f"파일 크기는 {limit // (1024 * 1024)}MB를 넘을 수 없습니다",
                )
        except ValueError:
            raise HTTPException(status_code=400, detail="Content-Length 형식이 올바르지 않습니다")

    root = upload_root()
    temp_root = root / ".tmp"
    temp_root.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    received = 0
    try:
        with tempfile.NamedTemporaryFile(dir=temp_root, delete=False) as handle:
            temporary_path = Path(handle.name)
            async for chunk in request.stream():
                received += len(chunk)
                if received > limit:
                    raise HTTPException(
                        status_code=413,
                        detail=f"파일 크기는 {limit // (1024 * 1024)}MB를 넘을 수 없습니다",
                    )
                handle.write(chunk)
        if received == 0:
            raise HTTPException(status_code=400, detail="파일이 비어 있습니다")
        manifest = store_validated_upload(
            dataset_type,
            filename,
            temporary_path,
            uploaded_by=str(official.get("username") or official.get("sub") or "official"),
            root=root,
        )
        temporary_path = None
        return manifest
    except ManualUploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        if temporary_path is not None and temporary_path.exists():
            os.unlink(temporary_path)
