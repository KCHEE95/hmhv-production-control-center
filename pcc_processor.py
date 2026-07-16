import pandas as pd
import numpy as np
from datetime import datetime

# ====================== 配置区（可随时调整规则） ======================
CONFIG = {
    "OP_MAPPING": {
        "激光切割": "Laser", "激光": "Laser", "Laser Cutting": "Laser",
        "冲压": "Punch", "冲床": "Punch", "Punching": "Punch",
        "折弯": "Bend", "折床": "Bend", "Bending": "Bend",
        "焊接": "Weld", "焊装": "Weld", "Welding": "Weld",
        "喷涂": "Paint", "喷漆": "Paint", "Painting": "Paint",
        "装配": "Assy", "组装": "Assy", "Assembly": "Assy"
    },
    "SCORE_RULES": {
        "DUE_OVERDUE": 50,
        "DUE_3DAYS": 40,
        "DUE_7DAYS": 25,
        "DUE_14DAYS": 10,
        "CUST_HIGH": 20,
        "CUST_MEDIUM": 10,
        "EXPEDITE_ESCALATE": 50,
        "EXPEDITE_URGENT": 30,
        "BOSS_OVERRIDE": 40,
        "PM_OVERRIDE": 20
    }
}

def clean_epicor_data(df):
    """标准化 Epicor 导出数据，自动匹配字段"""
    # 清理列名
    df.columns = df.columns.str.strip().str.replace(r"[^\w\u4e00-\u9fff]", "", regex=True)
    
    # 字段自动映射
    col_map = {
        "JobNum": ["JobNum", "工单号", "JobNo"],
        "PartNum": ["PartNum", "零件号", "物料号"],
        "Customer": ["Customer", "客户名称", "CustName"],
        "ExworkDate": ["ExworkDate", "出货日期", "交期", "DueDate"],
        "CurrentOp": ["CurrentOp", "当前工序", "CurrentOperation"],
        "CustPriority": ["CustPriority", "客户等级", "重要客户"],
        "Expedite": ["Expedite", "加急等级", "是否加急"],
        "PLCOwner": ["PLC", "负责人", "跟进人"]
    }
    
    for std, variants in col_map.items():
        match = next((c for c in df.columns if any(v in c for v in variants)), None)
        if match:
            df.rename(columns={match: std}, inplace=True)
    
    # 日期标准化
    if "ExworkDate" in df.columns:
        df["ExworkDate"] = pd.to_datetime(df["ExworkDate"], errors="coerce")
    
    # 工序名称统一
    if "CurrentOp" in df.columns:
        df["CurrentOp"] = df["CurrentOp"].astype(str).str.strip().replace(CONFIG["OP_MAPPING"])
    
    return df

def calc_priority(df):
    """计算优先级得分、分级、原因"""
    if "ExworkDate" not in df.columns:
        raise ValueError("缺少核心字段：交期/出货日期，请检查 Epicor 导出文件")
    
    today = datetime.today().date()
    df["DaysToDue"] = (df["ExworkDate"].dt.date - today).dt.days
    df["DaysLate"] = df["DaysToDue"].apply(lambda x: abs(x) if x < 0 else 0)
    
    # 交期风险分
    df["DueScore"] = np.select(
        [df["DaysToDue"] < 0, df["DaysToDue"] <=3, df["DaysToDue"] <=7, df["DaysToDue"] <=14],
        [50,40,25,10], default=0
    )
    
    # 客户等级分
    df["CustScore"] = df["CustPriority"].map({"High":20, "高":20, "Medium":10, "中":10}).fillna(0)
    
    # 加急分
    df["ExpediteScore"] = df["Expedite"].map({"Escalated":50, "客户升级":50, "Urgent":30, "紧急":30}).fillna(0)
    
    # 管理层特批分（后续可扩展字段）
    df["OverrideScore"] = 0
    
    # 总分与分级
    df["TotalScore"] = df["DueScore"] + df["CustScore"] + df["ExpediteScore"] + df["OverrideScore"]
    df["PriorityLevel"] = pd.cut(
        df["TotalScore"], bins=[-1,39,69,99,200],
        labels=["🟢 正常", "🟡 常规优先", "🟠 高优先", "🔴 最高优先"]
    )
    
    # 优先级原因说明
    df["PriorityReason"] = df.apply(
        lambda x: "; ".join([
            f"逾期{x['DaysLate']}天" if x["DaysLate"]>0 else f"距交期剩{x['DaysToDue']}天",
            "高价值客户" if x["CustScore"]==20 else "",
            "客户升级加急" if x["ExpediteScore"]==50 else "紧急订单" if x["ExpediteScore"]==30 else ""
        ]).strip("; "), axis=1
    )
    
    return df
