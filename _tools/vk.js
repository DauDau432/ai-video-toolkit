// Thư viện nhỏ được videokit.py tự chèn vào trang trước khi render (không cần <script src>).
// Dùng trong window.renderAtTime(t). Mọi hàm đều chỉ phụ thuộc t, không dùng timer hay ngẫu nhiên.
(function () {
  const POINTER = ["cursor_move", "hover", "click", "double_click", "right_click", "drag"];
  const KEYS = ["key", "shortcut"];
  const clamp = (x) => Math.max(0, Math.min(1, x));
  const ease = (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
  const easeOutBack = (x) => { const c = 0.9; return 1 + (c + 1) * Math.pow(x - 1, 3) + c * Math.pow(x - 1, 2); };
  const hash = (s) => { let h = 2166136261; for (const c of s) h = Math.imul(h ^ c.charCodeAt(0), 16777619); return (h >>> 0) / 4294967295; };

  function a(id) {
    const x = window.TIMELINE.actions[id];
    if (!x) throw new Error("Không có action '" + id + "' trong timeline");
    return x;
  }

  // Tiến độ 0..1 của một action (đã làm mượt). dur mặc định = duration của action.
  function p(t, id, dur) {
    const x = a(id);
    const d = dur ?? (x.duration || 0.35);
    return ease(clamp((t - x.start) / d));
  }

  const on = (t, id) => t >= a(id).start;

  // Chữ đang gõ dở tại thời điểm t, nhịp gõ không đều như người thật. Văn bản lấy từ action.text.
  function typed(t, id, text) {
    const x = a(id);
    text = text ?? x.text ?? "";
    const dur = x.duration || text.length * 0.06;
    let acc = 0;
    const w = [...text].map((c, i) => (acc += 0.6 + 0.8 * hash(id + i) + (c === " " ? 0.6 : 0)));
    const el = (t - x.start) / dur * acc;
    return text.slice(0, w.filter((v) => v <= el).length);
  }

  const caret = (t) => Math.floor(t * 2) % 2 === 0;

  function scene(t) {
    const s = window.TIMELINE.scenes;
    return s.find((x) => t >= x.start && t < x.end) || s[s.length - 1];
  }

  function center(sel) {
    const el = document.querySelector(sel);
    if (!el) throw new Error("Không thấy phần tử '" + sel + "' (target của action)");
    const r = el.getBoundingClientRect();
    return [r.left + r.width / 2, r.top + r.height / 2];
  }

  // ---- Lớp chuột + phím (Template mục 5.1), vẽ tự động sau renderAtTime
  let layer;
  function ensureLayer() {
    if (layer) return layer;
    layer = document.createElement("div");
    layer.style.cssText = "position:fixed;inset:0;pointer-events:none;z-index:2147483647";
    layer.innerHTML =
      '<div id="vk-ripple" style="position:absolute;border-radius:50%;border:3px solid rgba(255,255,255,.9);display:none"></div>' +
      '<svg id="vk-cursor" width="34" height="46" viewBox="0 0 17 23" style="position:absolute;transform-origin:0 0;filter:drop-shadow(0 3px 4px rgba(0,0,0,.5))">' +
      '<path d="M1 1 L1 18 L5.5 13.8 L8.6 21 L11.6 19.7 L8.6 12.8 L14.5 12.8 Z" fill="#fff" stroke="#111" stroke-width="1.2" stroke-linejoin="round"/></svg>' +
      '<div id="vk-keys" style="position:absolute;left:50%;bottom:70px;transform:translateX(-50%);display:none;gap:12px"></div>';
    document.body.appendChild(layer);
    return layer;
  }

  // Vị trí chuột: mỗi action chuột có thời điểm "tới nơi" (click/hover: lúc start; cursor_move/drag: lúc end).
  // Chuột rời điểm trước ngay sau thời điểm tới nơi trước đó, di chuyển theo đường cong, hơi vượt rồi dừng.
  function pointerState(t, sc) {
    const acts = Object.values(window.TIMELINE.actions)
      .filter((x) => POINTER.includes(x.type) && x.target && x.start >= sc.start && x.start < sc.end)
      .sort((x, y) => x.start - y.start);
    if (!acts.length || sc.pointer === false) return null;
    let pos = sc.cursor_start || [window.innerWidth * 0.62, window.innerHeight * 0.78];
    let free = sc.start;
    let st = { x: pos[0], y: pos[1], down: false, click: null };
    for (const x of acts) {
      const arrive = x.type === "cursor_move" ? x.start + (x.duration || 0.6) : x.start;
      const move = x.move ?? (x.type === "cursor_move" ? x.duration || 0.6 : 0.6);
      const t0 = Math.max(free, arrive - move);
      const tgt = center(x.target);
      if (t < t0) break;
      const k = clamp((t - t0) / Math.max(0.05, arrive - t0));
      const e = easeOutBack(ease(k) * 0.98 + k * 0.02);
      const dx = tgt[0] - pos[0], dy = tgt[1] - pos[1];
      const bend = (hash(x.id) - 0.5) * 0.35;
      const s = Math.sin(Math.PI * clamp(e));
      st = { x: pos[0] + dx * e - dy * bend * s, y: pos[1] + dy * e + dx * bend * s, down: false, click: null };
      if (["click", "double_click", "right_click"].includes(x.type) && t >= x.start) {
        st.down = t - x.start < 0.12 || (x.type === "double_click" && t - x.start > 0.2 && t - x.start < 0.32);
        if (t - x.start < 0.5) st.click = { x: tgt[0], y: tgt[1], k: (t - x.start) / 0.5 };
      }
      if (x.type === "drag" && x.to && t >= x.start) {
        const to = center(x.to);
        const kd = ease(clamp((t - x.start) / (x.duration || 0.8)));
        st = { x: tgt[0] + (to[0] - tgt[0]) * kd, y: tgt[1] + (to[1] - tgt[1]) * kd, down: kd < 1, click: null };
        pos = to;
      } else {
        pos = tgt;
      }
      free = x.type === "drag" ? x.start + (x.duration || 0.8) : arrive + (x.type === "click" ? 0.15 : 0);
    }
    return st;
  }

  function drawPointer(t) {
    ensureLayer();
    const sc = scene(t);
    const st = pointerState(t, sc);
    const cur = layer.querySelector("#vk-cursor");
    const rip = layer.querySelector("#vk-ripple");
    cur.style.display = st ? "block" : "none";
    rip.style.display = "none";
    if (st) {
      cur.style.left = st.x - 2 + "px";
      cur.style.top = st.y - 2 + "px";
      cur.style.transform = st.down ? "scale(.85)" : "none";
      if (st.click) {
        const r = 8 + 42 * ease(st.click.k);
        Object.assign(rip.style, { display: "block", left: st.click.x - r + "px", top: st.click.y - r + "px",
          width: 2 * r + "px", height: 2 * r + "px", opacity: String(1 - st.click.k) });
      }
    }
    // Phím tắt / phím bấm hiện dạng keycap 1,5 giây
    const keys = layer.querySelector("#vk-keys");
    const k = Object.values(window.TIMELINE.actions).filter((x) => KEYS.includes(x.type) && t >= x.start && t < x.start + 1.5)
      .sort((a, b) => b.start - a.start)[0];
    keys.style.display = k ? "flex" : "none";
    if (k) {
      const kp = clamp((t - k.start) / 0.12);
      keys.style.opacity = String(Math.min(kp, clamp((k.start + 1.5 - t) / 0.2)));
      keys.innerHTML = String(k.keys || k.key || "Enter").split("+").map((s) =>
        '<span style="font:600 34px/1 Segoe UI,Arial,sans-serif;color:#fff;background:#2b2f3a;border:2px solid #6b7280;' +
        "border-bottom-width:6px;border-radius:12px;padding:14px 22px;transform:translateY(" + (t - k.start < 0.1 ? 4 : 0) + 'px)">' +
        s.trim() + "</span>").join("");
    }
  }

  window.VK = { a, p, on, typed, caret, scene, ease, clamp, drawPointer };
})();
