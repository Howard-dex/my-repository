import streamlit as st
import requests

# 连接你本地正在跑的 api_server.py
API_BASE = "http://127.0.0.1:8000"

st.set_page_config(page_title="智能派单调度控制台 (数据库联通版)", page_icon="⚡", layout="wide")

ALL_SKILLS = ["水电", "网络", "硬件维修", "VIP专属", "高空作业", "软件调试"]
PRIORITY_MAP = {1: "🟢 普通", 2: "🟡 紧急", 3: "🔴 特急"}
STRATEGY_MAP = {
    "最少单量优先 (Least Loaded)": "least_loaded",
    "最低负载率优先 (Load Ratio)": "load_ratio",
    "均衡轮询 (Round Robin)": "round_robin"
}

# 检查后端是否启动
try:
    workers_resp = requests.get(f"{API_BASE}/workers", timeout=2)
    orders_resp = requests.get(f"{API_BASE}/orders", timeout=2)
    workers = workers_resp.json()
    orders = orders_resp.json()
except Exception:
    st.error("⚠️ 无法连接到后端数据库服务！请先在另一个终端运行：`uvicorn api_server:app --reload --port 8000`")
    st.stop()

worker_dict = {w["id"]: w for w in workers}

# ==========================================
# 侧边栏：策略选择 & 接单员状态管理 (实时读写 SQLite)
# ==========================================
with st.sidebar:
    st.title("⚙️ 调度引擎设置")
    selected_strategy_label = st.selectbox("当前自动派单策略", options=list(STRATEGY_MAP.keys()))
    current_strategy = STRATEGY_MAP[selected_strategy_label]

    st.divider()
    st.subheader("👷 接单员实时状态 (数据库同步)")

    for w in workers:
        with st.container(border=True):
            col1, col2 = st.columns([3, 2])
            with col1:
                dot = "🟢" if w["is_online"] else "⚪"
                st.markdown(f"**{dot} {w['name']}** (`{w['id']}`)")
            with col2:
                new_online = st.toggle("在线", value=w["is_online"], key=f"online_{w['id']}")
                if new_online != w["is_online"]:
                    requests.patch(f"{API_BASE}/workers/{w['id']}", json={"is_online": new_online})
                    st.rerun()

            st.caption(f"技能：{', '.join(w['skills']) if w['skills'] else '无特定技能'}")
            ratio = min(w["load_ratio"], 1.0)
            st.progress(ratio, text=f"当前负载: {w['current_load']} / {w['max_load']} 单")

    with st.expander("➕ 新增接单员"):
        with st.form("add_worker_form", clear_on_submit=True):
            new_w_name = st.text_input("姓名", placeholder="例如：陈工")
            new_w_skills = st.multiselect("具备技能", ALL_SKILLS)
            new_w_max = st.slider("最大同时接单数", 1, 10, 3)
            if st.form_submit_button("添加至数据库", use_container_width=True):
                if new_w_name.strip():
                    requests.post(f"{API_BASE}/workers", json={
                        "name": new_w_name.strip(),
                        "skills": new_w_skills,
                        "max_load": new_w_max,
                        "is_online": True
                    })
                    st.rerun()

# ==========================================
# 主界面：KPI 与工单操作
# ==========================================
st.title("⚡ 智能工单派发控制台 (FastAPI + SQLite 持久版)")

pending_orders = [o for o in orders if o["status"] in ("PENDING", "FAILED")]
assigned_orders = [o for o in orders if o["status"] == "ASSIGNED"]
completed_orders = [o for o in orders if o["status"] == "COMPLETED"]

k1, k2, k3, k4 = st.columns(4)
k1.metric("⏳ 待派单 / 滞留", f"{len(pending_orders)} 单")
k2.metric("🚀 处理中工单", f"{len(assigned_orders)} 单")
k3.metric("✅ 历史已办结", f"{len(completed_orders)} 单")
k4.metric("👷 在线接单员", f"{sum(1 for w in workers if w['is_online'])} / {len(workers)} 人")

