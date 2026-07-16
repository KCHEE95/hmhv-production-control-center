import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import datetime

st.set_page_config(page_title="生产控制中心PCC", layout="wide", initial_sidebar_state="expanded")
st.title("🏭 多品种小批量工厂 · 生产控制中心")
st.subheader("📊 数据驱动优先级 · 告别救火式排产")

# ====================== 核心数据处理（已修复所有兼容问题） ======================
def clean_epicor_data(df):
    # 清理列名
    df.columns = df.columns.str.strip().str.replace(r"[^\w\u4e00-\u9fff]", "", regex=True)
    
    # 字段自动映射（兼容所有常见 Epicor 列名）
    col_map = {
        "JobNum": ["JobNum", "工单号", "JobNo", "JobID"],
        "PartNum": ["PartNum", "零件号", "物料号", "PartID"],
        "Customer": ["Customer", "客户名称", "CustName", "CustID", "客户"],
        "ExworkDate": ["ExworkDate", "出货日期", "交期", "DueDate", "ShipDate", "预计出货日"],
        "CurrentOp": ["CurrentOp", "当前工序", "CurrentOperation", "当前步骤", "OpCode"],
        "CustPriority": ["CustPriority", "客户等级", "重要客户", "Priority"],
        "Expedite": ["Expedite", "加急等级", "是否加急", "Urgent"],
        "PLCOwner": ["PLC", "负责人", "跟进人", "Owner", "跟进"]
    }
    
    for std_name, variants in col_map.items():
        match_col = next((c for c in df.columns if any(var.lower() in c.lower() for var in variants)), None)
        if match_col:
            df.rename(columns={match_col: std_name}, inplace=True)
        else:
            # 缺失字段自动补空，不中断流程
            df[std_name] = np.nan
    
    # 🔧 修复日期转换：兼容所有格式，错误值强制设为空
    if "ExworkDate" in df.columns:
        df["ExworkDate"] = pd.to_datetime(df["ExworkDate"], errors="coerce")
    
    # 工序名称标准化
    op_mapping = {
        "激光切割": "Laser", "激光": "Laser", "Laser Cutting": "Laser", "Laser": "Laser",
        "冲压": "Punch", "冲床": "Punch", "Punching": "Punch", "Punch": "Punch",
        "折弯": "Bend", "折床": "Bend", "Bending": "Bend", "Bend": "Bend",
        "焊接": "Weld", "焊装": "Weld", "Welding": "Weld", "Weld": "Weld",
        "喷涂": "Paint", "喷漆": "Paint", "Painting": "Paint", "Paint": "Paint",
        "装配": "Assy", "组装": "Assy", "Assembly": "Assy", "Assy": "Assy"
    }
    if "CurrentOp" in df.columns:
        df["CurrentOp"] = df["CurrentOp"].astype(str).str.strip().str.title()
        df["CurrentOp"] = df["CurrentOp"].replace(op_mapping)
        df["CurrentOp"] = df["CurrentOp"].fillna("未知工序")
    
    # 基础字段补空
    df["Customer"] = df["Customer"].fillna("未知客户")
    df["JobNum"] = df["JobNum"].fillna("无工单号")
    df["PartNum"] = df["PartNum"].fillna("无零件号")
    
    return df

def calc_priority(df):
    today = datetime.today().date()
    
    # 🔧 安全计算日期差：空日期默认设为30天后
    df["DaysToDue"] = df["ExworkDate"].apply(
        lambda x: (x.date() - today).days if pd.notnull(x) else 30
    )
    df["DaysLate"] = df["DaysToDue"].apply(lambda x: abs(x) if x < 0 else 0)
    
    # 交期风险评分
    df["DueScore"] = np.select(
        [
            df["DaysToDue"] < 0,
            df["DaysToDue"] <= 3,
            df["DaysToDue"] <= 7,
            df["DaysToDue"] <= 14
        ],
        [50, 40, 25, 10],
        default=0
    )
    
    # 客户等级评分
    df["CustScore"] = df["CustPriority"].astype(str).str.strip().str.title().map({
        "High": 20, "高": 20, "高价值": 20,
        "Medium": 10, "中": 10, "普通": 10
    }).fillna(0)
    
    # 加急评分
    df["ExpediteScore"] = df["Expedite"].astype(str).str.strip().str.title().map({
        "Escalated": 50, "客户升级": 50, "升级": 50,
        "Urgent": 30, "紧急": 30, "加急": 30
    }).fillna(0)
    
    # 总分与优先级分级
    df["TotalScore"] = df["DueScore"] + df["CustScore"] + df["ExpediteScore"]
    df["PriorityLevel"] = pd.cut(
        df["TotalScore"],
        bins=[-1, 39, 69, 99, 200],
        labels=["🟢 正常", "🟡 常规优先", "🟠 高优先", "🔴 最高优先"]
    )
    
    # 优先级原因说明
    df["PriorityReason"] = df.apply(
        lambda x: "; ".join([
            f"逾期{x['DaysLate']}天" if x["DaysLate"] > 0 else f"距交期剩{x['DaysToDue']}天",
            "高价值客户" if x["CustScore"] == 20 else "",
            "客户升级加急" if x["ExpediteScore"] == 50 else "紧急订单" if x["ExpediteScore"] == 30 else ""
        ]).strip("; "),
        axis=1
    )
    
    return df

# ====================== 页面入口 ======================
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
            st.stop()
    elif "df" in st.session_state:
        df_final = st.session_state["df"]
    else:
        st.info("ℹ️ 请先上传 Epicor 导出的 Excel 文件开始使用")
        st.stop()

# 全局筛选（已修复字段缺失问题）
st.subheader("🔍 快速筛选")
c1, c2, c3, c4 = st.columns(4)
with c1: 
    cust_options = sorted(df_final["Customer"].dropna().unique().tolist())
    cust_sel = st.multiselect("客户", cust_options)
with c2: 
    op_options = sorted(df_final["CurrentOp"].dropna().unique().tolist())
    op_sel = st.multiselect("当前工序", op_options)
with c3: 
    level_options = sorted(df_final["PriorityLevel"].dropna().unique().tolist())
    level_sel = st.multiselect("优先级", level_options)
with c4: 
    days_range = st.slider("距交期天数", -90, 180, (-30, 60))

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
    show_cols = ["排名", "PriorityLevel", "JobNum", "Customer", "ExworkDate", "CurrentOp", "TotalScore", "PriorityReason"]
    show_cols = [c for c in show_cols if c in df_show.columns]
    st.dataframe(df_show[show_cols], use_container_width=True, hide_index=True)

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
