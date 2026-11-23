import io
import cv2
import numpy as np
import streamlit as st
from PIL import Image, ImageOps

st.set_page_config(page_title="v2: SLIC + Saliency + GrabCut", page_icon="🚀")
st.title("🚀 v2: SLIC + Saliency + GrabCut")

uploaded = st.file_uploader("Загрузите фото", type=["jpg", "jpeg", "png", "webp"])
if not uploaded:
    st.info("Выберите файл.")
    st.stop()

try:
    pil_img = Image.open(uploaded)
    pil_img = ImageOps.exif_transpose(pil_img).convert("RGB")
except Exception as e:
    st.error(f"Не удалось открыть: {e}")
    st.stop()

# уменьшаем для скорости обработки (макс 1000px по длинной стороне)
MAX_SIDE = 1000
if max(pil_img.size) > MAX_SIDE:
    ratio = MAX_SIDE / max(pil_img.size)
    new_size = (int(pil_img.width * ratio), int(pil_img.height * ratio))
    work_img = pil_img.resize(new_size, Image.LANCZOS)
else:
    work_img = pil_img.copy()

st.image(pil_img, caption="Оригинал", width="stretch")

# ---------- настройки ----------
st.subheader("Настройки")

method = st.radio(
    "Метод:",
    ["SLIC + K-means + GrabCut (рекомендую)", "SLIC + Saliency + GrabCut", "Только GrabCut"],
    horizontal=False,
)

n_segments = st.slider("SLIC: число суперпикселей", 100, 2000, 500, 50,
    help="Больше — точнее границы, но медленнее.")

k_color = st.slider("K-means: кластеров по цвету", 2, 8, 3, 1)

use_texture = st.checkbox("Учитывать текстуру (LBP)", value=True,
    help="Помогает, когда объект и фон похожи по цвету, но различаются по текстуре.")

use_saliency = st.checkbox("Использовать Saliency как подсказку", value=True,
    help="Выделяет визуально значимую область — обычно это объект.")

grabcut_iters = st.slider("GrabCut: итераций", 1, 10, 5, 1)

feather = st.slider("Сглаживание краёв (px)", 0, 8, 2, 1)