with st.expander("📝 录入新工单", expanded=True):
    with st.form("create_order_form", clear_on_submit=True):
        c1, c2, c3 = st.columns([3, 2, 1])
        o_title = c1.text_input("工单标题 / 故障描述")
        o_skills = c2.multiselect("所需技能标签", ALL_SKILLS)
        o_priority = c3.selectbox("优先级", options=[1, 2, 3], format_func=lambda x: PRIORITY_MAP[x])

        bc1, bc2 = st.columns([2, 1])
        auto_flag = bc1.checkbox("提交后立即自动派单", value=True)
        if bc2.form_submit_button("➕ 提交工单", type="primary", use_container_width=True):
            if o_title.strip():
                requests.post(f"{API_BASE}/orders", json={
                    "title": o_title.strip(),
                    "required_skills": o_skills,
                    "priority": o_priority,
                    "auto_dispatch": auto_flag,
                    "strategy": current_strategy
                })
                st.rerun()

tab1, tab2, tab3 = st.tabs([
    f"🎯 待派单调度池 ({len(pending_orders)})",
    f"🚀 处理中工单 ({len(assigned_orders)})",
    f"✅ 已办结归档 ({len(completed_orders)})"
])

with tab1:
    if not pending_orders:
        st.success("🎉 当前没有积压的待派工单！")
    for o in pending_orders:
        with st.container(border=True):
            c1, c2, c3 = st.columns([3, 3, 2])
            c1.markdown(f"#### `{o['id']}` {o['title']}")
            c1.caption(f"状态: {o['status']} | 优先级: {PRIORITY_MAP.get(o['priority'], o['priority'])} | 需技能: **{', '.join(o['required_skills']) or '无'}**")

            worker_options = {
                w["id"]: f"{w['name']} [负载:{w['current_load']}/{w['max_load']}] ({'🟢在线' if w['is_online'] else '⚪离线'})"
                for w in workers
            }
            sel_w = c2.selectbox("手动选择接单员", options=list(worker_options.keys()), format_func=lambda x: worker_options[x], key=f"sel_{o['id']}")
            force_flag = c2.checkbox("忽略限制强制指派", key=f"force_{o['id']}")

            b1, b2 = c3.columns(2)
            if b1.button("👈 手动派", key=f"m_{o['id']}", use_container_width=True):
                res = requests.post(f"{API_BASE}/orders/{o['id']}/dispatch/manual", json={"worker_id": sel_w, "force": force_flag})
                if res.status_code == 200:
                    st.rerun()
                else:
                    st.error(res.json().get("detail", "派单失败"))

            if b2.button("⚡ 自动派", key=f"a_{o['id']}", type="primary", use_container_width=True):
                requests.post(f"{API_BASE}/orders/{o['id']}/dispatch/auto", params={"strategy": current_strategy})
                st.rerun()

with tab2:
    for o in assigned_orders:
        w_name = worker_dict.get(o["assigned_worker_id"], {}).get("name", "未知")
        with st.container(border=True):
            ac1, ac2, ac3 = st.columns([4, 2, 2])
            ac1.markdown(f"**`{o['id']}` {o['title']}**")
            ac1.caption(f"所需技能: {', '.join(o['required_skills']) or '无'}")
            ac2.markdown(f"👷 接单人：**{w_name}** (`{o['assigned_mode']}`)")
            if ac3.button("✅ 确认结单 (释放负载并自动补位)", key=f"done_{o['id']}", type="primary", use_container_width=True):
                requests.post(f"{API_BASE}/orders/{o['id']}/complete")
                st.rerun()

with tab3:
    for o in completed_orders:
        w_name = worker_dict.get(o["assigned_worker_id"], {}).get("name", "-")
        st.markdown(f"- `{o['id']}` **{o['title']}** — 办结人: **{w_name}** *(派单方式: {o['assigned_mode']})*")