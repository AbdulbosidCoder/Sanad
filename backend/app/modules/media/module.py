"""Self-description of the `media` module (see app/core/modules.py)."""

from app.core.modules import ModuleInfo
from app.modules.media.api import router

MODULE = ModuleInfo(
    name="media",
    summary="Загрузка файлов в S3: presigned URL, проверка типа, ресайз изображений.",
    router=router,
    depends_on=(),
    emits=("MediaUploaded",),
    listens_to=(),
    tables=("media_files",),
)