# ---------- пайплайн ----------
def run_pipeline(pil_image, method, n_seg, k, tex, sal, gc_iters, feather_px):
    rgb = np.array(pil_image.convert("RGB"))
    h, w, _ = rgb.shape
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

    # ============ 1. SLIC superpixels ============
    slic = cv2.ximgproc.createSuperpixelSLIC(
        bgr, algorithm=cv2.ximgproc.SLICO, region_size=max(10, w * h // n_seg // 100)
    )
    slic.iterate(10)
    slic.enforceLabelConnectivity(min_label_size=max(10, w * h // (n_seg * 4)))
    labels = slic.getLabels()  # (h, w) int32, каждый пиксель = id суперпикселя
    n_labels = slic.getNumberOfSuperpixels()

    # ============ 2. Признаки суперпикселей ============
    # цвет (средний RGB) + текстура (LBP) + позиция
    lab_img = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)

    # LBP текстура
    if tex:
        lbp = np.zeros_like(gray)
        # простая LBP-реализация через сравнение с соседями
        g = gray.astype(np.int16)
        offsets = [(-1,-1),(-1,0),(-1,1),(0,1),(1,1),(1,0),(1,-1),(0,-1)]
        for i, (dy, dx) in enumerate(offsets):
            shifted = np.roll(np.roll(g, dy, axis=0), dx, axis=1)
            lbp += ((shifted >= g).astype(np.uint8) << i)
        lbp = lbp.astype(np.float32)

    # усредняем признаки по суперпикселям
    feats = np.zeros((n_labels, 8), np.float32)
    for i in range(n_labels):
        m = labels == i
        cnt = m.sum()
        if cnt == 0:
            continue
        feats[i, 0:3] = lab_img[m].mean(axis=0)               # LAB цвет
        feats[i, 3] = lbp[m].mean() if tex else 0              # текстура
        feats[i, 4] = lbp[m].std() if tex else 0               # разброс текстуры
        ys, xs = np.where(m)
        feats[i, 5] = xs.mean() / w                            # x центра (норм)
        feats[i, 6] = ys.mean() / h                            # y центра (норм)
        feats[i, 7] = cnt / (w * h)                            # доля площади

    # нормализация
    feats_norm = (feats - feats.mean(axis=0)) / (feats.std(axis=0) + 1e-6)

    # ============ 3. K-means по признакам суперпикселей ============
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 1.0)
    _, sp_labels, centers = cv2.kmeans(
        feats_norm.astype(np.float32), k, None, criteria, 10, cv2.KMEANS_PP_CENTERS
    )
    sp_labels = sp_labels.flatten()

    # ============ 4. Определяем фон по углам ============
    e = max(5, min(30, h // 10, w // 10))
    corner_pixels = np.concatenate([
        labels[:e, :e].ravel(),
        labels[:e, -e:].ravel(),
        labels[-e:, :e].ravel(),
        labels[-e:, -e:].ravel(),
    ])
    # какие K-кластеры доминируют в углах
    corner_k = sp_labels[corner_pixels]
    uniq, counts = np.unique(corner_k, return_counts=True)
    bg_k_labels = set(uniq[counts >= len(corner_k) * 0.3])

    # ============ 5. Saliency как подсказка ============
    sal_map = None
    if sal:
        sal_algo = cv2.saliency.StaticSaliencySpectralResidual_create()
        ok, sal_map = sal_algo.computeSaliency(bgr)
        if ok:
            sal_map = (sal_map * 255).astype(np.uint8)
            sal_map = cv2.GaussianBlur(sal_map, (31, 31), 0)
            sal_map = cv2.normalize(sal_map, None, 0, 255, cv2.NORM_MINMAX)

    # ============ 6. Собираем начальную маску ============
    fg_mask = np.zeros((h, w), np.uint8)
    for sp_id in range(n_labels):
        k_lab = sp_labels[sp_id]
        is_bg = k_lab in bg_k_labels
        # если saliency говорит, что здесь объект — не считаем фоном
        if is_bg and sal_map is not None:
            m = labels == sp_id
            if m.sum() > 0 and sal_map[m].mean() > 120:
                is_bg = False
        if not is_bg:
            fg_mask[labels == sp_id] = 255

    # морфология адаптивным ядром
    ks = max(3, int(min(h, w) * 0.01) | 1)
    kernel = np.ones((ks, ks), np.uint8)
    fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, kernel, iterations=2)
    fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, kernel, iterations=2)

    # ============ 7. GrabCut с инициализацией маской ============
    if method != "Только GrabCut":
        gc_mask = np.full((h, w), cv2.GC_BGD, np.uint8)
        gc_mask[fg_mask == 255] = cv2.GC_PR_FGD  # возможно объект
        # уверенно объект — центр найденной маски
        cnts, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL,
                                    cv2.CHAIN_APPROX_SIMPLE)
        if cnts:
            biggest = max(cnts, key=cv2.contourArea)
            inner = np.zeros_like(fg_mask)
            cv2.drawContours(inner, [biggest], -1, 255, -1)
            inner = cv2.erode(inner, kernel, iterations=2)
            gc_mask[inner == 255] = cv2.GC_FGD
        bgd_model = np.zeros((1, 65), np.float64)
        fgd_model = np.zeros((1, 65), np.float64)
        try:
            cv2.grabCut(bgr, gc_mask, None, bgd_model, fgd_model,
                        gc_iters, cv2.GC_INIT_WITH_MASK)
        except Exception as ex:
            st.warning(f"GrabCut: {ex}")
        fg_mask = np.where(
            (gc_mask == cv2.GC_FGD) | (gc_mask == cv2.GC_PR_FGD), 255, 0
        ).astype(np.uint8)
    else:
        # только GrabCut — с рамкой по центру
        m = int(min(h, w) * 0.1)
        rect = (m, m, w - 2 * m, h - 2 * m)
        gc_mask = np.zeros((h, w), np.uint8)
        bgd_model = np.zeros((1, 65), np.float64)
        fgd_model = np.zeros((1, 65), np.float64)
        try:
            cv2.grabCut(bgr, gc_mask, rect, bgd_model, fgd_model,
                        gc_iters, cv2.GC_INIT_WITH_RECT)
            fg_mask = np.where(
                (gc_mask == cv2.GC_FGD) | (gc_mask == cv2.GC_PR_FGD), 255, 0
            ).astype(np.uint8)
        except Exception as ex:
            st.warning(f"GrabCut: {ex}")

    # ============ 8. Оставить только объект в центре ============
    cnts, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL,
                                cv2.CHAIN_APPROX_SIMPLE)
    if cnts:
        cx, cy = w // 2, h // 2
        best = None
        best_score = -1
        for c in cnts:
            area = cv2.contourArea(c)
            if area < h * w * 0.01:  # мусор
                continue
            M = cv2.moments(c)
            if M["m00"] == 0:
                continue
            ox, oy = M["m10"] / M["m00"], M["m01"] / M["m00"]
            dist = np.hypot(ox - cx, oy - cy)
            score = area / (1 + dist)
            if score > best_score:
                best_score = score
                best = c
        if best is not None:
            mask_center = np.zeros_like(fg_mask)
            cv2.drawContours(mask_center, [best], -1, 255, -1)
            fg_mask = mask_center

    # ============ 9. Guided filter для мягких краёв ============
    if feather_px > 0:
        try:
            guided = cv2.ximgproc.guidedFilter(
                guide=bgr, src=fg_mask, radius=feather_px * 4,
                eps=1e-3
            )
            alpha_arr = np.clip(guided, 0, 255).astype(np.uint8)
        except Exception:
            alpha_arr = cv2.GaussianBlur(fg_mask, (0, 0), feather_px)
    else:
        alpha_arr = fg_mask

    rgba = pil_image.convert("RGBA").copy()
    rgba.putalpha(Image.fromarray(alpha_arr, mode="L"))
    return rgba, fg_mask, alpha_arr

# ---------- запуск ----------
if st.button("🚀 Вырезать", type="primary"):
    with st.spinner("Пайплайн работает..."):
        try:
            result_work, mask, alpha = run_pipeline(
                work_img, method, n_segments, k_color,
                use_texture, use_saliency, grabcut_iters, feather
            )
        except Exception as e:
            st.error(f"Ошибка пайплайна: {e}")
            st.exception(e)
            st.stop()

    # возвращаем к оригинальному размеру
    if result_work.size != pil_img.size:
        result = result_work.resize(pil_img.size, Image.LANCZOS)
    else:
        result = result_work

    col1, col2 = st.columns(2)
    with col1:
        st.image(pil_img, caption="Оригинал", width="stretch")
    with col2:
        st.image(result, caption="Результат", width="stretch")

    with st.expander("Маски"):
        st.image(mask, caption="Итоговая маска", width="stretch")
        st.image(alpha, caption="Альфа-канал (сглаженный)", width="stretch")

    buf = io.BytesIO()
    result.save(buf, format="PNG")
    st.download_button("⬇️ Скачать PNG", data=buf.getvalue(),
                       file_name="cut.png", mime="image/png")