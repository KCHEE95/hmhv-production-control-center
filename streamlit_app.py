import streamlit as st
import pandas as pd
import plotly.express as px
from pcc_processor import clean_epicor_data, calc_priority

# 页面基础配置
st.set_page_config(page_title="生产控制中心PCC", layout="wide", initial_sidebar_state="expanded")
st.title("🏭 多品种小批量工厂 · 生产控制中心")
st.subheader("📊 数据驱动优先级 · 告别救火式排产")

# 侧边栏：上传 Epicor 文件
with st.sidebar:
    st.header("📂 上传 Epicor 导出 Excel")
    uploaded_file = st.file_uploader("仅支持 .xlsx 格式", type="xlsx")
    
    if uploaded_file:
        try:
            df_raw = pd.read_excel(uploaded_file, engine="openpyxl")
            df_clean = clean_epicor_data(df_raw)
            df_final = calc_priority(df_clean)
            st.session_state["df"] = df_final
            st.success(f"✅ 加载完成：共 {len(df_final)} 条工单")
        except Exception as e:
            st.error(f"❌ 处理失败：{str(e)}")
    elif "df" in st.session_state:
        df_final = st.session_state["df"]
    else:
        st.info("ℹ️ 请先上传 Epicor 导出的 Excel 文件开始使用")
        st.stop()

# 全局筛选器
st.subheader("🔍 快速筛选")
c1, c2, c3, c4 = st.columns(4)
with c1: cust_sel = st.multiselect("客户", df_final["Customer"].dropna().unique())
with c2: op_sel = st.multiselect("当前工序", df_final["CurrentOp"].dropna().unique())
with c3: level_sel = st.multiselect("优先级", df_final["PriorityLevel"].unique())
with c4: days_range = st.slider("距交期天数", -30, 60, (-30, 60))

# 应用筛选
df_show = df_final.copy()
if cust_sel: df_show = df_show[df_show["Customer"].isin(cust_sel)]
if op_sel: df_show = df_show[df_show["CurrentOp"].isin(op_sel)]
if level_sel: df_show = df_show[df_show["PriorityLevel"].isin(level_sel)]
df_show = df_show[(df_show["DaysToDue"] >= days_range[0]) & (df_show["DaysToDue"] <= days_range[1])]

# 页面导航
page = st.sidebar.radio("📑 功能页面", [
    "🔥 优先级总榜", "🚚 出货风险看板", "⚠️ 逾期工单", "🔄 WIP流转", "⚡ 瓶颈分析", "🔎 工单查询"
])

# ---------------------- 页面内容 ----------------------
if page == "🔥 优先级总榜":
    st.subheader("🔥 每日生产会议核心排产参考")
    df_show = df_show.sort_values("TotalScore", ascending=False).reset_index(drop=True)
    df_show["排名"] = df_show.index + 1
    cols = ["排名", "PriorityLevel", "JobNum", "Customer", "ExworkDate", "CurrentOp", "TotalScore", "PriorityReason"]
    st.dataframe(df_show[cols], use_container_width=True, hide_index=True)

elif page == "⚡ 瓶颈分析":
    st.subheader("⚡ 各工序工单积压统计")
    op_count = df_show["CurrentOp"].value_counts().reset_index()
    op_count.columns = ["工序", "待处理工单数量"]
    fig = px.bar(op_count, x="工序", y="待处理工单数量", color="待处理工单数量",
                color_continuous_scale="OrRd", text="待处理工单数量")
    st.plotly_chart(fig, use_container_width=True)

elif page == "🔎 工单查询":
    st.subheader("🔎 按工单号/零件号/客户精准查询")
    keyword = st.text_input("输入关键词搜索：")
    if keyword:
        res = df_show[
            df_show["JobNum"].astype(str).str.contains(keyword, case=False) |
            df_show["PartNum"].astype(str).str.contains(keyword, case=False) |
            df_show["Customer"].astype(str).str.contains(keyword, case=False)
        ]
        if len(res) > 0:
            st.dataframe(res, use_container_width=True)
        else:
            st.warning("未找到匹配工单")
