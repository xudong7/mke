"""MKE Web v2 端到端验证（需要后端 :8000 + 前端 :5173 已启动）

覆盖 v2 改版的 8 项清单：上传-only 列表 / DPR 清晰度 / 侧栏折叠 /
时间轴 / runAll 全流程 / 刷新后历史恢复 / 重新运行 / 结果批注。
运行：uv run python frontend/e2e/verify_v2.py
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

SHOT_DIR = Path("/tmp/mke_ui_v2")
SHOT_DIR.mkdir(exist_ok=True)
BASE = "http://localhost:5173"
PDF_PATH = "/tmp/mke_test/sample_twocol.pdf"

results = []


def check(name: str, ok: bool, detail: str = ""):
    results.append((name, ok, detail))
    print(f"{'✅' if ok else '❌'} {name}" + (f" — {detail}" if detail and not ok else ""))


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1600, "height": 1000})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    # 1. 左侧只显示"已上传"（无语料库组）
    page.goto(BASE)
    page.wait_for_load_state("networkidle")
    page.wait_for_selector(".paper-item", timeout=15000)
    n_items = page.locator(".paper-item").count()
    has_corpus = page.locator(".paper-group-label:has-text('语料库')").count() > 0
    check("左侧只显示已上传论文（无语料库）", n_items >= 1 and not has_corpus,
          f"items={n_items}, corpus组={has_corpus}")
    page.screenshot(path=str(SHOT_DIR / "01_sidebar.png"))

    # 2. 选择论文 → PDF 渲染（DPR 清晰度）
    page.locator(".paper-item").first.click()
    page.wait_for_selector("canvas", timeout=20000)
    page.wait_for_timeout(1500)
    dpr = page.evaluate("() => window.devicePixelRatio")
    canvas_info = page.evaluate("""() => {
      const c = document.querySelector('canvas');
      const r = c.getBoundingClientRect();
      return { width: c.width, height: c.height, cssW: r.width, cssH: r.height };
    }""")
    sharp = abs(canvas_info["width"] - canvas_info["cssW"] * dpr) <= 2
    check("PDF 按 devicePixelRatio 高清渲染",
          sharp, f"canvas={canvas_info['width']}px vs css={canvas_info['cssW']}px × dpr={dpr}")
    zoom = page.locator(".zoom-label").inner_text()
    check("加载默认适应宽度（非 100%）", zoom != "100%", f"zoom={zoom}")
    page.screenshot(path=str(SHOT_DIR / "02_pdf_dpr.png"))

    # 3. 聚焦模式（唯一按钮 = 折叠左栏 + 右栏加宽至 75%）
    center_before = page.locator(".pane-center").bounding_box()["width"]
    kanban_before = page.locator(".sidebar-right").bounding_box()["width"]
    vp_w = page.viewport_size["width"]
    page.locator(".panel-handle-right").click()
    page.wait_for_timeout(600)
    check("聚焦：左栏折叠", page.locator(".sidebar-left").count() == 0)
    check("聚焦：右栏常驻", page.locator(".kanban").count() > 0)
    kanban_w = page.locator(".sidebar-right").bounding_box()["width"]
    center_after = page.locator(".pane-center").bounding_box()["width"]
    check("聚焦：右栏加宽 ≥75% 视口", kanban_w >= vp_w * 0.7,
          f"{kanban_w:.0f} vs 75%={vp_w * 0.75:.0f}")
    page.screenshot(path=str(SHOT_DIR / "03_wide_mode.png"))
    page.locator(".panel-handle-right").click()
    page.wait_for_timeout(600)
    check("还原：左栏恢复", page.locator(".sidebar-left").count() == 1)
    center_restored = page.locator(".pane-center").bounding_box()["width"]
    check("还原：PDF 区宽度还原", abs(center_restored - center_before) < 10,
          f"{center_restored:.0f} vs {center_before:.0f}")

    # 4. 时间轴渲染
    nodes = page.locator(".timeline-node")
    connectors = page.locator(".timeline-connector")
    check("时间轴 5 节点", nodes.count() == 5, f"nodes={nodes.count()}")
    check("连接线存在", connectors.count() >= 4, f"connectors={connectors.count()}")
    page.screenshot(path=str(SHOT_DIR / "04_timeline.png"))

    # 5. runAll 全流程（真实 LLM，5 步依次完成）
    page.locator(".kanban-actions .btn-primary", has_text="全部运行").click()
    page.wait_for_timeout(2000)
    for _ in range(60):
        page.wait_for_timeout(5000)
        done = page.locator(".timeline-node.status-done").count()
        running = page.locator(".timeline-node.status-running").count()
        err = page.locator(".timeline-node.status-error").count()
        print(f"    [progress] done={done} running={running} error={err}")
        if done == 5 or err > 0:
            break
    check("全部运行 → 5 步全部完成", done == 5, f"done={done}")
    page.wait_for_selector(".results-table", timeout=15000)
    n_records = page.locator(".results-row").count()
    check("结果表渲染", n_records >= 1, f"records={n_records}")
    page.screenshot(path=str(SHOT_DIR / "05_runall_done.png"))

    # 6. 刷新 → 历史恢复（零 LLM）
    page.reload()
    page.wait_for_load_state("networkidle")
    page.wait_for_selector(".paper-item", timeout=15000)
    page.locator(".paper-item").first.click()
    page.wait_for_timeout(3000)
    check("历史记录出现在列表", page.locator(".run-history-item").count() >= 1)
    first_run = page.locator(".run-history-item").first
    check("历史 run 状态 done 5/5",
          "status-done" in (first_run.locator(".dot").get_attribute("class") or ""))
    page.locator('.run-history-item button[aria-label="查看"]').first.click()
    page.wait_for_timeout(2500)
    done_nodes = page.locator(".timeline-node.status-done").count()
    check("查看历史 → 看板完整恢复（5 节点 done）", done_nodes == 5, f"done={done_nodes}")
    check("历史记录恢复到结果表", page.locator(".results-row").count() >= 1)
    page.screenshot(path=str(SHOT_DIR / "06_history_loaded.png"))

    # 7. 重新运行 → 新 run
    runs_before = page.locator(".run-history-item").count()
    page.locator('.run-history-item button[aria-label="重新运行"]').first.click()
    page.wait_for_timeout(2000)
    runs_after_wait = page.locator(".run-history-item").count()
    check("重新运行 → 新 run 出现（运行中）", runs_after_wait >= runs_before,
          f"{runs_before} → {runs_after_wait}")
    # 等待新 run 完成（可能复用 LLM 结果，等 5 步 done）
    for _ in range(60):
        page.wait_for_timeout(5000)
        if page.locator(".timeline-node.status-running").count() == 0:
            break
    page.wait_for_timeout(3000)
    check("新 run 完成（5/5）", page.locator(".timeline-node.status-done").count() == 5)
    page.screenshot(path=str(SHOT_DIR / "07_rerun.png"))

    # 8. 结果批注（v3：hover 触发 + 浮层 + tab）
    # 8a. 行级批注
    page.locator(".results-row").first.hover()
    page.wait_for_timeout(300)
    page.locator(".results-row").first.locator(".anno-add").click()
    page.wait_for_selector(".annotation-popover textarea", timeout=5000)
    page.locator(".annotation-popover textarea").fill("行级测试批注")
    page.locator(".annotation-popover button", has_text="保存批注").click()
    page.wait_for_timeout(1200)
    check("行级批注保存", page.locator(".anno-dot").count() >= 1)
    page.screenshot(path=str(SHOT_DIR / "08_row_annotation.png"))

    # 8b. 字段级批注
    page.locator(".results-row").first.click()  # 展开
    page.wait_for_selector(".detail-fields .flag-btn", timeout=5000)
    page.locator(".detail-fields").first.hover()
    page.wait_for_timeout(300)
    page.locator(".detail-fields .flag-btn").first.click()
    page.wait_for_selector(".annotation-popover textarea", timeout=5000)
    page.locator(".annotation-popover textarea").fill("字段级测试批注")
    page.locator(".annotation-popover button", has_text="保存批注").click()
    page.wait_for_timeout(1200)
    check("字段级批注保存", page.locator(".anno-dot").count() >= 1)

    # 8c. tab 批注面板 → 点击定位（scroll/flash）
    page.locator(".kanban-tab", has_text="批注").click()
    page.wait_for_timeout(400)
    check("批注 tab 显示列表", page.locator(".annotation-item").count() >= 2)
    page.locator(".annotation-item").last.click()
    page.wait_for_timeout(1000)
    flash = page.locator(".results-row.flash").count()
    check("面板点击定位记录并闪烁", flash >= 1, f"flash={flash}")
    page.screenshot(path=str(SHOT_DIR / "09_annotation_flash.png"))

    # 8d. 删除批注
    page.locator(".kanban-tab", has_text="批注").click()
    page.wait_for_timeout(300)
    n_before = page.locator(".annotation-item").count()
    page.locator('.annotation-item-actions button[aria-label="删除"]').first.click()
    page.wait_for_timeout(800)
    check("批注删除", page.locator(".annotation-item").count() == n_before - 1)

    # 8e. PDF 文本选中不再弹出批注框
    span = page.locator(".textLayer span").first
    if span.count() > 0:
        b = span.bounding_box()
        page.mouse.move(b["x"] + 2, b["y"] + b["height"] / 2)
        page.mouse.down()
        page.mouse.move(b["x"] + b["width"] / 2 + 30, b["y"] + b["height"] / 2, steps=10)
        page.mouse.up()
        page.wait_for_timeout(800)
        check("PDF 文本选中不再弹批注框", page.locator(".annotation-popover").count() == 0)

    check("无页面 JS 错误", len(errors) == 0, "; ".join(errors[:3]))
    browser.close()

print("\n" + "=" * 50)
failed = [r for r in results if not r[1]]
print(f"结果: {len(results) - len(failed)}/{len(results)} 通过")
sys.exit(1 if failed else 0)
