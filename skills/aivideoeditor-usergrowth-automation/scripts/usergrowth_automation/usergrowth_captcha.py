from __future__ import annotations


class UserGrowthCaptchaSolver:
    """UserGrowth 登录验证码识别器。"""

    def __init__(self) -> None:
        """初始化 ddddocr；未安装时给出清晰提示。"""
        try:
            import ddddocr
        except ImportError as exc:
            raise RuntimeError("需要先安装 ddddocr 才能自动识别登录验证码") from exc
        self._ocr = ddddocr.DdddOcr(show_ad=False)

    def solve(self, image_bytes: bytes) -> str:
        """识别图片验证码，并返回去掉首尾空白后的文本。"""
        return self._ocr.classification(image_bytes).strip()
