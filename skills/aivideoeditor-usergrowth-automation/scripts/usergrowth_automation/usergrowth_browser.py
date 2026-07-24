from __future__ import annotations

import asyncio
import re
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

from .usergrowth_captcha import UserGrowthCaptchaSolver
from .usergrowth_models import UserGrowthCancelled, UserGrowthOrderPlan, UserGrowthVideoItem
from .usergrowth_rules import display_material_from_label

ProgressCallback = Callable[[str], None]
OrderCompleteCallback = Callable[[UserGrowthOrderPlan], None]


def _compact_text(value: str) -> str:
    """去掉空白字符，便于比较中文 UI 文案"""
    return re.sub(r"[\s\u00a0]+", "", value or "")


def _compact_cascader_text(value: str) -> str:
    return re.sub(r"[\s\u00a0_]+", "", value or "")


def card_defaults_for_item(item: UserGrowthVideoItem) -> tuple[list[str], list[str]]:
    """返回计划阶段确定的分类和标签，避免浏览器阶段按文件名重新推导。"""
    classification_path = [str(value).strip() for value in item.classification_path if str(value).strip()]
    if not classification_path:
        raise RuntimeError(f"素材缺少已规划的分类标签：{item.file_name}")
    return ["LUNA功能卖点", *classification_path], list(item.custom_tags)


LOGIN_URL = "https://usergrowth.com.cn/open/login"
HOME_URL = "https://usergrowth.com.cn/home"

# 操作速度
USERGROWTH_OPERATION_SPEED_FACTOR = 1.0

# 投放信息弹窗选择器：定位 Arco Modal / Dialog / Drawer 等弹窗容器
DELIVERY_MODAL_SELECTOR = ".arco-modal, .arco-modal-content, [role='dialog'], .arco-drawer"
# 表单项选择器：定位包含字段标签和控件的表单行item
FORM_ITEM_SELECTOR = ".arco-form-item, [class*='form-item']"
# 下拉选择控件选择器：定位可点击打开下拉菜单的 Select/Cascader/InputTag 输入区域
SELECT_CONTROL_SELECTOR = (
    ".arco-select-view, .arco-cascader-view, .arco-input-tag, .arco-input-tag-view, "
    "[class*='select-view'], [class*='cascader-view'], [class*='input-tag']"
)
# 下拉菜单容器选择器：定位点击 Select 后展开的选项列表
DROPDOWN_ROOT_SELECTOR = ".arco-trigger-popup, .arco-select-dropdown, .arco-cascader-popup, [role='listbox']"
# 下拉选项元素
DROPDOWN_OPTION_SELECTOR = ".arco-select-option, .arco-cascader-option, [role='option']"


