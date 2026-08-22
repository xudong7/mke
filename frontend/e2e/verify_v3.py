"""MKE Web v3 端到端验证（需要后端 :8000 + 前端 :5173 已启动）

覆盖 v3 的 5 项改版 + v2 回归：
手柄位置/中栏折叠/页面滚动修复/批注浮层与 tab/步骤详情定制渲染。
运行：uv run python frontend/e2e/verify_v3.py
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

SHOT_DIR = Path("/tmp/mke_ui_v3")
SHOT_DIR.mkdir(exist_ok=True)
BASE = "http://localhost:5173"

results = []


def check(name: str, ok: bool, detail: str = ""):
    results.append((name, ok, detail))
    print(f"{'✅' if ok else '❌'} {name}" + (f" — {detail}" if detail and not ok else ""))


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1600, "height": 1000})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    page.goto(BASE)
    page.wait_for_load_state("networkidle")
    page.wait_for_selector(".paper-item", timeout=15000)

    # ============ 1. 手柄位置（三区竖直居中，无重叠） ============
    strips = page.locator(".edge-strip")
    check("三区手柄存在", strips.count() == 3, f"count={strips.count()}")
    left_strip = page.locator(".edge-strip-left").bounding_box()
    center_bb = page.locator(".pane-center").bounding_box()
    check("左侧手柄位于屏幕左缘", left_strip["x"] < 2, f"x={left_strip['x']}")
    check(
        "左侧手柄竖直居中于面板",
        abs((left_strip["y"] + left_strip["height"] / 2) - (center_bb["y"] + center_bb["height"] / 2)) < 12,
    )
    center_strip = page.locator(".edge-strip-center").bounding_box()
    check(
        "中部手柄贴邻中栏右缘",
        abs(center_strip["x"] - (center_bb["x"] + center_bb["width"])) < 3,
        f"strip x={center_strip['x']:.0f}, center right={center_bb['x'] + center_bb['width']:.0f}",
    )
    page.screenshot(path=str(SHOT_DIR / "01_handles.png"))

    # ============ 2. 折叠/恢复（含中栏） ============
    # 左栏折叠
    page.locator(".edge-strip-left").click()
    page.wait_for_timeout(500)
    check("左栏折叠", page.locator(".sidebar-left").count() == 0 and page.locator(".sidebar-rail").count() >= 1)
    page.locator(".sidebar-rail").first.click()
    page.wait_for_timeout(500)
    check("左栏恢复", page.locator(".sidebar-left").count() == 1)

    # 中栏折叠 → 看板占据中栏释放的空间
    kanban_before = page.locator(".sidebar-right").bounding_box()["width"]
    page.locator(".edge-strip-center").click()
    page.wait_for_timeout(500)
    kanban_w = page.locator(".sidebar-right").bounding_box()["width"]
    check("中栏折叠后看板显著变宽", kanban_w > kanban_before + 500,
          f"{kanban_before:.0f} → {kanban_w:.0f}")
    check("中栏折叠出现 rail-center", page.locator(".rail-center").count() == 1)
    page.screenshot(path=str(SHOT_DIR / "02_center_collapsed.png"))
    page.locator(".rail-center").click()
    page.wait_for_timeout(500)
    check("中栏恢复", page.locator(".pane-center").count() == 1)

    # 右栏折叠
    page.locator(".edge-strip-right").click()
    page.wait_for_timeout(500)
    check("右栏折叠", page.locator(".kanban").count() == 0)
    page.locator(".sidebar-rail").last.click()
    page.wait_for_timeout(500)
    check("右栏恢复", page.locator(".kanban").count() > 0)

    # ============ 3. 页面滚动修复 ============
    page.locator(".paper-item").first.click()
    page.wait_for_selector("canvas", timeout=20000)
    page.wait_for_timeout(1500)
    scroll_h = page.evaluate("document.documentElement.scrollHeight")
    inner_h = page.evaluate("window.innerHeight")
    check("页面不整体滚动", scroll_h <= inner_h + 1, f"scrollH={scroll_h} innerH={inner_h}")
    pane_h = page.locator(".pane-center").bounding_box()["height"]
    check("中栏高度 == 视口-48", abs(pane_h - (inner_h - 48)) < 3, f"{pane_h:.0f} vs {inner_h - 48}")
    pdf_scroll = page.locator(".pdf-scroll")
    pdf_scroll.evaluate("el => { el.scrollTop = 400; }")
    page.wait_for_timeout(300)
    st = pdf_scroll.evaluate("el => el.scrollTop")
    check("PDF 区内部滚动生效", st > 100, f"scrollTop={st}")

    # ============ 4. 批注：hover 触发 + 浮层 + tab ============
    # 先跑全部运行得到结果（真实 LLM）
    page.locator(".kanban-actions .btn-primary", has_text="全部运行").click()
    page.wait_for_timeout(2000)
    for _ in range(60):
        page.wait_for_timeout(5000)
        done = page.locator(".timeline-node.status-done").count()
        err = page.locator(".timeline-node.status-error").count()
        if done == 5 or err > 0:
            break
    check("runAll 5/5（回归）", done == 5, f"done={done}")
    page.wait_for_selector(".results-table", timeout=15000)

    # 初始 opacity 0
    op0 = page.locator(".results-row").first.locator(".anno-add").evaluate(
        "el => getComputedStyle(el).opacity"
    )
    check("批注按钮默认隐藏", op0 == "0", f"opacity={op0}")
    # hover 行 → 显示
    page.locator(".results-row").first.hover()
    page.wait_for_timeout(300)
    op1 = page.locator(".results-row").first.locator(".anno-add").evaluate(
        "el => getComputedStyle(el).opacity"
    )
    check("hover 行后批注按钮显示", op1 == "1", f"opacity={op1}")
    # 点击 → 浮层
    page.locator(".results-row").first.locator(".anno-add").click()
    page.wait_for_selector(".annotation-popover", timeout=5000)
    check("点击弹出批注浮层", True)
    check("无内联编辑行", page.locator(".results-edit-row").count() == 0)
    check("无 field-edit-bar", page.locator(".field-edit-bar").count() == 0)
    page.locator(".annotation-popover textarea").fill("v3 浮层批注测试")
    page.locator(".annotation-popover .btn-primary", has_text="保存批注").click()
    page.wait_for_timeout(1000)
    check("浮层保存 → popover 关闭", page.locator(".annotation-popover").count() == 0)
    check("行出现批注黄点", page.locator(".anno-dot").count() >= 1)
    page.screenshot(path=str(SHOT_DIR / "03_popover_saved.png"))

    # 字段级：展开行 → hover 字段 → 旗标 → 浮层
    page.locator(".results-row").first.click()
    page.wait_for_selector(".detail-fields .flag-btn", timeout=5000)
    page.locator(".detail-fields").first.hover()
    page.wait_for_timeout(300)
    page.locator(".detail-fields .flag-btn").first.click()
    page.wait_for_selector(".annotation-popover", timeout=5000)
    page.locator(".annotation-popover textarea").fill("字段级批注")
    page.locator(".annotation-popover .btn-primary", has_text="保存批注").click()
    page.wait_for_timeout(1000)
    check("字段级批注保存", page.locator(".anno-dot").count() >= 1,
          f"dot={page.locator('.anno-dot').count()}, popover={page.locator('.annotation-popover').count()}")

    # tab：批注(n)
    anno_tab = page.locator(".kanban-tab", has_text="批注")
    check("批注 tab 计数", "(2)" in anno_tab.inner_text(), anno_tab.inner_text())
    anno_tab.click()
    page.wait_for_timeout(500)
    check("批注 tab 显示列表（看板隐藏）",
          page.locator(".annotation-item").count() >= 1 and page.locator(".timeline").count() == 0)
    # 点条目 → 自动切回看板 + 闪烁
    page.locator(".annotation-item").first.click()
    page.wait_for_timeout(1000)
    check("点批注条目自动切回看板", page.locator(".timeline").count() > 0)
    check("记录闪烁", page.locator(".results-row.flash").count() >= 1)
    # 删除
    page.locator(".kanban-tab", has_text="批注").click()
    page.wait_for_timeout(300)
    n_before = page.locator(".annotation-item").count()
    page.locator('.annotation-item-actions button[aria-label="删除"]').first.click()
    page.wait_for_timeout(800)
    check("批注删除", page.locator(".annotation-item").count() == n_before - 1)
    # backdrop 关闭测试
    page.locator(".kanban-tab", has_text="看板").click()
    page.locator(".results-row").first.hover()
    page.locator(".results-row").first.locator(".anno-add").click()
    page.wait_for_selector(".annotation-popover", timeout=5000)
    page.locator(".annotation-popover-backdrop").click(position={"x": 5, "y": 5})
    page.wait_for_timeout(400)
    check("backdrop 点击关闭浮层", page.locator(".annotation-popover").count() == 0)

    # ============ 5. 步骤详情定制渲染 ============
    for node_idx, expect in [
        (0, "stat-card"),
        (1, "analysis-badge"),
        (2, "step-summary"),
        (3, "cite-record"),
        (4, "struct-chip"),
    ]:
        page.locator(".timeline-node").nth(node_idx).click()
        page.wait_for_timeout(400)
        found = page.locator(f".step-detail .{expect}").count()
        check(f"步骤 {node_idx + 1} 详情渲染（{expect}）", found >= 1, f"count={found}")
        # 原始 JSON toggle
        page.locator(".step-raw-toggle").click()
        page.wait_for_timeout(300)
        raw = page.locator(".step-detail .step-payload pre").inner_text()
        check(f"步骤 {node_idx + 1} 原始 JSON 可查看", "{" in raw)
        page.locator(".step-raw-toggle").click()
        page.wait_for_timeout(200)
    # parse 详情细查
    page.locator(".timeline-node").first.click()
    page.wait_for_timeout(400)
    n_stats = page.locator(".stat-card").count()
    check("parse 统计卡 ≥5", n_stats >= 5, f"count={n_stats}")
    check("parse markdown 预览", page.locator(".step-markdown").count() >= 1)
    page.screenshot(path=str(SHOT_DIR / "04_parse_detail.png"))
    page.locator(".timeline-node").nth(1).click()
    page.wait_for_timeout(400)
    badge = page.locator(".analysis-badge").inner_text()
    check("route 分类徽标", "软模板" in badge or "复合" in badge or "硬模板" in badge, badge)
    page.screenshot(path=str(SHOT_DIR / "05_route_detail.png"))

    # ============ 6. 回归：历史恢复 + 重跑 ============
    page.reload()
    page.wait_for_load_state("networkidle")
    page.wait_for_selector(".paper-item", timeout=15000)
    page.locator(".paper-item").first.click()
    page.wait_for_timeout(3000)
    check("历史 run 出现", page.locator(".run-history-item").count() >= 1)
    page.locator('.run-history-item button[aria-label="查看"]').first.click()
    page.wait_for_timeout(2500)
    check("历史恢复 5/5", page.locator(".timeline-node.status-done").count() == 5)
    check("历史恢复结果表", page.locator(".results-row").count() >= 1)
    page.screenshot(path=str(SHOT_DIR / "06_history.png"))

    check("无页面 JS 错误", len(errors) == 0, "; ".join(errors[:3]))
    browser.close()

print("\n" + "=" * 50)
failed = [r for r in results if not r[1]]
print(f"结果: {len(results) - len(failed)}/{len(results)} 通过")
sys.exit(1 if failed else 0)
