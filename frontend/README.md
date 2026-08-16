# MKE Web 前端

MKE(介孔材料文献知识自动抽取系统)的 Web 界面:React 18 + Vite + TypeScript。

- 左面板:PDF 论文浏览器(pdf.js 渲染,上传/缩放/翻页/文本选中)
- 右面板:解析流程看板(① PDF 解析 → ② 路由 → ③ 主抽取 → ④ 字段引用 → ⑤ 数值结构化)与批注交互
- 主题:黑白灰,仅状态信号用红黄绿(`theme.css` 中的 `--signal-*` 变量)

## 开发

```bash
npm install
npm run dev        # http://localhost:5173, /api 代理到 :8000
```

## 构建

```bash
npm run build      # 产物在 dist/,由 backend/main.py 静态托管(单端口访问)
```