class UserGrowthBrowserClient:
    """封装 UserGrowth 平台从登录到上传、录入变色龙、送审、回填 CID 的浏览器流程。"""

    def __init__(
            self,
            account: str,
            password: str,
            *,
            headless: bool = False,
            debug_dir: Path | None = None,
            timeout_ms: int = 45000,
            refresh_interval_seconds: float = 12.0,
            max_status_retries: int = 3,
            browser_slow_mo_ms: int = 600,
            order_complete: OrderCompleteCallback | None = None,
            cancel_event: threading.Event | None = None,
    ) -> None:
        """保存浏览器自动化运行参数。"""
        self.account = account
        self.password = password
        self.headless = headless
        self.debug_dir = debug_dir
        self.timeout_ms = timeout_ms
        self.refresh_interval_seconds = refresh_interval_seconds
        self.max_status_retries = max_status_retries
        self.browser_slow_mo_ms = browser_slow_mo_ms
        self.order_complete = order_complete
        self.cancel_event = cancel_event
        self.operation_speed_factor = max(float(USERGROWTH_OPERATION_SPEED_FACTOR or 1.0), 0.1)
        self._captcha_solver: UserGrowthCaptchaSolver | None = None

    async def run(self, plans: list[UserGrowthOrderPlan], progress: ProgressCallback | None = None) -> None:
        """启动浏览器并按订单计划逐单处理上传流程。"""
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise RuntimeError("需要先安装 playwright，并执行 playwright install chromium") from exc

        start_time = time.perf_counter()
        start_ts = datetime.now().isoformat(timespec="seconds")
        self._write_run_log(
            f"[{start_ts}] run start, plans={len(plans)}"
        )

        self._raise_if_cancelled()
        async with async_playwright() as playwright:
            browser = await self._launch_browser(playwright)
            cancel_task = asyncio.create_task(self._watch_cancel(browser, progress))
            context = await browser.new_context(viewport={"width": 1440, "height": 1000})
            page = await context.new_page()
            self._wrap_page_speed(page)
            page.set_default_timeout(self.timeout_ms)
            try:
                self._raise_if_cancelled()
                await self._snapshot(page, "00_browser_created")
                await self._login(page, progress)
                await self._enable_post_login_resource_blocking(context, progress)
                await self._snapshot(page, "02_after_login")
                for plan in plans:
                    self._raise_if_cancelled()
                    if plan.status == "skipped":
                        continue
                    await self._process_order(page, plan, progress)
                    if self.order_complete and plan.status == "success":
                        self.order_complete(plan)
            except Exception as exc:
                if self._cancel_requested():
                    raise UserGrowthCancelled("任务已取消") from exc
                raise
            finally:
                cancel_task.cancel()
                try:
                    await cancel_task
                except asyncio.CancelledError:
                    pass
                elapsed = time.perf_counter() - start_time
                end_ts = datetime.now().isoformat(timespec="seconds")
                self._write_run_log(
                    f"[{end_ts}] run finished, elapsed={elapsed:.2f}s, "
                    f"plans={len(plans)}"
                )
                try:
                    await browser.close()
                except Exception:
                    pass

    def _write_run_log(self, message: str) -> None:
        """把流程级别的计时日志追加到 run.log。

        debug_dir 不为空时写到 debug_dir/run.log，否则写到当前目录 run.log。
        """
        log_path = (
            (self.debug_dir / "run.log")
            if self.debug_dir
            else Path("run.log")
        )
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        try:
            with open(log_path, "a", encoding="utf-8") as fp:
                fp.write(message + "\n")
        except Exception as exc:
            print(f"[run.log] 写入失败: {exc}")

    async def _launch_browser(self, playwright):
        """用本机 Edge/Chrome 启动浏览器；首选 Edge，失败时回退到 Chrome。"""
        last_error: Exception | None = None
        for channel in ("msedge", "chrome"):
            try:
                return await playwright.chromium.launch(
                    channel=channel, headless=self.headless, slow_mo=self._scale_ms(self.browser_slow_mo_ms)
                )
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                continue
        raise RuntimeError(f"启动浏览器失败：{last_error}")

    async def _login(self, page, progress: ProgressCallback | None) -> None:
        """打开登录页，填写账号密码并自动识别图片验证码。"""
        self._emit(progress, "打开 UserGrowth 登录页")
        await self._safe_goto(page, LOGIN_URL)
        await self._snapshot(page, "01_open_login")
        if await self._looks_logged_in(page):
            self._emit(progress, "当前浏览器上下文已登录")
            return

        for attempt in range(1, 6):
            self._emit(progress, f"填写账号密码并识别验证码，第 {attempt} 次")
            await self._fill_first(
                page,
                (
                    "input[placeholder='请输入注册邮箱']",
                    "input[type='text']",
                ),
                self.account,
            )
            await self._fill_first(page, ("input[type='password']", "input[placeholder*='密码']"), self.password)
            await self._fill_captcha(page)
            await self._snapshot(page, f"login_attempt_{attempt}_filled")
            await self._click_first(page, ("button:has-text('登录')", "button:has-text('登 录')", "button"))
            await page.wait_for_timeout(5000)
            await self._safe_goto(page, HOME_URL)
            await page.wait_for_timeout(2500)
            if await self._looks_logged_in(page):
                self._emit(progress, "登录成功")
                return
            await self._snapshot_error(page, f"login_failed_{attempt}")
        raise RuntimeError("UserGrowth 登录失败：验证码或账号密码未通过")

    async def _enable_post_login_resource_blocking(self, context, progress: ProgressCallback | None = None) -> None:
        """登录后拦截非必要静态资源，降低后续页面加载成本。"""

        async def handle_route(route) -> None:
            if self._should_block_static_resource(route.request):
                await route.abort()
                return
            await route.continue_()

        await context.route("**/*", handle_route)
        self._emit(progress, "已开启登录后静态资源拦截：图片、字体、favicon")

    @staticmethod
    def _should_block_static_resource(request) -> bool:
        """判断登录后的请求是否属于可拦截静态资源。"""
        resource_type = getattr(request, "resource_type", "")
        if resource_type in {"image", "font"}:
            return True
        url = str(getattr(request, "url", "") or "").lower()
        return "favicon.ico" in url

    async def _looks_logged_in(self, page) -> bool:
        """根据 URL 和页面文本判断当前是否已登录。"""
        if "/home" in page.url:
            return True
        try:
            body = await page.locator("body").inner_text(timeout=5000)
        except Exception:
            return False
        return "墨攻AI" in body or "采购中心" in body

    async def _fill_captcha(self, page) -> None:
        """查找验证码输入框和验证码图片，并把识别结果填入输入框。"""
        captcha_input = await self._first_existing(
            page,
            (
                "input[placeholder='请输入图片验证码']",
            ),
        )
        if not captcha_input:
            return

        captcha_image = await self._find_captcha_image(page, captcha_input)
        self._captcha_solver = self._captcha_solver or UserGrowthCaptchaSolver()
        code = self._captcha_solver.solve(await captcha_image.screenshot())
        await captcha_input.fill(code)

    async def _find_captcha_image(self, page, captcha_input=None):
        """在登录页图片中选出最像验证码的图片元素。"""
        images = page.locator("img")
        count = await images.count()
        if not count:
            return None
        # 输入框中心坐标；拿不到就退化成"只比面积"
        cx, cy = None, None
        if captcha_input:
            try:
                box = await captcha_input.bounding_box()
                if box:
                    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
            except Exception:
                pass
        # 一次遍历：尺寸合规 + 离输入框最近，分最高的就是验证码
        best, best_score = None, -1
        for i in range(count):
            try:
                box = await images.nth(i).bounding_box()
                if not box or not (50 <= box["width"] <= 260 and 20 <= box["height"] <= 100):
                    continue
                score = box["width"] * box["height"]
                if cx is not None:
                    score -= abs(box["x"] + box["width"] / 2 - cx) * 2
                    score -= abs(box["y"] + box["height"] / 2 - cy) * 6
                if score > best_score:
                    best, best_score = images.nth(i), score
            except Exception:
                continue
        if best:
            return best
        # 兜底：尺寸没一个合规的，从后往前拿第一个可见图片
        for i in range(count - 1, -1, -1):
            try:
                if await images.nth(i).is_visible():
                    return images.nth(i)
            except Exception:
                continue
        return None

    async def _process_order(self, page, plan: UserGrowthOrderPlan, progress: ProgressCallback | None) -> None:
        """处理单个订单：进入工单、上传素材、录入变色龙、送审并读取 CID。"""
        active_items = [item for item in plan.items if item.status != "skipped"]
        if not active_items:
            plan.status = "skipped"
            plan.message = "没有可上传素材"
            return

        self._emit(progress, f"处理订单 {plan.order_id}，素材 {len(active_items)} 个")
        try:
            self._raise_if_cancelled()
            await self._open_work_order_management(page, progress)
            await self._search_order(page, plan.order_id)
            page = await self._open_create_creative_unit(page, plan.order_id)
            await self._snapshot(page, f"order_{plan.order_id}_after_create")
            limit = await self._read_upload_limit(page)
            plan.upload_limit = limit
            if limit is not None and len(active_items) > limit:
                plan.status = "skipped"
                plan.message = f"超过页面上传限制：最多 {limit} 个，实际 {len(active_items)} 个"
                for item in active_items:
                    item.status = "skipped"
                    item.message = plan.message
                return
            page = await self._upload_and_enter_chameleon_with_retry(page, plan, active_items, progress)
            plan.task_id = await self._read_current_task_id(page)
            if not plan.task_id:
                await self._snapshot_error(page, f"order_{plan.order_id}_task_id_not_found")
                raise RuntimeError("未读取到当前任务ID")

            await self._wait_task_success(page, progress, expected_attempts=max(len(active_items), 1))
            await self._submit_review(page)
            await self._fill_cids_for_task(page, active_items, plan.task_id, progress)
            plan.status = "success"
            plan.message = "处理完成"
        except UserGrowthCancelled as exc:
            plan.status = "cancelled"
            plan.message = str(exc) or "任务已取消"
            for item in active_items:
                if item.status not in {"success", "skipped"}:
                    item.status = "cancelled"
                    item.message = plan.message
            raise
        except Exception as exc:  # noqa: BLE001
            plan.status = "failed"
            plan.message = str(exc)
            await self._snapshot_error(
                page,
                f"order_{plan.order_id}_failed",
                exc=exc,
                extra=f"order_id={plan.order_id}, items={len(active_items)}",
            )
            for item in active_items:
                if item.status not in {"success", "skipped"}:
                    item.status = "failed"
                    item.message = str(exc)

    async def _upload_and_enter_chameleon_with_retry(
            self,
            page,
            plan: UserGrowthOrderPlan,
            items: list[UserGrowthVideoItem],
            progress: ProgressCallback | None,
    ):
        """上传素材并进入变色龙；平台初始化上传失败时刷新上传页后自动重试。"""
        upload_url = page.url
        for attempt in range(1, self.max_status_retries + 1):
            self._emit(progress, f"上传订单 {plan.order_id} 素材，第 {attempt} 次")
            if attempt > 1:
                await self._reset_upload_page(page, upload_url, plan.order_id, attempt)
            # 内部失败时会刷新页面并从「新建创意单元」入口重新走，
            # 拿到最终的 page（可能是新 tab）继续后续流程
            page = await self._upload_files(page, items, plan.order_id)
            try:
                return await self._enter_chameleon(page, items, progress)
            except Exception as exc:
                is_last = attempt >= self.max_status_retries
                if not self._is_upload_transient_failure(str(exc)) or is_last:
                    raise
                await self._snapshot_error(
                    page,
                    f"upload_retry_{attempt}_failed",
                    exc=exc,
                )
                self._emit(progress, f"上传初始化失败，准备重试第 {attempt + 1} 次")
                await page.wait_for_timeout(2500)
        raise RuntimeError("上传素材失败")

    async def _reset_upload_page(self, page, upload_url: str, order_id: str, attempt: int) -> None:
        """重试上传前回到干净的创意单元上传页。"""
        try:
            await self._safe_goto(page, upload_url)
        except Exception:
            await page.reload(wait_until="domcontentloaded")
        await page.wait_for_timeout(2500)
        await self._snapshot(page, f"order_{order_id}_upload_retry_{attempt}_reset")

    @staticmethod
    def _is_upload_transient_failure(message: str) -> bool:
        """识别平台上传初始化、网络抖动这类适合重试的错误。"""
        keywords = (
            "上传处理失败",
            "上传失败",
            "当前选择文件数量超过订单创意单元上限",
            "订单创意单元上限: 0",
        )
        return any(keyword in message for keyword in keywords)

    async def _open_work_order_management(self, page, progress: ProgressCallback | None = None) -> None:
        """从首页点墨攻AI进入，再点菜单栏的工单管理。"""
        self._emit(progress, "进入工单管理")

        # 1. 等"墨攻AI"出现；不设总超时，页面短暂白屏或接口慢时持续等待。
        while True:
            try:
                await self._wait_for_page_text(
                    page, ("墨攻AI",),
                    timeout_ms=15000,
                    raise_on_timeout=True,
                )
                break
            except Exception:
                # 沿用之前的刷新逻辑：safe_goto HOME_URL
                try:
                    await self._safe_goto(page, HOME_URL)
                except Exception:
                    pass
                self._emit(progress, "等待墨攻AI入口加载，继续重试")
                await page.wait_for_timeout(2000)
        await self._click_text(page, "墨攻AI")

        # 2. 等墨攻AI加载（出现工单管理/素材管理菜单就算成功），不设总超时。
        await self._wait_for_page_text(
            page, ("工单管理", "素材管理"),
            timeout_ms=None,
            raise_on_timeout=True,
        )

        # 3. 点工单管理
        try:
            await self._click_text(page, "工单管理")
        except RuntimeError:
            await self._snapshot_error(page, "work_order_not_reached")
            raise RuntimeError("未找到工单管理菜单")
        await page.wait_for_timeout(2000)
        if not await self._is_work_order_page(page):
            await self._snapshot_error(page, "work_order_not_reached")
            raise RuntimeError("点击工单管理后未进入列表")

    async def _is_work_order_page(self, page) -> bool:
        """判断当前页面是否是工单管理列表页。"""
        body = await self._body_text(page)
        if "新建创意单元" in body:
            return True
        return bool(
            await self._first_existing(
                page,
                (
                    "input[placeholder*='订单']",
                ),
            )
        )

    async def _search_order(self, page, order_id: str) -> None:
        """在工单管理页按订单 ID 搜索并确认结果出现。"""
        if not await self._is_work_order_page(page):
            await self._snapshot_error(page, "search_order_not_on_work_order_page")
            raise RuntimeError("未进入工单管理页，不能搜索订单")
        if await self._order_visible(page, order_id):
            return
        search_input = await self._wait_first_existing(
            page,
            (
                "input[placeholder*='订单名称或ID']",
            ),
            timeout_ms=20000,
        )
        if not search_input:
            raise RuntimeError("未找到订单搜索框")
        await self._type_into_locator(search_input, page, order_id)
        await page.wait_for_timeout(1000)
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(4000)
        if not await self._order_visible(page, order_id):
            await self._snapshot_error(page, f"order_{order_id}_not_found")
            raise RuntimeError(f"查询结果中未找到订单 {order_id}")

    async def _order_visible(self, page, order_id: str) -> bool:
        """判断当前页面文本中是否能看到订单 ID。"""
        body = await self._body_text(page)
        return order_id in body

    async def _open_create_creative_unit(self, page, order_id: str):
        """在订单搜索结果中点击"新建创意单元"，并返回实际进入的上传页面。"""
        await self._snapshot(page, f"order_{order_id}_before_create")

        async def try_open(attempt: int):
            for clicker in (self._click_create_button_for_order, self._click_create_button_by_coordinates):
                before_pages = list(page.context.pages)
                old_url = page.url
                if not await clicker(page, order_id):
                    continue
                target_page = await self._wait_create_page_after_click(page, before_pages, old_url)
                if target_page:
                    await target_page.wait_for_timeout(4000)
                    return target_page
            await self._snapshot_error(page, f"order_{order_id}_create_click_no_effect_{attempt}")
            return False

        try:
            return await self._retry(
                try_open,
                description=f"打开订单 {order_id} 的新建创意单元",
                max_attempts=4,
            )
        except RuntimeError as exc:
            await self._snapshot_error(
                page,
                f"order_{order_id}_create_button_not_found",
                exc=exc,
                extra=f"order_id={order_id}",
            )
            raise RuntimeError(f"订单 {order_id} 搜索结果中未找到新建创意单元") from exc

    async def _wait_create_page_after_click(self, page, before_pages: list, old_url: str):
        """点击创建入口后等待当前页或新标签页进入上传页。"""
        before_ids = {id(p) for p in before_pages}
        deadline = asyncio.get_event_loop().time() + 25

        while asyncio.get_event_loop().time() < deadline:
            for candidate in reversed(page.context.pages):
                if candidate.is_closed():
                    continue
                try:
                    await candidate.wait_for_load_state("domcontentloaded", timeout=1000)
                except Exception:
                    pass
                # 命中条件：是上传页，或者是一个新开的、非占位 URL 的标签页
                is_upload = await self._looks_like_upload_page(candidate)
                is_new = (
                        id(candidate) not in before_ids
                        and candidate.url not in {"about:blank", old_url}
                )
                if is_upload or is_new:
                    try:
                        await candidate.bring_to_front()
                    except Exception:
                        pass
                    self._wrap_page_speed(candidate)
                    return candidate
            # 当前页已经离开工单管理页（点中了跳转）
            if page.url != old_url and not await self._is_work_order_page(page):
                self._wrap_page_speed(page)
                return page
            await page.wait_for_timeout(800)
        return None

    async def _looks_like_upload_page(self, page) -> bool:
        """判断页面是否已经进入上传创意单元页面。"""
        if await self._first_attached(page, ("input[type='file']",)):
            return True
        body = await self._body_text(page, timeout_ms=2000)
        return any(text in body for text in ("点击或拖拽", "文件上传", "温馨提示"))

    async def _click_create_button_for_order(self, page, order_id: str) -> bool:
        """优先在包含订单 ID 的结果区域中点击“新建创意单元”。"""
        scope = await self._order_result_scope(page, order_id)
        if scope and await self._click_create_button_in_scope(scope):
            return True
        if await self._order_visible(page, order_id):
            exact_buttons = page.get_by_text("新建创意单元", exact=True)
            if await self._click_single_visible_locator(exact_buttons):
                return True
        return await self._click_create_button_near_order(page, order_id)

    async def _click_create_button_in_scope(self, scope) -> bool:
        """在指定 DOM 区域内寻找并点击"新建创意单元"。"""
        for locator in (
                scope.locator("button.ant-btn-link:has-text('新建创意单元')"),
                scope.get_by_text("新建创意单元", exact=True),
        ):
            try:
                button = locator.first
                if await button.count() and await button.is_visible():
                    await button.scroll_into_view_if_needed(timeout=3000)
                    await button.click(force=True)
                    return True
            except Exception:
                continue
        return False

    async def _find_closest_create_button(self, page, order_id: str):
        """找到距离订单 ID 垂直方向最近的"新建创意单元"按钮；找不到返回 None。"""
        # 仅在订单文本垂直方向 90 像素内搜索按钮，避免误点页面其它位置的同名按钮。
        max_distance = 90
        order_box = await self._first_text_box(page, order_id)
        if not order_box:
            return None
        order_y = order_box["y"] + order_box["height"] / 2

        candidates = page.locator(
            "button.ant-btn-link:has-text('新建创意单元'), "
            "a:has-text('新建创意单元'), "
            "[role='button']:has-text('新建创意单元')"
        )

        best, best_distance = None, max_distance
        for index in range(min(await candidates.count(), 30)):
            try:
                button = candidates.nth(index)
                if not await button.is_visible():
                    continue
                box = await button.bounding_box(timeout=3000)
                if not box:
                    continue
                distance = abs(box["y"] + box["height"] / 2 - order_y)
                if distance < best_distance:
                    best, best_distance = button, distance
            except Exception:
                continue
        return best

    async def _click_create_button_near_order(self, page, order_id: str) -> bool:
        """用 Playwright 点击订单附近的"新建创意单元"。"""
        button = await self._find_closest_create_button(page, order_id)
        return bool(button) and await self._click_locator(button)

    async def _click_create_button_by_coordinates(self, page, order_id: str) -> bool:
        """用真实鼠标点击，作为 Playwright 点击失败的兜底。"""
        button = await self._find_closest_create_button(page, order_id)
        return bool(button) and await self._click_locator_center(page, button)

    async def _order_result_scope(self, page, order_id: str):
        """寻找同时包含订单 ID 和操作入口的订单结果区域。"""
        order_literal = self._xpath_literal(order_id)
        for text_locator in (
                page.get_by_text(order_id, exact=True).first,
                page.get_by_text(order_id, exact=False).first,
        ):
            for xpath in (
                    "xpath=ancestor::*[contains(., '新建创意单元')][1]",
                    f"xpath=ancestor::*[contains(., {order_literal}) and contains(., '新建创意单元')][1]",
                    f"xpath=ancestor::*[contains(., {order_literal}) and contains(., '查看创意单元')][1]",
            ):
                try:
                    scope = text_locator.locator(xpath)
                    if await scope.count() and await scope.is_visible():
                        return scope
                except Exception:
                    continue
        return None

    async def _click_single_visible_locator(self, locators) -> bool:
        """当匹配结果只有一个可见元素时点击它。"""
        visible = await self._visible_locators(locators)
        if len(visible) != 1:
            return False
        return await self._click_locator(visible[0])

    async def _first_text_box(self, page, text: str):
        """返回页面上某段文本的第一个可见位置。"""
        for locator in (
                page.get_by_text(text, exact=True).first,
                page.get_by_text(text, exact=False).first,
        ):
            try:
                if await locator.count() and await locator.is_visible():
                    box = await locator.bounding_box(timeout=3000)
                    if box:
                        return box
            except Exception:
                continue
        return None

    @staticmethod
    def _xpath_literal(value: str) -> str:
        """把普通字符串转换成 XPath contains 可安全使用的字面量。"""
        if "'" not in value:
            return f"'{value}'"
        if '"' not in value:
            return f'"{value}"'
        parts = value.split("'")
        return "concat(" + ", \"'\", ".join(f"'{part}'" for part in parts) + ")"

    async def _read_upload_limit(self, page) -> int | None:
        """从上传页温馨提示中读取最多可上传创意单元数量。"""
        try:
            body = await page.locator("body").inner_text(timeout=5000)
        except Exception:
            return None
        # 三种文案兜底：带"上传"、带"个"、带"上限"，相互不重叠，按出现概率从高到低排序。
        patterns = (
            r"最多(?:可以)?上传\s*(\d+)",
            r"最多\s*(\d+)\s*个",
            r"上限\s*(\d+)",
        )
        for pattern in patterns:
            match = re.search(pattern, body)
            if match:
                return int(match.group(1))
        return None

    async def _upload_files(
            self,
            page,
            items: list[UserGrowthVideoItem],
            order_id: str | None = None,
    ):
        """上传视频文件，失败自动重试。

        文件上传 input 会持续等待，找不到时周期性点击上传入口。
        上传动作本身仍复用 _retry 做指数退避重试，避免平台返回明确失败后无限卡住。

        失败时如果传入了 order_id，会刷新当前页并从"新建创意单元"入口
        重新走流程再进行下一次重试，避免"点击或拖拽"被点击后服务端没
        真正开始上传而留下的半成品状态。
        """

        current_page = page

        async def attempt(_attempt: int) -> bool:
            nonlocal current_page
            try:
                await self._snapshot(current_page, f"before_upload_{_attempt}")
                file_input = None
                while not file_input:
                    file_input = await self._wait_file_input(
                        current_page,
                        timeout_ms=25000
                    )
                    if file_input:
                        break
                    try:
                        await self._click_text(current_page, "点击或拖拽文件至此区域")
                    except RuntimeError:
                        await self._click_if_present(current_page, "上传")

                    file_input = await self._wait_file_input(
                        current_page,
                        timeout_ms=15000
                    )
                    if not file_input:
                        print("[upload] 未找到文件上传控件，继续等待")
                # 设置文件
                await file_input.set_input_files(
                    [str(item.path) for item in items]
                )
                # 触发真正上传
                await self._click_if_present(
                    current_page,
                    "点我开始上传"
                )
                await current_page.wait_for_timeout(3000)
                # 检查上传是否异常
                body = await self._body_text(current_page)
                if self._has_upload_limit_zero_error(body):
                    raise RuntimeError("当前选择文件数量超过订单创意单元上限: 0")
                if "上传失败" in body or "上传异常" in body:
                    raise RuntimeError(
                        "页面提示上传失败"
                    )
                return True

            except Exception as exc:
                await self._snapshot_error(
                    current_page,
                    f"upload_failed_retry_{_attempt}",
                    exc=exc,
                )
                print(f"[upload] 第 {_attempt} 次上传失败: {exc}")
                # 刷新页面 + 从「新建创意单元」入口重新走流程，
                # 避免「点击或拖拽」被点击后服务端没真正开始上传的半成品状态
                if order_id:
                    try:
                        try:
                            await current_page.reload(
                                wait_until="domcontentloaded"
                            )
                            await current_page.wait_for_timeout(2000)
                        except Exception:
                            pass
                        new_page = await self._open_create_creative_unit(
                            current_page,
                            order_id,
                        )
                        if new_page:
                            current_page = new_page
                    except Exception as reset_exc:
                        print(
                            f"[upload] 重新走新建创意单元失败: {reset_exc}"
                        )
                return False

        try:
            await self._retry(
                attempt,
                description="upload files",
                max_attempts=6,
                base_interval_ms=2000,
            )
        except RuntimeError as exc:
            raise RuntimeError(
                f"上传失败，重试 6 次仍失败: {exc}"
            ) from exc
        return current_page

    @staticmethod
    def _has_upload_limit_zero_error(body: str) -> bool:
        """识别上传后页面提示的创意单元上限为 0 异常。"""
        compact_body = _compact_text(body)
        return (
                "当前选择文件数量超过订单创意单元上限" in body
                or "当前选择文件数量超过订单创意单元上限:0" in compact_body
                or "订单创意单元上限:0" in compact_body
        )

    async def _wait_file_input(self, page, timeout_ms: int = 20000):
        """等待隐藏或可见的文件上传 input 出现在页面上。"""

        async def find_file_input():
            return await self._first_attached(page, ("input[type='file']",))

        return await self._wait_for_result(find_file_input, timeout_ms=timeout_ms, interval_ms=800)

    async def _enter_chameleon(
            self,
            page,
            items: list[UserGrowthVideoItem],
            progress: ProgressCallback | None = None,
    ):
        """提交上传后的创意单元列表，并进入录入流程。"""

        def _log(msg: str) -> None:
            print(f"[enter-chameleon] {msg}", flush=True)

        self._emit(progress, f"等待 {len(items)} 个视频生成待提交卡片")
        await self._wait_upload_cards_ready(page, items)
        await self._click_if_present(page, "继续编辑")
        await page.wait_for_timeout(2000)
        # "确认提交"点击后可能打开新标签页，也可能当前页跳转；不设总超时等待目标页出现。
        new_page = await self._click_text_and_wait_page(page, "确认提交", timeout_ms=None)
        self._wrap_page_speed(new_page)
        _log(f"new tab opened, url={new_page.url}")
        # 切到新标签页
        page = new_page
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=0)
        except Exception as exc:
            await self._snapshot_error(page, "new_tab_load_failed", exc=exc)
            raise RuntimeError(f"新标签页加载失败: {exc}, url={page.url}")
        _log(f"new tab loaded, url={page.url}")
        await self._wait_creative_unit_table_ready(page, timeout_ms=None)
        await self._click_creative_unit_select_all_checkbox(page)
        # "录入素材"点击后可能打开新标签页，也可能当前页跳转；不设总超时等待目标页出现。
        entry_page = await self._click_text_and_wait_page(page, "录入素材", timeout_ms=None)
        self._wrap_page_speed(entry_page)
        page = entry_page
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=0)
        except Exception as exc:
            await self._snapshot_error(page, "enter_chameleon_load_failed", exc=exc)
            raise RuntimeError(f"chameleon 录入页加载失败: {exc}, url={page.url}")
        # 等 chameleon 内容渲染
        while True:
            if await self._looks_like_chameleon_entry_page(page):
                _log(f"chameleon entry page ready, url={page.url}")
                break
            await page.wait_for_timeout(500)
        await self._snapshot(page, "after_enter_chameleon")
        await self._ensure_chameleon_modal(page)
        await self._click_chameleon_modal_confirm(page)
        await page.wait_for_timeout(2500)
        # todo 是否每次上传都是同一批的，如果是的话就不用循环了
        await self._fill_card_defaults(page, items[0])
        return page

    async def _wait_chameleon_entry_page_after_click(self, page, before_pages: list, old_url: str):
        """点击录入素材后，等待跳转后的新标签页出现。"""
        before_ids = {id(p) for p in before_pages}
        deadline = asyncio.get_event_loop().time() + 45
        while asyncio.get_event_loop().time() < deadline:
            for candidate in reversed(page.context.pages):
                if candidate.is_closed():
                    continue
                try:
                    await candidate.wait_for_load_state("domcontentloaded", timeout=1000)
                except Exception:
                    pass
                # 是新开的非占位页
                is_chameleon = await self._looks_like_chameleon_entry_page(candidate)
                is_new = (
                        id(candidate) not in before_ids
                        and candidate.url not in {"about:blank", old_url}
                )
                if is_chameleon or is_new:
                    try:
                        await candidate.bring_to_front()
                    except Exception:
                        pass
                    return candidate
            await self._sleep(1)
        await self._snapshot_error(page, "enter_chameleon_page_timeout")
        raise RuntimeError("点击录入后未进入录入页面")

    async def _looks_like_chameleon_entry_page(self, page) -> bool:
        """判断页面是否是录入变色龙后的投放信息确认页。"""
        body = await self._body_text(page, timeout_ms=2000)
        if not body.strip():
            return False
        return any(text in body for text in ("投放平台", "汽水音乐"))

    async def _wait_upload_cards_ready(self, page, items: list[UserGrowthVideoItem]) -> None:
        """等待选中文件后页面生成对应数量的待提交创意设置卡片，不设总超时。"""
        expected_count = len(items)
        s_count = 0

        while True:
            try:
                body = await self._body_text(page, timeout_ms=3000)
            except Exception:
                body = ""

            if self._has_upload_limit_zero_error(body):
                await self._snapshot_error(page, "upload_limit_zero_before_cards_ready")
                raise RuntimeError("当前选择文件数量超过订单创意单元上限: 0")
            if "上传失败" in body or "上传异常" in body:
                await self._snapshot_error(page, "upload_failed_before_cards_ready")
                raise RuntimeError("等待上传卡片时页面提示上传失败")

            try:
                # 查找页面上所有的 Arco 复选框/勾选图标
                success_icons = page.locator("span.arco-upload-list-success-icon")

                # 统计可见数量
                visible_icons = await self._visible_locators(success_icons, limit=100)
                s_count = len(visible_icons)

                # 数量相等即视为上传成功
                if s_count >= expected_count:
                    await self._snapshot(page, "upload_cards_ready")
                    return

            except Exception:
                # 统计过程中发生任何异常（比如页面还没加载出 DOM），忽略，继续下一轮
                pass

            # 轮询间隔，避免 CPU 飙高
            await page.wait_for_timeout(1000)

    async def _wait_before_submit_after_upload(self, page, items: list[UserGrowthVideoItem]) -> None:
        """提交前按视频数量等待平台完成文件预处理。"""
        timeout_ms = self._pre_submit_upload_wait_ms(len(items))
        deadline = None if timeout_ms is None else asyncio.get_event_loop().time() + timeout_ms / 1000
        while deadline is None or asyncio.get_event_loop().time() < deadline:
            body = await self._body_text(page, timeout_ms=3000)
            if "上传失败" in body or "上传异常" in body:
                await self._snapshot_error(page, "upload_failed_before_submit")
                raise RuntimeError("提交前视频上传处理失败")
            await page.wait_for_timeout(3000)
        await self._snapshot(page, "upload_before_submit_wait_done")

    async def _is_creative_unit_list_page(self, page, body: str | None = None) -> bool:
        """判断当前页面是否是创意单元列表页。"""
        body = body if body is not None else await self._body_text(page, timeout_ms=3000)
        if "提交创意单元" in body:
            return True
        return "创意单元" in body and any(text in body for text in ("操作", "单元名称"))

    async def _creative_unit_rows_ready(
            self,
            page,
            body: str | None,
            items: list[UserGrowthVideoItem],
    ) -> bool:
        """确认创意单元列表中已经出现本次上传的所有文件名。"""
        body = body if body is not None else await self._body_text(page, timeout_ms=3000)
        if not await self._is_creative_unit_list_page(page, body):
            return False
        if "暂无数据" in body:
            return False
        return all(item.file_name in body for item in items)

    async def _ensure_chameleon_modal(self, page) -> None:
        """检查录入弹窗里的投放产品和投放平台是否符合预期。"""
        await self._snapshot(page, "chameleon_delivery_before_check")
        expected_fields = (
            ("投放产品", "汽水音乐"),
        )
        for field_text, value_text in expected_fields:
            if not await self._ensure_delivery_field_value(page, field_text, value_text):
                await self._snapshot_error(page, f"chameleon_delivery_{field_text}_not_selected")
        if not await self._ensure_delivery_platform_all(page):
            await self._snapshot_error(page, "chameleon_delivery_platform_not_selected")

        missing = [
            f"{label}:{value}"
            for label, value in expected_fields
            if not await self._delivery_field_has_value(page, label, value)
        ]
        if not await self._delivery_platform_has_selection(page):
            missing.append("投放平台:全部下拉选项")
        if missing:
            await self._snapshot_error(page, "chameleon_delivery_check_failed")
            raise RuntimeError(f"录入弹窗内容不符合预期：缺少 {', '.join(missing)}")

    async def _ensure_delivery_field_value(self, page, field_text: str, value_text: str) -> bool:
        """确保录入投放信息中的指定字段选择到目标值。"""
        if await self._delivery_field_has_value(page, field_text, value_text):
            return True
        for attempt in range(3):
            if not await self._open_delivery_dropdown_by_label(page, field_text):
                await page.wait_for_timeout(800)
                continue
            await page.wait_for_timeout(900)
            if field_text == "投放平台":
                await self._snapshot(page, f"chameleon_delivery_platform_dropdown_{attempt + 1}")
                await self._type_into_open_dropdown(page, value_text)
                await self._snapshot(page, f"chameleon_delivery_platform_after_type_{attempt + 1}")
            await self._click_dropdown_option(page, value_text)
            await page.wait_for_timeout(900)
            # 只按当前字段校验，避免页面其他位置的相同文案造成误判。
            if await self._delivery_field_has_value(page, field_text, value_text):
                await self._close_open_delivery_dropdown_if_needed(page)
                return True
        return False

    async def _open_delivery_dropdown_by_label(self, page, field_text: str) -> bool:
        """在录入确认框中，按字段标签打开对应下拉控件。"""
        root = await self._delivery_modal_root(page)
        if not root:
            return False

        # 优先从表单项内部找控件；新页面布局变化时，再按字段标签同一行找右侧控件兜底。
        candidates = []
        form_item = await self._delivery_form_item(page, field_text)
        if form_item:
            candidates.extend(await self._select_controls(form_item))
        candidates.extend(await self._nearby_select_controls(root, field_text))

        # Arco 下拉有时不响应 dispatchEvent，所以这里用真实鼠标点击并确认浮层真的展开。
        for locator in candidates[:4]:
            if await self._click_locator_center(page, locator):
                await page.wait_for_timeout(250)
                if await self._delivery_dropdown_opened(page):
                    return True
        return False

    async def _delivery_modal_root(self, page):
        """返回录入投放弹窗根节点。"""
        # body 是最后兜底：有些页面把内容放在 drawer/portal 外层，仍然能靠文案定位。
        for selector in (DELIVERY_MODAL_SELECTOR, "body"):
            for locator in reversed(await self._visible_locators(page.locator(selector), limit=30)):
                text = _compact_text(await self._locator_text(locator, timeout_ms=2000))
                if "投放产品" in text and "投放平台" in text:
                    return locator
        return None

    @staticmethod
    def _pre_submit_upload_wait_ms(item_count: int) -> int:
        """根据视频数量计算点击提交前的固定等待时间。"""
        return UserGrowthBrowserClient._bounded_timeout_ms(item_count, minimum=90000, per_item=10000,
                                                           maximum=5 * 60 * 1000)

    @staticmethod
    def _bounded_timeout_ms(item_count: int, *, minimum: int, per_item: int, maximum: int) -> int:
        """按素材数量计算带上下限的等待时间。"""
        count = max(item_count, 1)
        return min(max(minimum, count * per_item), maximum)

    async def _delivery_form_item(self, page, field_text: str):
        """按字段名返回投放弹窗里的表单项。"""
        root = await self._delivery_modal_root(page)
        if not root:
            return None
        wanted = _compact_text(field_text)
        # 只在弹窗内部查找，避免页面背景里同名字段干扰。
        for item in await self._visible_locators(root.locator(FORM_ITEM_SELECTOR), limit=80):
            if wanted in _compact_text(await self._locator_text(item, timeout_ms=1000)):
                return item
        return None

    async def _select_controls(self, root) -> list:
        """返回某个区域内可见可用的选择控件。"""
        controls = []
        for locator in await self._visible_locators(root.locator(SELECT_CONTROL_SELECTOR), limit=80):
            class_name = str(await locator.get_attribute("class") or "")
            aria_disabled = await locator.get_attribute("aria-disabled")
            # 同时看 aria 和 class，兼容 Arco 不同组件的禁用状态写法。
            if aria_disabled != "true" and "disabled" not in class_name:
                controls.append(locator)
        return controls

    async def _nearby_select_controls(self, root, field_text: str) -> list:
        """按字段标签所在行寻找右侧选择控件。"""
        label = await self._field_label(root, field_text)
        if not label:
            return []
        label_box = await label.bounding_box(timeout=2000)
        if not label_box:
            return []
        label_y = label_box["y"] + label_box["height"] / 2
        controls = []
        for control in await self._select_controls(root):
            box = await control.bounding_box(timeout=1000)
            # 同一行右侧控件是最接近人工视觉判断的兜底，避免误点其它投放字段。
            if box and box["x"] >= label_box["x"] and abs((box["y"] + box["height"] / 2) - label_y) <= 70:
                controls.append((abs((box["y"] + box["height"] / 2) - label_y), control))
        return [control for _, control in sorted(controls, key=lambda item: item[0])]

    async def _field_label(self, root, field_text: str):
        """返回字段标签元素。"""
        wanted = _compact_text(field_text)
        labels = await self._visible_locators(root.locator("label, .arco-form-item-label, div, span"), limit=120)
        for label in labels:
            text = _compact_text(await self._locator_text(label, timeout_ms=1000))
            # 限制长度，避免把包含大量子控件文本的容器误判成标签。
            if wanted in text and len(text) <= len(wanted) + 12:
                return label
        return None

    async def _open_dropdown_root(self, page):
        """返回当前展开的下拉浮层。"""
        for locator in reversed(await self._visible_locators(page.locator(DROPDOWN_ROOT_SELECTOR), limit=30)):
            text = _compact_text(await self._locator_text(locator, timeout_ms=1000))
            if text:
                return locator
        return None

    async def _dropdown_option_clickable(self, option) -> bool:
        """判断下拉选项是否可点击且尚未选中。"""
        text = _compact_text(await self._locator_text(option, timeout_ms=1000))
        if not text:
            return False
        class_name = str(await option.get_attribute("class") or "")
        aria_disabled = await option.get_attribute("aria-disabled")
        if aria_disabled == "true" or "disabled" in class_name:
            return False
        if await self._dropdown_option_selected(option):
            return False
        return True

    async def _dropdown_option_selected(self, option) -> bool:
        """识别 Arco 下拉项的已选状态，避免再次点击把多选项反选掉。"""
        class_name = str(await option.get_attribute("class") or "")
        aria_selected = await option.get_attribute("aria-selected")
        if aria_selected == "true" or "selected" in class_name:
            return True
        try:
            # 多选项里有 check 图标时也视为已选中，避免重复点击导致反选。
            return bool(await option.locator(".arco-icon-check").count())
        except Exception:
            return False

    async def _dropdown_at_bottom(self, root) -> bool:
        """判断下拉浮层是否已经滚到底。"""
        try:
            return bool(
                await root.evaluate(
                    """node => {
                        const items = [node, ...Array.from(node.querySelectorAll('*'))]
                            .filter(item => item.scrollHeight > item.clientHeight + 4);
                        const target = items.find(item => item.scrollTop + item.clientHeight < item.scrollHeight - 2);
                        return !target;
                    }"""
                )
            )
        except Exception:
            # 判断失败时按“到底”处理，宁可少滚一轮，也不要卡在无限滚动里。
            return True

    async def _scroll_dropdown_root(self, page, root) -> None:
        """滚动当前下拉浮层。"""
        try:
            box = await root.bounding_box(timeout=2000)
            if box:
                # 优先使用鼠标滚轮，触发组件自己的虚拟列表加载逻辑。
                await page.mouse.move(box["x"] + box["width"] / 2, box["y"] + max(box["height"] - 16, 8))
                await page.mouse.wheel(0, max(int(box["height"] * 0.9), 220))
                return
        except Exception:
            pass
        try:
            # 鼠标滚轮失败时，直接推进内部可滚动容器作为最后兜底。
            await root.evaluate(
                """node => {
                    const items = [node, ...Array.from(node.querySelectorAll('*'))]
                        .filter(item => item.scrollHeight > item.clientHeight + 4);
                    const target = items.find(item => item.scrollTop + item.clientHeight < item.scrollHeight - 2) || items[0];
                    if (target) target.scrollTop = Math.min(target.scrollTop + Math.max(target.clientHeight * 0.85, 120), target.scrollHeight);
                }"""
            )
        except Exception:
            return

    async def _delivery_dropdown_opened(self, page) -> bool:
        """确认当前页面确实展开了 Arco 下拉浮层。"""
        return await self._open_dropdown_root(page) is not None

    async def _ensure_delivery_platform_all(self, page) -> bool:
        """把投放平台下拉里的平台全部选中。

        一次全选 + 点"投放平台"标题收起，不再做 has_selection 校验，
        校验交给最后的 _click_chameleon_modal_confirm 流程。
        """
        for attempt in range(2):
            if not await self._open_delivery_dropdown_by_label(page, "投放平台"):
                await page.wait_for_timeout(250)
                continue
            await page.wait_for_timeout(100)
            await self._snapshot(page, f"chameleon_delivery_platform_dropdown_{attempt + 1}")
            await self._select_all_open_dropdown_options(page)
            await self._snapshot(page, f"chameleon_delivery_platform_all_clicked_{attempt + 1}")
            # 选完不等待，直接点"投放平台"标题收回下拉
            await self._click_text(page, "投放平台")
            await page.wait_for_timeout(100)
            return True
        return False

    async def _close_open_delivery_dropdown_if_needed(self, page) -> None:
        """仅在投放信息弹窗下拉仍然展开时尝试收起，避免遮挡确认按钮。"""
        if await self._delivery_dropdown_opened(page):
            await self._click_text(page, "上传素材")

    async def _select_all_open_dropdown_options(self, page) -> int:
        """逐屏逐个点击当前打开下拉框里的未选中选项，直到滚动到底。"""
        total_clicked = 0
        stagnant_rounds = 0
        last_visible_text = ""
        for _ in range(35):
            root = await self._open_dropdown_root(page)
            if not root:
                break
            clicked_this_round = 0
            visible_text = _compact_text(await self._locator_text(root, timeout_ms=2000))
            options = await self._visible_locators(root.locator(DROPDOWN_OPTION_SELECTOR), limit=80)
            for option in options:
                try:
                    if not await self._dropdown_option_clickable(option):
                        continue
                    await option.click(timeout=3000)
                    clicked_this_round += 1
                    total_clicked += 1
                    await page.wait_for_timeout(220)
                except Exception:
                    continue
            if await self._dropdown_at_bottom(root):
                break
            await self._scroll_dropdown_root(page, root)
            # 虚拟列表滚动异常时，连续几轮没有新文本也没有点击，就停止防止死循环。
            if visible_text == last_visible_text and clicked_this_round == 0:
                stagnant_rounds += 1
            else:
                stagnant_rounds = 0
            last_visible_text = visible_text
            if stagnant_rounds >= 3:
                break
            await page.wait_for_timeout(450)
        return total_clicked

    async def _delivery_field_has_value(self, page, field_text: str, value_text: str) -> bool:
        """只检查指定字段自己的可见值，避免被页面其它同名文案误导。"""
        text = await self._delivery_field_text(page, field_text)
        normalized = _compact_text(text)
        value_area = normalized.replace(_compact_text(field_text), "", 1)
        return "请选择" not in value_area and self._delivery_value_visible(value_area, value_text)

    async def _delivery_platform_has_selection(self, page) -> bool:
        """判断投放平台字段是否已经有选择值，而不是停留在“请选择”。"""
        text = await self._delivery_field_text(page, "投放平台")
        normalized = _compact_text(text)
        value_text = normalized.replace("投放平台", "")
        return bool(value_text) and "请选择" not in value_text

    async def _delivery_field_text(self, page, field_text: str) -> str:
        """读取录入变色龙投放弹窗中某个字段所在表单项的可见文本。"""
        item = await self._delivery_form_item(page, field_text)
        return await self._locator_text(item) if item else ""

    async def _type_into_open_dropdown(self, page, keyword: str) -> None:
        """在已经展开的下拉框里输入关键词，优先让长列表过滤出目标选项。"""
        try:
            root = await self._open_dropdown_root(page)
            input_box = root.locator("input").first if root else None
            if input_box and await input_box.count() and await input_box.is_visible():
                # 可搜索下拉优先填 input，让平台自己过滤长列表。
                await input_box.fill(keyword, timeout=3000)
            else:
                # 部分 Arco 组件 input 不在浮层内，退回键盘输入给当前焦点。
                await self._keyboard_type(page, keyword)
            await page.wait_for_timeout(800)
        except Exception:
            return

    async def _click_dropdown_option(self, page, option_text: str) -> bool:
        """点击 Arco 下拉浮层里的指定选项。"""
        deadline = asyncio.get_event_loop().time() + 8
        while asyncio.get_event_loop().time() < deadline:
            if await self._click_visible_dropdown_option(page, option_text):
                return True
            await self._scroll_open_dropdown(page)
            await page.wait_for_timeout(400)
        return False

    async def _click_visible_dropdown_option(self, page, option_text: str) -> bool:
        """点击当前已经渲染出来的下拉选项。"""
        root = await self._open_dropdown_root(page)
        if not root:
            return False
        wanted = _compact_text(option_text)
        for option in await self._visible_locators(root.locator(DROPDOWN_OPTION_SELECTOR), limit=80):
            text = _compact_text(await self._locator_text(option, timeout_ms=1000))
            if text == wanted or wanted in text:
                if await self._dropdown_option_selected(option):
                    return True
                if not await self._dropdown_option_clickable(option):
                    return False
                return await self._click_locator(option)
        return False

    async def _scroll_open_dropdown(self, page) -> None:
        """滚动当前展开的下拉浮层，让未渲染在首屏的选项逐步出现。"""
        root = await self._open_dropdown_root(page)
        if root:
            await self._scroll_dropdown_root(page, root)

    async def _click_chameleon_modal_confirm(self, page) -> None:
        """只点击录入变色龙投放信息弹窗里的确认按钮。"""
        await self._close_open_delivery_dropdown_if_needed(page)
        root = await self._delivery_modal_root(page)
        if root:
            for button in await self._visible_locators(root.locator("button"), limit=20):
                text = _compact_text(await self._locator_text(button, timeout_ms=1000))
                if text in {"确认", "确定"} and await self._click_locator(button):
                    return
        await self._click_first(page, ("button:has-text('确认')", "button:has-text('确定')"))

    @staticmethod
    def _delivery_value_visible(body: str, value_text: str) -> bool:
        """判断投放信息目标值是否已显示。"""
        return value_text in body

    async def _fill_card_defaults(self, page, item: UserGrowthVideoItem) -> None:
        """为素材卡片填写制作团队、授权、分类标签和自定义标签。"""
        await self._select_dropdown_value(page, "请选择UGC内容", "不包含")
        await self._select_dropdown_value(page, "分类标签")
        # 进入到弹窗进行级联选择
        await self._select_cascader(
            page,
            "汽水音乐-素材类型",
            [
                "汽水音乐-素材类型",
                "LUNA_剪辑制作",
                "LUNA_自产"
            ]
        )
        await self._select_cascader(page, "LUNA素材来源", ["LUNA素材来源", "LUNA_千沧代理"])

        path, tags = card_defaults_for_item(item)
        print(f"计划中的分类标签{path}")
        await self._select_cascader(
            page,
            "LUNA功能卖点",
            path
        )

        await self._click_if_present(page, "确定")

        # 填入自定义标签
        print(f"计划中的自定义标签集合{tags}")

        for tag in tags:
            input_box = await self._inputtag_for_field(page, "自定义标签")
            await input_box.fill(tag, timeout=5000)
            await page.keyboard.press("Enter")
            # tag 之间不留停顿，让 chip 一次性录入

        # 单选选择
        await self._click_radio_near_text(page, "未成年人内容", "已授权")
        await self._click_radio_near_text(page, "影视内容", "已授权")

        # 一键复用-全选-一键复用
        await self._click_if_present(page, "一键复用")
        await page.wait_for_timeout(1000)
        await self._click_if_present(page, "全选")
        await page.wait_for_timeout(800)
        await self._click_if_present(page, "一键复用")
        await page.wait_for_timeout(1000)
        await self._click_if_present(page, "提交")
        await page.wait_for_timeout(1500)
        # 提交后平台生成任务详情入口可能较慢，不设总超时等待。
        await self._wait_and_click_text(page, "查看任务详情", timeout_ms=None)

    async def _select_cascader(
            self,
            page,
            field_name: str,
            path: list[str]
    ) -> None:
        """
        通用级联选择

        path:
        [
            "汽水音乐-素材类型",
            "LUNA_剪辑制作",
            "LUNA_自产"
        ]
        """

        title = page.get_by_text(
            field_name,
            exact=True
        ).first

        await title.wait_for(
            state="visible",
            timeout=10000
        )

        cascader = title.locator(
            "xpath=following::div[contains(@class,'arco-cascader')][1]"
        )

        await cascader.wait_for(
            state="visible",
            timeout=10000
        )

        print(
            f"[cascader] 打开字段: {field_name}"
        )

        input_box = cascader.locator("input")

        if await input_box.count():

            print(
                "[cascader] 点击 input"
            )

            await input_box.click()

        else:

            print(
                "[cascader] 未找到input，点击容器"
            )

            await cascader.click(
                force=True
            )

        await page.wait_for_timeout(1000)

        popup = page.locator(
            ".arco-cascader-popup"
        ).last

        popup_count = await page.locator(
            ".arco-cascader-popup"
        ).count()

        print(
            f"[cascader] popup数量={popup_count}"
        )

        if popup_count == 0:
            raise RuntimeError(
                f"级联弹窗打开失败: {field_name}"
            )

        # 打印真实DOM
        try:

            html = await popup.inner_html()

            print(
                "[cascader html]",
                html[:2000]
            )

        except Exception as e:

            print(
                "[cascader] 获取html失败:",
                e
            )

        # 逐级点击
        for index, value in enumerate(path):

            print(
                f"[cascader] 选择第{index + 1}级: {value}"
            )

            success = await self._click_cascader_option(
                page,
                value
            )

            if not success:
                raise RuntimeError(
                    f"级联选择失败: {value}"
                )

            # 等待下一列展开
            if index < len(path) - 1:
                await page.wait_for_timeout(
                    800
                )

    async def _wait_next_cascader_column(
            self,
            page,
            timeout_ms=5000
    ):
        """等待级联下一列展开"""

        for _ in range(10):

            columns = await page.locator(
                ".arco-cascader-list"
            ).count()

            if columns >= 2:
                return

            await page.wait_for_timeout(500)

        raise RuntimeError(
            "级联下一层未展开"
        )

    async def _inputtag_for_field(self, page, field_text: str):
        """按 label 定位同行右侧 InputTag 的 input。"""
        label = page.get_by_text(field_text, exact=True).first
        await label.wait_for(state="visible", timeout=10000)
        return label.locator(
            "xpath=following::div[contains(@class,'arco-input-tag')][1]//input"
        )

    async def _wait_cascader_option(
            self,
            page,
            value: str,
            timeout_ms: int = 10000
    ):
        """等待级联节点出现"""

        wanted = _compact_cascader_text(value)

        async def check():
            options = page.locator(
                ".arco-cascader-list-column:last-child .arco-cascader-option:visible"
            )

            for option in await self._visible_locators(
                    options,
                    limit=80
            ):
                text = _compact_cascader_text(
                    await self._locator_text(option)
                )

                if text == wanted:
                    return True

            return False

        await self._retry(
            lambda _: check(),
            description=f"等待级联节点 {value}",
            max_attempts=10,
            base_interval_ms=500,
        )

    async def _click_cascader_option(
            self,
            page,
            value: str
    ) -> bool:
        """
        点击当前级联节点

        Arco Cascader:
        - 文本在 .arco-cascader-list-item-label
        - 展开事件绑定在 li.arco-cascader-list-item
        """

        wanted = _compact_cascader_text(value)

        popup = page.locator(
            ".arco-cascader-popup"
        ).last

        if not await popup.count():
            print(
                "[cascader] popup不存在"
            )
            return False

        # 当前弹窗所有节点
        nodes = popup.locator(
            ".arco-cascader-list-item-label"
        )

        count = await nodes.count()

        print(
            f"[cascader] 当前可匹配节点数量={count}, target={value}"
        )

        for i in range(count):

            node = nodes.nth(i)

            try:

                text = _compact_cascader_text(
                    await node.inner_text()
                )

            except Exception:

                continue

            print(
                f"[cascader] 节点[{i}]: {text}"
            )

            if text != wanted:
                continue

            print(
                f"[cascader] 匹配成功: {text}"
            )

            try:

                # Arco事件绑定在li
                item = node.locator(
                    "xpath=ancestor::li[contains(@class,'arco-cascader-list-item')]"
                ).first

                if await item.count():

                    print(
                        "[cascader] 点击li节点"
                    )

                    await item.click(
                        force=True
                    )

                else:

                    print(
                        "[cascader] 未找到li，点击label"
                    )

                    await node.click(
                        force=True
                    )

                await page.wait_for_timeout(
                    800
                )

                # 判断是否展开下一列
                columns = page.locator(
                    ".arco-cascader-list-column"
                )

                print(
                    "[cascader] 当前列数量:",
                    await columns.count()
                )

                print(
                    f"[cascader] 点击完成: {value}"
                )

                return True


            except Exception as e:

                print(
                    f"[cascader] 点击失败 {value}: {e}"
                )

                return False

        print(
            f"[cascader] 未找到: {value}"
        )

        return False

    async def _select_dropdown_value(
            self,
            page,
            field_text: str,
            value_text: str | None = None
    ) -> None:
        """
        点击下拉框并选择值。
        field_text 支持:
        1. 表单标题，例如 UGC内容
        2. placeholder，例如 请选择UGC内容
        """
        try:
            trigger = await self._dropdown_trigger_for_field(page, field_text)
            if trigger:
                if not await self._click_locator_center(page, trigger):
                    if not await self._click_locator(trigger):
                        raise RuntimeError(f"未点击到下拉控件: {field_text}")
            elif not value_text and field_text in {"分类标签", "选择分类标签"}:
                await self._open_label_selector(page)
                return
            else:
                # 最后兜底才点击文案本身，避免误点到左侧 label
                await self._click_text(page, field_text)
            await page.wait_for_timeout(700)
            if not value_text:
                return
            # 选择下拉选项
            await self._click_text(page, value_text)

        except Exception:
            return

    async def _dropdown_trigger_for_field(self, page, field_text: str):
        """按字段名或 placeholder 找到真正的下拉触发控件，避免误点左侧标题。"""
        wanted = _compact_text(field_text)
        body = page.locator("body").first

        for item in await self._visible_locators(body.locator(FORM_ITEM_SELECTOR), limit=120):
            item_text = _compact_text(await self._locator_text(item, timeout_ms=1000))
            if wanted and wanted in item_text:
                controls = await self._select_controls(item)
                if controls:
                    return controls[0]

        for control in await self._visible_locators(page.locator(SELECT_CONTROL_SELECTOR), limit=120):
            text = _compact_text(await self._locator_text(control, timeout_ms=1000))
            if wanted and wanted in text:
                return control

        placeholder_candidates = []
        for text in (field_text, f"选择{field_text}", f"请选择{field_text}"):
            compacted = _compact_text(text)
            if compacted and compacted not in placeholder_candidates:
                placeholder_candidates.append(compacted)

        for candidate in placeholder_candidates:
            for locator in (
                    page.get_by_text(candidate, exact=True).first,
                    page.get_by_text(candidate, exact=False).first,
            ):
                try:
                    if not await locator.count() or not await locator.is_visible():
                        continue
                    for xpath in (
                            "xpath=ancestor::*[contains(@class, 'arco-select-view')][1]",
                            "xpath=ancestor::*[contains(@class, 'arco-cascader-view')][1]",
                            "xpath=ancestor::*[contains(@class, 'arco-input-tag-view')][1]",
                            "xpath=ancestor::*[contains(@class, 'arco-input-tag')][1]",
                            "xpath=ancestor::*[contains(@class, 'select-view')][1]",
                            "xpath=ancestor::*[contains(@class, 'cascader-view')][1]",
                            "xpath=ancestor::*[contains(@class, 'input-tag')][1]",
                            "xpath=ancestor::*[@role='combobox'][1]",
                    ):
                        trigger = locator.locator(xpath)
                        if await trigger.count() and await trigger.is_visible():
                            return trigger
                    return locator
                except Exception:
                    continue

        nearby_controls = await self._nearby_select_controls(body, field_text)
        if nearby_controls:
            return nearby_controls[0]

        return None

    async def _click_radio_near_text(self, page, field_text: str, value_text: str) -> None:
        """点击某个字段附近的单选值；找不到时保持页面现状。"""
        try:
            await self._click_text(page, field_text)
            await self._click_text(page, value_text)
        except RuntimeError:
            return

    async def _open_label_selector(self, page) -> None:
        """打开分类标签选择入口。"""
        for field_text in ("选择分类标签", "分类标签"):
            trigger = await self._dropdown_trigger_for_field(page, field_text)
            if trigger:
                if await self._click_locator_center(page, trigger) or await self._click_locator(trigger):
                    await page.wait_for_timeout(1200)
                    return
        for text in ("选择分类标签", "分类标签"):
            try:
                await self._click_text(page, text)
                await page.wait_for_timeout(1200)
                return
            except RuntimeError:
                continue
        raise RuntimeError("未找到分类标签入口")

    async def _ensure_custom_tags(self, page, tags: Iterable[str]) -> None:
        """确保素材卡片中包含规则要求的全部自定义标签。"""
        for tag in tags:
            body = await page.locator("body").inner_text(timeout=5000)
            if tag in body:
                continue
            input_box = await self._first_existing(
                page,
                (
                    "input[placeholder*='自定义标签']",
                    "input[placeholder*='标签']",
                    "textarea[placeholder*='标签']",
                ),
            )
            if not input_box:
                continue
            await input_box.fill(tag)
            await input_box.press("Enter")
            await page.wait_for_timeout(500)

    async def _submit_review(self, page) -> None:
        """发起送审，并确认送审弹窗。"""
        await self._click_text(page, "送审")
        await page.wait_for_timeout(2000)
        # await self._ensure_chameleon_modal(page)
        await self._click_text(page, "确定")
        await page.wait_for_timeout(3500)
        await self._click_if_present(page, "查看任务详情")

    async def _wait_task_success(
            self,
            page,
            progress: ProgressCallback | None,
            *,
            expected_attempts: int | None = None,
    ) -> None:
        """轮询任务状态，失败时尝试重试，直到全部成功或达到重试上限。

        默认按视频数量走（与上传素材数相当），间隔减半，
        只点一次"刷新列表"，避免短时间内连续点两次造成抖动。
        """
        max_attempts = max(
            expected_attempts or self.max_status_retries,
            1,
        )
        # 间隔减半，最小 3s，避免空转
        interval_ms = max(int(self.refresh_interval_seconds * 500), 3000)
        for attempt in range(1, max_attempts + 3):
            body = await page.locator("body").inner_text(timeout=5000)
            if "全部成功" in body:
                return
            if "已失败" in body:
                raise RuntimeError("任务执行失败")
            self._emit(progress, f"刷新任务状态，第 {attempt}/{max_attempts} 次")
            await self._click_if_present(page, "刷新列表")
            await page.wait_for_timeout(interval_ms)
        raise RuntimeError("任务状态未在重试次数内变为全部成功")

    async def _fill_cids_for_task(
            self,
            page,
            items: list[UserGrowthVideoItem],
            task_id: str,
            progress: ProgressCallback | None,
    ) -> None:
        """按任务ID进入任务详情与素材页，读取 CID 后回填到素材条目。"""
        try:
            page = await self._open_task_detail_for_task_id(
                page,
                task_id,
                progress,
                expected_attempts=max(len(items), 1),
            )
            material_page = await self._open_material_list_page(page)
            cids = await self._read_cids_from_search_input(material_page)
        except Exception as exc:
            await self._snapshot_error(
                page,
                f"task_{task_id}_fill_cids_fallback",
                exc=exc,
                extra=f"task_id={task_id}, items={len(items)}",
            )
            await self._fill_cids_from_detail(page, items)
            return

        if not cids:
            await self._snapshot_error(
                material_page,
                f"task_{task_id}_cid_not_found",
                extra=f"task_id={task_id}, items={len(items)}",
            )
            raise RuntimeError(f"任务 {task_id} 未读取到 CID")
        if len(cids) < len(items):
            await self._snapshot_error(
                material_page,
                f"task_{task_id}_cid_count_mismatch",
                extra=f"task_id={task_id}, expected={len(items)}, got={len(cids)}",
            )
            raise RuntimeError(f"任务 {task_id} 读取到的 CID 数量不足：期望 {len(items)}，实际 {len(cids)}")

        for item, cid in zip(items, cids):
            item.cid = cid
            item.cid_material_type = await self._read_material_type_by_cid(material_page, cid) or item.material_type
            item.status = "success"
            item.message = "上传并送审成功"

    async def _read_current_task_id(self, page) -> str:
        """从当前任务列表首条数据读取任务ID。"""
        await self._wait_task_list_ready(page)
        task_id_input = await self._wait_first_existing(
            page,
            (
                "input[placeholder*='任务ID']",
                "input[placeholder*='任务']",
            ),
            timeout_ms=10000,
        )
        if not task_id_input:
            raise RuntimeError("未找到任务ID输入框")
        try:
            return self._extract_digits(await task_id_input.input_value(timeout=2000))
        except Exception:
            return self._extract_digits(await self._locator_text(task_id_input, timeout_ms=2000))

    async def _wait_task_list_ready(self, page, timeout_ms: int = 30000) -> None:
        """等待任务ID输入框中出现值后再读取任务ID。"""

        async def task_list_ready():
            task_id_input = await self._first_existing(
                page,
                (
                    "input[placeholder*='任务ID']",
                    "input[placeholder*='任务']",
                ),
            )
            if not task_id_input:
                return False
            try:
                value = await task_id_input.input_value(timeout=1500)
            except Exception:
                value = await self._locator_text(task_id_input, timeout_ms=1500)
            return bool(self._extract_digits(value))

        if await self._wait_for_result(task_list_ready, timeout_ms=timeout_ms, interval_ms=500):
            return
        raise RuntimeError("等待任务ID输入框渲染超时，未读取到任务ID")

    async def _open_task_detail_for_task_id(
            self,
            page,
            task_id: str,
            progress: ProgressCallback | None,
            *,
            expected_attempts: int | None = None,
    ):
        """根据任务ID定位任务行，等待成功后点击查看详情。"""
        await self._search_task_by_id(page, task_id)
        await self._wait_task_row_success(
            page,
            task_id,
            progress,
            expected_attempts=expected_attempts,
        )
        row = await self._find_task_row(page, task_id)
        if not row:
            await self._snapshot_error(
                page,
                f"task_{task_id}_row_not_found",
                extra=f"task_id={task_id}",
            )
            raise RuntimeError(f"未找到任务 {task_id} 对应行")
        if not await self._click_first_visible_locator(
                row.get_by_text("查看详情", exact=True).first,
                row.locator("a:has-text('查看详情')").first,
                row.locator("button:has-text('查看详情')").first,
        ):
            raise RuntimeError(f"未打开任务 {task_id} 详情")
        await page.wait_for_timeout(2500)
        return page

    async def _search_task_by_id(self, page, task_id: str) -> None:
        """在任务列表页用任务ID精确筛选当前任务。"""
        await self._click_if_present(page, "操作任务")
        search_input = await self._wait_first_existing(
            page,
            (
                "input[placeholder*='任务ID']",
            ),
            timeout_ms=20000,
        )
        if search_input:
            await self._set_task_id_search_input(page, search_input, task_id)
            await page.wait_for_timeout(800)
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(2500)
            return
        await page.wait_for_timeout(2500)

    async def _set_task_id_search_input(self, page, locator, task_id: str) -> None:
        """稳定写入任务ID筛选框，优先清空后 fill，并校验最终值。"""
        target_value = str(task_id or "").strip()
        if not target_value:
            raise RuntimeError("任务ID为空，无法写入搜索框")
        try:
            await locator.click(force=True, timeout=5000)
        except Exception:
            pass
        try:
            await locator.fill("", timeout=5000)
            await locator.fill(target_value, timeout=5000)
            current_value = await locator.input_value(timeout=2000)
            if self._extract_digits(current_value) == self._extract_digits(target_value):
                return
        except Exception:
            pass
        try:
            await locator.click(force=True, timeout=5000)
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")
            await self._keyboard_type(page, target_value)
            current_value = await locator.input_value(timeout=2000)
            if self._extract_digits(current_value) == self._extract_digits(target_value):
                return
        except Exception:
            pass
        try:
            await locator.evaluate(
                """(node, value) => {
                    node.value = value;
                    node.dispatchEvent(new Event('input', { bubbles: true }));
                    node.dispatchEvent(new Event('change', { bubbles: true }));
                }""",
                target_value,
            )
            current_value = await locator.input_value(timeout=2000)
            if self._extract_digits(current_value) == self._extract_digits(target_value):
                return
        except Exception:
            pass
        raise RuntimeError(f"任务ID未成功写入搜索框: {target_value}")

    async def _wait_task_row_success(
            self,
            page,
            task_id: str,
            progress: ProgressCallback | None,
            *,
            expected_attempts: int | None = None,
    ) -> None:
        """轮询指定任务行状态直到全部成功。

        默认按视频数量走，间隔减半，只点一次"刷新列表"避免连续两次抖动。
        """
        max_attempts = max(
            expected_attempts or self.max_status_retries,
            1,
        )
        interval_ms = max(int(self.refresh_interval_seconds * 500), 3000)
        for attempt in range(1, max_attempts + 3):
            row = await self._find_task_row(page, task_id)
            row_text = _compact_text(await self._locator_text(row, timeout_ms=3000)) if row else ""
            if "全部成功" in row_text:
                return
            if "失败" in row_text:
                raise RuntimeError(f"任务 {task_id} 执行失败")
            self._emit(progress, f"等待任务 {task_id} 完成，第 {attempt}/{max_attempts} 次")
            await self._click_if_present(page, "刷新列表")
            await page.wait_for_timeout(interval_ms)
            await self._search_task_by_id(page, task_id)
        raise RuntimeError(f"任务 {task_id} 未在重试次数内变为全部成功")

    async def _open_material_list_page(self, page):
        """从任务详情中打开素材/文案列表页，兼容新标签页和当前页跳转。"""
        before_pages = list(page.context.pages)
        before_url = page.url
        for text in ("素材/文案列表查看", "素材列表查看", "文案列表查看", "素材查看"):
            if not await self._click_text_or_locator(page, text):
                continue
            target_page = await self._wait_page_change_or_new_page(page, before_pages, before_url, timeout_ms=15000)
            if target_page:
                await target_page.wait_for_timeout(2500)
                return target_page
        raise RuntimeError("未打开素材/文案列表页")

    async def _read_cids_from_search_input(self, page) -> list[str]:
        """读取素材管理页搜索框中的 CID 列表。"""
        search_input = await self._wait_first_existing(
            page,
            (
                "input[placeholder*='全局搜索']",
                "input[placeholder*='搜索']",
                "input.arco-input",
            ),
            timeout_ms=None,
        )
        if search_input:
            return await self._wait_cids_from_input(search_input)
        text = await self._body_text(page, timeout_ms=5000)
        return self._extract_cids(text)

    async def _fill_cids_from_detail(self, page, items: list[UserGrowthVideoItem]) -> None:
        """进入详情页读取 CID，并回写到素材条目。"""
        await self._click_if_present(page, "查看详情")
        await page.wait_for_timeout(3000)
        cids = await self._copy_or_read_cids(page)
        if not cids:
            await self._snapshot_error(
                page,
                "cid_not_found",
                extra=f"items={len(items)}",
            )
            raise RuntimeError("未读取到 CID")
        for item, cid in zip(items, cids):
            item.cid = cid
            item.cid_material_type = await self._read_material_type_by_cid(page, cid) or item.material_type
            item.status = "success"
            item.message = "上传并送审成功"

    async def _copy_or_read_cids(self, page) -> list[str]:
        """优先使用一键复制对象 ID，失败时从页面文本中提取 CID。"""
        try:
            await self._click_text(page, "一键复制对象id")
            await page.wait_for_timeout(500)
            text = await page.evaluate(
                "navigator.clipboard && navigator.clipboard.readText ? navigator.clipboard.readText() : ''")
        except Exception:
            text = ""
        if not text:
            text = await page.locator("body").inner_text(timeout=5000)
        return self._extract_cids(text)

    async def _read_material_type_by_cid(self, page, cid: str) -> str:
        """按 CID 查看素材详情，读取分类标签作为回填素材类型。"""
        try:
            row = page.locator(f"tr:has-text('{cid}')").first
            if await row.count():
                button = row.locator("text=查看素材").first
                if await button.count():
                    await button.click()
                    await page.wait_for_timeout(2000)
                    body = await page.locator("body").inner_text(timeout=5000)
                    match = re.search(r"分类标签[:：]?\s*([^\n]+)", body)
                    await self._click_if_present(page, "关闭")
                    if match:
                        return display_material_from_label(match.group(1))
        except Exception:
            return ""
        return ""

    async def _wait_selected_count(self, page, minimum: int, timeout_ms: int = 8000) -> bool:
        """等待页面“已选中”数量达到指定值。"""

        async def enough_selected() -> bool:
            return await self._selected_count(page) >= minimum

        return bool(await self._wait_for_result(enough_selected, timeout_ms=timeout_ms, interval_ms=500))

    async def _selected_count(self, page) -> int:
        """从页面文本中读取当前已选中的行数。"""
        body = await self._body_text(page, timeout_ms=2000)
        match = re.search(r"已选中\s*(\d+)", body)
        if match:
            return int(match.group(1))
        return 0

    async def _select_row_by_file_name(self, page, file_name: str) -> bool:
        """通过文件名定位列表行，并点击该行的 Arco 复选框。"""
        for locator in (
                page.locator(f"tr:has-text('{file_name}')").first,
                page.locator(f"[role='row']:has-text('{file_name}')").first,
                page.locator(f".arco-table-tr:has-text('{file_name}')").first,
                page.locator(f"[class*='arco-table-tr']:has-text('{file_name}')").first,
                page.locator(f"[class*='arco-table-row']:has-text('{file_name}')").first,
                page.locator(f".ant-table-row:has-text('{file_name}')").first,
        ):
            try:
                if await locator.count() and await locator.is_visible():
                    return await self._click_visible_checkbox_box(
                        locator,
                        "label.arco-checkbox, .arco-checkbox-mask-wrapper, .arco-checkbox-mask, .arco-checkbox, label",
                    )
            except Exception:
                continue
        text_locator = page.get_by_text(file_name, exact=True).first
        for xpath in (
                "xpath=ancestor::tr[1]",
                "xpath=ancestor::*[@role='row'][1]",
                "xpath=ancestor::*[contains(@class, 'arco-table-tr')][1]",
                "xpath=ancestor::*[contains(@class, 'arco-table-row')][1]",
                "xpath=ancestor::*[contains(@class, 'ant-table-row')][1]",
        ):
            try:
                row = text_locator.locator(xpath)
                if await row.count() and await row.is_visible():
                    return await self._click_visible_checkbox_box(
                        row,
                        "label.arco-checkbox, .arco-checkbox-mask-wrapper, .arco-checkbox-mask, .arco-checkbox, label",
                    )
            except Exception:
                continue
        return await self._select_row_by_file_name_dom(page, file_name)

    async def _select_row_by_file_name_dom(self, page, file_name: str) -> bool:
        """按文件名定位行并点击 Arco checkbox 的兜底。"""
        # 列表实现可能是 table、div row 或虚拟表格，这里统一从可见行里按文件名过滤。
        rows = page.locator(
            ".arco-table-tr, [class*='arco-table-tr'], [class*='arco-table-row'], tr, [role='row']"
        ).filter(has_text=file_name)
        for row in await self._visible_locators(rows, limit=30):
            if await self._click_visible_checkbox_box(
                    row,
                    "label.arco-checkbox, .arco-checkbox-mask-wrapper, .arco-checkbox-mask",
            ):
                return True
        return False

    async def _click_visible_checkbox_box(self, scope, selector: str) -> bool:
        """在指定区域内点击可见的复选框外壳，并确认是否选中。"""
        boxes = scope.locator(selector)
        try:
            count = min(await boxes.count(), 30)
        except Exception:
            return False
        for index in range(count):
            box = boxes.nth(index)
            try:
                if not await box.is_visible():
                    continue
                if await self._checkbox_box_is_checked(box):
                    return True
                await box.scroll_into_view_if_needed(timeout=3000)
                await box.click(force=True, timeout=5000)
                await self._sleep(0.2)
                if await self._checkbox_box_is_checked(box):
                    return True
            except Exception:
                continue
        return False

    async def _checkbox_box_is_checked(self, box) -> bool:
        """判断 Arco/原生复选框外壳是否已经处于选中状态。"""
        try:
            input_box = box.locator("input[type='checkbox']").first
            if await input_box.count():
                return await input_box.is_checked()
        except Exception:
            pass
        # Arco checkbox 经常把状态挂在外层 class 上，而不是原生 input checked。
        for locator in (box, box.locator("xpath=ancestor::*[contains(@class, 'arco-checkbox')][1]")):
            try:
                class_name = await locator.get_attribute("class")
                if class_name and "checked" in class_name:
                    return True
            except Exception:
                continue
        return False

    async def _safe_goto(self, page, url: str) -> None:
        """打开页面并做简单重试，降低偶发网络或白屏影响。"""
        last_error: Exception | None = None
        for _ in range(3):
            try:
                await page.goto(url, wait_until="domcontentloaded")
                return
            except Exception as exc:
                last_error = exc
                await page.wait_for_timeout(2500)
        raise RuntimeError(f"页面打开失败：{url}: {last_error}")

    async def _click_text(self, page, text: str) -> None:
        """按文本内容点击按钮、链接或普通可点击文字。"""
        if await self._click_first_visible_locator(
                page.get_by_text(text, exact=True).first,
                page.get_by_text(text, exact=False).first,
                page.locator(f"button:has-text('{text}')").first,
                page.locator(f"a:has-text('{text}')").first,
        ):
            return
        raise RuntimeError(f"未找到可点击文本：{text}")

    async def _click_first(self, page, selectors: tuple[str, ...]) -> None:
        """按选择器顺序点击第一个可见控件。"""
        if await self._click_first_visible_locator(*(page.locator(selector).first for selector in selectors)):
            return
        raise RuntimeError(f"未找到可点击控件：{selectors}")

    async def _click_first_visible_locator(self, *locators) -> bool:
        """点击一组 locator 中第一个可见元素。"""
        for locator in locators:
            if await self._click_locator(locator):
                return True
        return False

    async def _click_locator(self, locator) -> bool:
        """点击单个可见 locator，失败时返回 False。"""
        try:
            if not await locator.count() or not await locator.is_visible():
                return False
            await locator.scroll_into_view_if_needed(timeout=3000)
            await locator.click(force=True)
            return True
        except Exception:
            return False

    async def _click_locator_center(self, page, locator) -> bool:
        """用真实鼠标点击 locator 中心点。"""
        try:
            if not await locator.count() or not await locator.is_visible():
                return False
            await locator.scroll_into_view_if_needed(timeout=3000)
            box = await locator.bounding_box(timeout=3000)
            if not box:
                return False
            await page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            return True
        except Exception:
            return False

    async def _visible_locators(self, locators, limit: int = 30) -> list:
        """返回 locator 集合中可见的前若干个元素。"""
        try:
            count = min(await locators.count(), limit)
        except Exception:
            return []
        visible = []
        for index in range(count):
            locator = locators.nth(index)
            try:
                if await locator.is_visible():
                    visible.append(locator)
            except Exception:
                continue
        return visible

    async def _click_if_present(self, page, text: str) -> None:
        """如果页面上存在某个文本按钮就点击，不存在则忽略。"""
        try:
            await self._click_text(page, text)
        except RuntimeError:
            return

    async def _click_text_or_locator(self, page, text: str) -> bool:
        """点击文本；若不存在则返回 False。"""
        try:
            await self._click_text(page, text)
            return True
        except RuntimeError:
            return False

    async def _fill_first(self, page, selectors: tuple[str, ...], value: str) -> None:
        """找到第一个可见输入框并输入指定文本。"""
        locator = await self._first_existing(page, selectors)
        if not locator:
            raise RuntimeError(f"未找到输入框：{selectors}")
        await self._type_into_locator(locator, page, value)

    async def _type_into_locator(self, locator, page, value: str) -> None:
        """兼容 fill、键盘输入和坐标点击三种方式向输入框写值。

        优先 fill 一次性写入，避免逐字键入对账号/密码/订单ID
        这类短文本带来的额外耗时和触发前端额外逻辑。
        """
        try:
            await locator.fill(value, timeout=5000)
            return
        except Exception:
            pass
        try:
            await locator.click(force=True, timeout=5000)
            await self._keyboard_type(page, value)
            return
        except Exception:
            pass
        box = await locator.bounding_box(timeout=5000)
        if not box:
            raise RuntimeError("输入框不可点击")
        await page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        await self._keyboard_type(page, value)

    async def _first_existing(self, page, selectors: tuple[str, ...]):
        """返回第一个存在且可见的元素。"""
        for selector in selectors:
            locator = page.locator(selector).first
            try:
                if await locator.count() and await locator.is_visible():
                    return locator
            except Exception:
                continue
        return None

    async def _first_attached(self, page, selectors: tuple[str, ...]):
        """返回第一个已挂载到 DOM 的元素，适合隐藏 file input。"""
        for selector in selectors:
            locator = page.locator(selector).first
            try:
                if await locator.count():
                    return locator
            except Exception:
                continue
        return None

    async def _wait_first_existing(self, page, selectors: tuple[str, ...], timeout_ms: int = 20000):
        """轮询等待某组选择器中任意一个可见元素出现。"""

        async def find_locator():
            return await self._first_existing(page, selectors)

        return await self._wait_for_result(find_locator, timeout_ms=timeout_ms, interval_ms=800)

    async def _locator_text(self, locator, timeout_ms: int = 3000) -> str:
        """安全读取 locator 文本。"""
        if not locator:
            return ""
        try:
            return await locator.inner_text(timeout=timeout_ms)
        except Exception:
            return ""

    async def _body_text(self, page, timeout_ms: int = 5000) -> str:
        """读取页面 body 文本；读取失败时返回空字符串。"""
        try:
            return await page.locator("body").inner_text(timeout=timeout_ms)
        except Exception:
            return ""

    async def _wait_for_page_text(
            self,
            page,
            texts: tuple[str, ...],
            *,
            timeout_ms: int | None = 15000,
            raise_on_timeout: bool = True,
    ) -> bool:
        """等待页面出现指定文本，必要时超时抛错。"""

        async def has_text() -> bool:
            body = await self._body_text(page, timeout_ms=2000)
            return any(text in body for text in texts)

        if await self._wait_for_result(has_text, timeout_ms=timeout_ms, interval_ms=800):
            return True
        if raise_on_timeout:
            raise RuntimeError(f"页面未出现预期内容：{', '.join(texts)}")
        return False

    async def _wait_for_result(self, producer, *, timeout_ms: int | None, interval_ms: int = 800):
        """按固定间隔轮询异步函数，直到返回真值或超时。"""
        deadline = None if timeout_ms is None else asyncio.get_event_loop().time() + timeout_ms / 1000
        while deadline is None or asyncio.get_event_loop().time() < deadline:
            result = await producer()
            if result:
                return result
            await self._sleep(interval_ms / 1000)
        return None

    async def _retry(
            self,
            operation,
            *,
            description: str,
            max_attempts: int = 3,
            base_interval_ms: int = 5000,
    ):
        """
        异步操作重试：
        - 最大尝试次数默认3次
        - 指数退避等待
          第1次失败 -> 2s
          第2次失败 -> 4s
        """

        last_error: Exception | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                result = await operation(attempt)

                # 返回False表示失败，其他认为成功
                if result is not False:
                    return result

            except Exception as exc:
                last_error = exc

            if attempt < max_attempts:
                wait_ms = base_interval_ms * (2 ** (attempt - 1))

                await self._sleep(
                    wait_ms / 1000
                )

        raise RuntimeError(
            f"{description} failed after {max_attempts} attempts"
        ) from last_error

    async def _wait_page_change_or_new_page(
            self,
            page,
            before_pages: list,
            before_url: str,
            timeout_ms: int | None = 15000,
    ):
        """等待点击后的当前页跳转或新标签页打开。"""
        deadline = None if timeout_ms is None else asyncio.get_event_loop().time() + timeout_ms / 1000
        before_ids = {id(candidate) for candidate in before_pages}
        while deadline is None or asyncio.get_event_loop().time() < deadline:
            for candidate in reversed(page.context.pages):
                if candidate.is_closed():
                    continue
                try:
                    await candidate.wait_for_load_state("domcontentloaded", timeout=1000)
                except Exception:
                    pass
                is_new_page = id(candidate) not in before_ids and candidate.url not in {"about:blank", before_url}
                if is_new_page:
                    self._wrap_page_speed(candidate)
                    return candidate
            if page.url != before_url:
                self._wrap_page_speed(page)
                return page
            await self._sleep(0.5)
        return None

    async def _first_table_row(self, page):
        """读取当前页第一个可见表格数据行。"""
        rows = page.locator("tbody tr")
        try:
            count = min(await rows.count(), 10)
        except Exception:
            return None
        for index in range(count):
            row = rows.nth(index)
            try:
                if await row.is_visible():
                    return row
            except Exception:
                continue
        return None

    async def _find_task_row(self, page, task_id: str):
        """按任务ID匹配任务列表中的数据行。"""
        rows = page.locator("tbody tr")
        try:
            count = min(await rows.count(), 20)
        except Exception:
            return None
        compact_task_id = _compact_text(task_id)
        for index in range(count):
            row = rows.nth(index)
            row_text = _compact_text(await self._locator_text(row, timeout_ms=2000))
            if compact_task_id and compact_task_id in row_text:
                return row
        return None

    def _extract_digits(self, text: str) -> str:
        """提取文本中第一个连续任务ID数字。"""
        compact = re.sub(r"\s+", "", text or "")
        match = re.search(r"\b\d{7,}\b", compact)
        return match.group(0) if match else ""

    def _extract_cids(self, text: str) -> list[str]:
        """从任意文本中提取 CID。"""
        return re.findall(r"\b[a-f0-9]{24,40}\b", text or "", flags=re.IGNORECASE)

    async def _wait_and_click_text(
            self,
            page,
            text: str,
            timeout_ms: int | None = 30000,
    ):
        """等待文本出现并点击"""
        timeout = 0 if timeout_ms is None else timeout_ms

        locator = page.get_by_text(
            text,
            exact=True
        ).first

        await locator.wait_for(
            state="visible",
            timeout=timeout
        )

        await locator.click(timeout=timeout)

    async def _click_text_and_wait_page(
            self,
            page,
            text: str,
            *,
            timeout_ms: int | None = 30000,
    ):
        """点击文本后等待新标签页出现或当前页跳转；timeout_ms=None 时不设总超时。"""
        before_pages = list(page.context.pages)
        before_url = page.url
        await self._wait_and_click_text(page, text, timeout_ms=timeout_ms)
        target_page = await self._wait_page_change_or_new_page(
            page,
            before_pages,
            before_url,
            timeout_ms=timeout_ms,
        )
        if not target_page:
            raise RuntimeError(f"点击{text}后未进入目标页面")
        try:
            await target_page.bring_to_front()
        except Exception:
            pass
        return target_page

    async def _wait_cids_from_input(
            self,
            locator,
            *,
            timeout_ms: int | None = None,
            interval_ms: int = 800,
    ) -> list[str]:
        """等待输入框里真正出现 CID 再读取。"""

        async def read_cids():
            try:
                text = await locator.input_value(timeout=2000)
            except Exception:
                try:
                    text = await self._locator_text(locator, timeout_ms=2000)
                except Exception:
                    return None
            cids = self._extract_cids(text)
            return cids or None

        cids = await self._wait_for_result(
            read_cids,
            timeout_ms=timeout_ms,
            interval_ms=interval_ms,
        )
        return cids or []

    async def _click_creative_unit_select_all_checkbox(self, page):
        """在 unit tab 全选所有行。"""
        candidates = (
            page.locator(".arco-table thead .arco-checkbox-mask").first,
            page.locator(".arco-table thead .arco-checkbox-mask-wrapper").first,
            page.locator(".arco-table thead label.arco-checkbox").first,
            page.locator(".arco-table thead .arco-checkbox").first,
        )

        async def click_select_all() -> bool:
            for checkbox in candidates:
                try:
                    if not await checkbox.count() or not await checkbox.is_visible():
                        continue
                    await checkbox.scroll_into_view_if_needed(timeout=3000)
                    if await self._checkbox_box_is_checked(checkbox):
                        return True
                    if not await self._click_locator(checkbox):
                        continue
                    await page.wait_for_timeout(1200)
                    if await self._checkbox_box_is_checked(checkbox):
                        return True
                except Exception:
                    continue
            return False

        while not await click_select_all():
            await page.wait_for_timeout(1200)
        await page.wait_for_timeout(1500)

    async def _wait_and_click_table_select_all(
            self,
            page,
            *,
            timeout_ms: int | None = None,
    ) -> None:
        """等待表格表头全选复选框出现并点击；默认不设总超时。"""

        candidates = (
            page.locator(".arco-table thead .arco-checkbox-mask").first,
            page.locator(".arco-table thead .arco-checkbox-mask-wrapper").first,
            page.locator(".arco-table thead label.arco-checkbox").first,
            page.locator(".arco-table thead .arco-checkbox").first,
            # 兜底：弹层里也可能直接放一个「全选」按钮
            page.get_by_role("button", name="全选").first,
            page.locator("button:has-text('全选')").first,
        )

        async def attempt() -> bool:
            for checkbox in candidates:
                try:
                    if not await checkbox.count() or not await checkbox.is_visible():
                        continue
                    await checkbox.scroll_into_view_if_needed(timeout=3000)
                    # 已是选中态直接视为成功
                    if await self._checkbox_box_is_checked(checkbox):
                        return True
                    if not await self._click_locator(checkbox):
                        continue
                    await page.wait_for_timeout(800)
                    if await self._checkbox_box_is_checked(checkbox):
                        return True
                except Exception:
                    continue
            return False

        deadline = None if timeout_ms is None else asyncio.get_event_loop().time() + timeout_ms / 1000
        while deadline is None or asyncio.get_event_loop().time() < deadline:
            if await attempt():
                return
            await page.wait_for_timeout(2000)
        raise RuntimeError("等待表格全选框超时")

    async def _snapshot(self, page, name: str, *, screenshot: bool = False) -> None:
        """保存当前页面文本和截图。

        正常流程的快照（screenshot=False）直接跳过，不写 .txt 也不写 .png，
        避免 debug_dir 被无意义快照塞满。
        错误场景请走 _snapshot_error，里面会用 screenshot=True 走完整流程。
        """
        if not screenshot:
            return
        if not self.debug_dir:
            return
        self.debug_dir.mkdir(parents=True, exist_ok=True)
        safe_name = "".join(char if char.isalnum() or char in ("_", "-") else "_" for char in name)
        try:
            body = await page.locator("body").inner_text(timeout=3000)
        except Exception as exc:
            body = f"<read body failed: {exc}>"
        (self.debug_dir / f"{safe_name}.txt").write_text(
            f"URL: {page.url}\n\n{body}", encoding="utf-8"
        )
        try:
            await page.screenshot(
                path=str(self.debug_dir / f"{safe_name}.png"),
                full_page=True,
            )
        except Exception:
            pass

    async def _snapshot_error(
            self,
            page,
            name: str,
            exc: BaseException | None = None,
            *,
            extra: str | None = None,
    ) -> None:
        """错误场景专用：截图 + 写页面文本 + 写详细错误日志到 run.log。

        exc 不为空时附带异常类型、消息和堆栈到 run.log。
        extra 是附加的纯文本上下文（例如 plan/order 标识）。
        """
        await self._snapshot(page, name, screenshot=True)
        if exc is None and extra is None:
            return
        lines = [
            f"[{datetime.now().isoformat(timespec='seconds')}] ERROR snapshot: {name}",
        ]
        if page is not None:
            try:
                lines.append(f"  url: {page.url}")
            except Exception:
                lines.append("  url: <unavailable>")
        if extra:
            lines.append(f"  context: {extra}")
        if exc is not None:
            lines.append(f"  exc_type: {type(exc).__name__}")
            lines.append(f"  exc_msg: {exc}")
            lines.append("  traceback:")
            lines.append("    " + "\n    ".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            ).rstrip())
        self._write_run_log("\n".join(lines))

    def _emit(self, progress: ProgressCallback | None, message: str) -> None:
        """向调用方发送一条进度消息。"""
        if progress:
            progress(message)

    def _cancel_requested(self) -> bool:
        return bool(self.cancel_event and self.cancel_event.is_set())

    def _raise_if_cancelled(self) -> None:
        if self._cancel_requested():
            raise UserGrowthCancelled("任务已取消")

    async def _watch_cancel(self, browser, progress: ProgressCallback | None = None) -> None:
        """后台监听取消事件，取消时关闭浏览器以打断 Playwright 无限等待。"""
        while not self._cancel_requested():
            await asyncio.sleep(0.5)
        self._emit(progress, "收到取消请求，正在关闭浏览器")
        try:
            await browser.close()
        except Exception:
            pass

    def _scale_ms(self, delay_ms: int | float, *, minimum_ms: int = 0) -> int:
        """按全局操作速度系数缩放毫秒级等待时长。"""
        scaled = int(round(float(delay_ms) / self.operation_speed_factor))
        return max(minimum_ms, scaled)

    def _scale_seconds(self, delay_seconds: int | float, *, minimum_seconds: float = 0.0) -> float:
        """按全局操作速度系数缩放秒级等待时长。"""
        scaled = float(delay_seconds) / self.operation_speed_factor
        return max(minimum_seconds, scaled)

    def _wrap_page_speed(self, page) -> None:
        """包装 page.wait_for_timeout，使现有页面等待自动遵循全局速度。"""
        if getattr(page, "_usergrowth_speed_wrapped", False):
            return
        original_wait_for_timeout = page.wait_for_timeout

        async def scaled_wait_for_timeout(delay_ms):
            self._raise_if_cancelled()
            remaining_ms = self._scale_ms(delay_ms)
            while remaining_ms > 0:
                self._raise_if_cancelled()
                step_ms = min(remaining_ms, 500)
                await original_wait_for_timeout(step_ms)
                remaining_ms -= step_ms
            self._raise_if_cancelled()

        page.wait_for_timeout = scaled_wait_for_timeout
        page._usergrowth_speed_wrapped = True

    async def _sleep(self, delay_seconds: int | float, *, minimum_seconds: float = 0.0) -> None:
        """使用全局操作速度系数执行 sleep。"""
        remaining = self._scale_seconds(delay_seconds, minimum_seconds=minimum_seconds)
        while remaining > 0:
            self._raise_if_cancelled()
            step = min(remaining, 0.5)
            await asyncio.sleep(step)
            remaining -= step
        self._raise_if_cancelled()

    async def _keyboard_type(self, page, value: str, delay_ms: int = 80) -> None:
        """按全局操作速度系数控制键盘输入节奏。"""
        await page.keyboard.type(value, delay=self._scale_ms(delay_ms))

    async def _wait_creative_unit_table_ready(self, page, timeout_ms: int | None) -> None:
        """等待创意单元页表格可操作，不设总超时。"""

        async def table_ready():
            for locator in (
                    page.locator(".arco-table thead .arco-checkbox-mask").first,
                    page.locator(".arco-table thead .arco-checkbox-mask-wrapper").first,
                    page.locator(".arco-table thead label.arco-checkbox").first,
                    page.locator(".arco-table thead .arco-checkbox").first,
            ):
                try:
                    if await locator.count() and await locator.is_visible():
                        return True
                except Exception:
                    continue
            return False

        if await self._wait_for_result(table_ready, timeout_ms=timeout_ms, interval_ms=500):
            return
        raise RuntimeError("确认提交后等待创意单元表格渲染超时")
