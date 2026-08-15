"""后端冒烟测试：启动 uvicorn 后运行 uv run python backend/smoke_test.py"""
import json
import urllib.request

BASE = "http://localhost:8000/api"


def call(method: str, path: str, body=None, data=None, headers=None):
    url = BASE + path
    req = urllib.request.Request(url, method=method, headers=headers or {})
    payload = None
    if body is not None:
        payload = json.dumps(body, ensure_ascii=False).encode()
        req.add_header("Content-Type", "application/json")
    elif data is not None:
        payload = data
    with urllib.request.urlopen(req, data=payload, timeout=120) as resp:
        raw = resp.read()
        if resp.status == 204:
            return None
        return json.loads(raw)


def main():
    print("1. health:", call("GET", "/health"))
    papers = call("GET", "/papers")
    print(f"2. papers: {len(papers)} 篇; 第一篇:", papers[0]["title"][:40])
    pid = papers[0]["id"]
    import urllib.parse
    qpid = urllib.parse.quote(pid)
    text = call("GET", f"/papers/{qpid}/text")["text"]
    print(f"3. text: {len(text)} 字符, 开头:", text[:80].replace(chr(10), " "))

    # 4. corpus 论文 parse → skipped
    pr = call("POST", "/pipeline/parse", {"paper_id": pid})
    print("4. parse(corpus): skipped =", pr["data"].get("skipped"))

    # 5. 上传 PDF → 自动解析
    with open("/tmp/mke_test/sample_twocol.pdf", "rb") as f:
        pdf_data = f.read()
    boundary = "----mketestboundary"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="sample_twocol.pdf"\r\n'
        f"Content-Type: application/pdf\r\n\r\n"
    ).encode() + pdf_data + f"\r\n--{boundary}--\r\n".encode()
    up = call("POST", "/papers/upload", data=body,
              headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    print("5. upload:", {k: up[k] for k in ("paper_id", "has_pdf", "text_size")},
          "| parse_meta:", up.get("parse_meta"))
    print("   upload text 前 100 字符:", up["text"][:100].replace(chr(10), " "))

    # 6. 上传论文 parse → 版面中间产物
    pr2 = call("POST", "/pipeline/parse", {"paper_id": up["paper_id"]})
    print("6. parse(upload): columns =", pr2["data"]["column_stats"],
          "| filtered =", pr2["data"]["header_footer_filtered_count"])

    # 7. 批注 CRUD 往返
    ann = call("POST", f"/papers/{urllib.parse.quote(up['paper_id'])}/annotations",
               {"page": 1, "quote": "sample quote", "note": "测试批注",
                "anchor": {"rects": [{"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.02}]}})
    print("7. annotation created:", ann["id"][:8], "| note:", ann["note"])
    listed = call("GET", f"/papers/{urllib.parse.quote(up['paper_id'])}/annotations")
    print("   list:", len(listed), "条")
    call("DELETE", f"/annotations/{ann['id']}")
    listed2 = call("GET", f"/papers/{urllib.parse.quote(up['paper_id'])}/annotations")
    print("   delete 后:", len(listed2), "条")

    # 8. route（真实 LLM 调用，短文本）
    route = call("POST", "/pipeline/route", {"text": text[:1500]})
    print("8. route:", route["data"]["analysis_type"], "| took_ms:", route["took_ms"])
    print("   skills:", route["data"]["selected_skills"])

    print("\n✅ 冒烟测试全部通过")


if __name__ == "__main__":
    main()
