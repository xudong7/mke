"""验证：中栏分隔条可左右拖动缩放文献预览，且拖动后定位功能仍然生效。

需要后端 :8000 已启动（生产模式，托管 frontend/dist）。
运行：uv run python frontend/e2e/verify_drag.py
"""
import sys

from playwright.sync_api import sync_playwright

BASE = "http://localhost:8000"
results = []


def check(name: str, ok: bool, detail: str = ""):
    results.append((name, ok, detail))
    print(f"{'OK  ' if ok else 'FAIL'} {name}" + (f" — {detail}" if detail else ""))


def drag(page, strip, dx: int, steps: int = 10):
    bb = strip.bounding_box()
    x = bb["x"] + bb["width"] / 2
    y = bb["y"] + bb["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + dx, y, steps=steps)
    page.mouse.up()


with sync_playwright() as p:
    # 未下载 playwright 自带 chromium 时，退回系统 Edge（与 debug_pdf.py 一致）
    try:
        browser = p.chromium.launch(headless=True, channel="msedge")
    except Exception:
        browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1600, "height": 1000})
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    page.goto(BASE, wait_until="networkidle")
    page.wait_for_selector(".paper-item", timeout=20000)

    # 先选中论文（历史记录随选中论文显示），再用「查看」加载一次既有 run（才能测定位）
    page.locator(".paper-item").first.click()
    page.wait_for_selector(".run-history", timeout=15000)
    page.locator("button", has_text="查看").first.click()
    page.wait_for_selector(".results-table", timeout=20000)
    page.wait_for_timeout(2000)

    # ---------- 1. 分隔条可拖动 ----------
    check("分隔条存在且可拖动", page.locator(".edge-strip-drag").count() == 1)

    # ---------- 2. 拖动改变中栏/右栏宽度 ----------
    center_before = page.locator(".pane-center").bounding_box()["width"]
    right_before = page.locator(".sidebar-right").bounding_box()["width"]
    zoom_before = page.locator(".zoom-label").inner_text()

    drag(page, page.locator(".edge-strip-drag"), 140)
    page.wait_for_timeout(1500)

    center_after = page.locator(".pane-center").bounding_box()["width"]
    right_after = page.locator(".sidebar-right").bounding_box()["width"]
    check(
        "向右拖动 → 中栏变宽",
        center_after > center_before + 80,
        f"{center_before:.0f} → {center_after:.0f}",
    )
    check(
        "向右拖动 → 右栏变窄",
        right_after < right_before - 80,
        f"{right_before:.0f} → {right_after:.0f}",
    )
    check(
        "三栏总宽不变（未溢出）",
        abs((center_after + right_after) - (center_before + right_before)) < 5,
    )

    # ---------- 3. PDF 适应宽度后缩放随之变化 ----------
    zoom_after = page.locator(".zoom-label").inner_text()
    check("PDF 缩放随之变化", zoom_after != zoom_before, f"{zoom_before} → {zoom_after}")

    # ---------- 4. 反向拖动可拖回 ----------
    drag(page, page.locator(".edge-strip-drag"), -80)
    page.wait_for_timeout(1200)
    center_back = page.locator(".pane-center").bounding_box()["width"]
    check("反向拖动可缩回", center_back < center_after - 40, f"{center_after:.0f} → {center_back:.0f}")

    # ---------- 5. 定位仍然生效 ----------
    page.locator('[data-record-index="0"]').first.click()
    page.wait_for_timeout(600)
    # 用「字段引用」区的「定位全部引用句」按钮（最可靠：第一条 .citation-locate 属于
    # 关键字段区的「分析类型」，该字段通常没有引用句，点了不会出高亮）
    locate = page.locator(".detail-citations .citation-locate")
    if locate.count() == 0:
        check("该 run 有字段引用可供定位", False, "未找到 .detail-citations")
    else:
        locate.first.click()
        page.wait_for_timeout(2500)
        n_before = page.locator(".highlight-box").count()
        check("点击定位后出现高亮框", n_before > 0, f"highlight-box={n_before}")

        # ---------- 6. 拖动后高亮框仍然存在（关键需求） ----------
        drag(page, page.locator(".edge-strip-drag"), -120)
        page.wait_for_timeout(2500)
        n_after = page.locator(".highlight-box").count()
        check(
            "拖动分隔条后高亮框仍然存在",
            n_after > 0,
            f"{n_before} → {n_after}",
        )

        # ---------- 7. 拖动后再次定位仍然可用 ----------
        locate.first.click()
        page.wait_for_timeout(2500)
        check(
            "拖动后再次定位仍生效",
            page.locator(".highlight-box").count() > 0,
            f"highlight-box={page.locator('.highlight-box').count()}",
        )

    # ---------- 8. 手动缩放后拖动仍能自适应宽度 ----------
    # 回归：点 +/− 会退出「适应宽度」模式，拖动若不适配，页面会超出容器被截断
    page.locator(".viewer-toolbar button", has_text="+").click()
    page.wait_for_timeout(700)
    drag(page, page.locator(".edge-strip-drag"), -150)
    page.wait_for_timeout(1300)
    fit = page.evaluate(
        """() => {
            const sc = document.querySelector('.pdf-scroll');
            const pc = document.querySelector('.page-container');
            return Math.round(pc.getBoundingClientRect().width) - (sc.clientWidth - 48);
        }"""
    )
    check("手动缩放(+)后拖动仍自适应（画面不被截断）", fit <= 0, f"超出 {fit}px")

    # ---------- 9. 左侧「历史解析结果」可收起 / 展开 ----------
    n0 = page.locator(".run-history-item").count()
    page.locator(".run-history-header").click()
    page.wait_for_timeout(400)
    n1 = page.locator(".run-history-item").count()
    page.locator(".run-history-header").click()
    page.wait_for_timeout(400)
    n2 = page.locator(".run-history-item").count()
    check("历史解析结果可收起", n0 > 0 and n1 == 0, f"{n0} → {n1}")
    check("历史解析结果可展开恢复", n2 == n0, f"{n1} → {n2}")

    check("无 JS 运行时错误", len(errors) == 0, "; ".join(errors[:2]))

    browser.close()

failed = [r for r in results if not r[1]]
print(f"\n{len(results) - len(failed)}/{len(results)} 通过")
sys.exit(1 if failed else 0)
