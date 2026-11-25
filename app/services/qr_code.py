from io import BytesIO
from typing import Literal
from urllib.parse import urlencode

import qrcode
from qrcode.image.svg import SvgPathImage

from app.core.config import settings


class QRCodeService:
    @staticmethod
    def build_target_url(
        *,
        source_name: str,
        page: Literal["apply", "register"] = "apply",
        ref: str | None = None,
        base_url: str | None = None,
    ) -> str:
        root = (base_url or settings.frontend_base_url).rstrip("/")
        clean_page = page.strip("/")
        params: dict[str, str] = {"source": source_name}
        if ref and ref.strip():
            params["ref"] = ref.strip().upper()
        return f"{root}/{clean_page}?{urlencode(params)}"

    @staticmethod
    def generate_png(*, url: str, box_size: int = 12, border: int = 2) -> bytes:
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=box_size,
            border=border,
        )
        qr.add_data(url)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        return buffer.getvalue()

    @staticmethod
    def generate_svg(*, url: str, box_size: int = 12, border: int = 2) -> bytes:
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=box_size,
            border=border,
            image_factory=SvgPathImage,
        )
        qr.add_data(url)
        qr.make(fit=True)

        img = qr.make_image()
        buffer = BytesIO()
        img.save(buffer)
        return buffer.getvalue()
