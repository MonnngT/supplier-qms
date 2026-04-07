import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import re

# 设置页面配置，展开为宽屏模式更适合显示表格
st.set_page_config(page_title="生产过程数据采集", layout="wide")

# 产品定义 (已补充 4xφ8.5 和 2 这两个尺寸)
PRODUCTS = {
    "Shroud/910/t=2/DX/205/SQ/FL/DIFF/Powder coated/4x14.5/1010x1010": [
        "1070 (0/-3)", "1010 (±1)", "8xM8", "BC φ954 (±1)", "4x φ14.5 (±0.5)",
        "4x φ8.5 (±0.2)", "BC φ1140 (±1.5)", "φ1021.1 (±2)", "φ979 (±3)", 
        "22 (±2)", "2 (±0.2)", "205 (±3)", "30 (±5)", "R60", "R120"
    ]
}

# --- 核心智能逻辑：自动判定 OK/NG ---
def judge_dimension(dim_str, mode, val_str):
    """根据图纸要求和实测值自动判定OK/NG"""
    if mode == "实配 (Pass)":
        return "OK"
    if not val_str.strip():
        return "" # 用户还没输入内容
    
    try:
        val = float(val_str)
    except ValueError:
        return "格式错误"
        
    # 匹配对称公差，例如: "1010 (±1)", "4x φ8.5 (±0.2)"
    m_pm = re.search(r'([\d\.]+)[^\d]*\(\s*±\s*([\d\.]+)[^\d]*\)', dim_str)
    if m_pm:
        nom, tol = float(m_pm.group(1)), float(m_pm.group(2))
        return "OK" if abs(val - nom) <= tol else "NG"
        
    # 匹配不对称公差，例如: "1070 (0/-3)"
    m_diff = re.search(r'([\d\.]+)[^\d]*\(\s*([+-]?[\d\.]+)\s*/\s*([+-]?[\d\.]+)[^\d]*\)', dim_str)
    if m_diff:
        nom, t1, t2 = float(m_diff.group(1)), float(m_diff.group(2)), float(m_diff.group(3))
        upper = nom + max(t1, t2)
        lower = nom + min(t1, t2)
        return "OK" if lower <= val <= upper else "NG"
        
    # 如果尺寸没有明确的公差标记
    return "需人工确认"


# ================= 界面构建 =================

st.title("🛠️ 生产过程数据采集")

# 1. 侧边栏：基础信息与全局日期配置
with st.sidebar:
    st.header("📋 基础信息")
    selected_part = st.selectbox("选择图纸产品 (Partname)", list(PRODUCTS.keys()))
    
    st.markdown("---")
    st.header("⏱️ 测量时间")
    st.caption("只需选择日期，系统会在提交时自动补充当前时间点")
    # 仅保留日期选择
    measure_date = st.date_input("选择测量日期", datetime.today())

# 2. 主区域：数据采集表格
st.subheader(f"📝 尺寸测量记录单: {selected_part}")

# 构建表头
col1, col2, col3, col4 = st.columns([3, 2, 2, 1.5])
col1.markdown("**图纸尺寸**")
col2.markdown("**记录方式**")
col3.markdown("**实测值**")
col4.markdown("**判定 (OK/NG)**")
st.divider()

# 存储用户输入的数据
input_results = {}
dimensions = PRODUCTS[selected_part]

# 动态生成表格行
for dim in dimensions:
    c1, c2, c3, c4 = st.columns([3, 2, 2, 1.5])
    
    # 第1列: 尺寸名称
    c1.write(f"**{dim}**")
    
    # 第2列: 下拉选择模式
    mode = c2.selectbox(
        "模式", 
        ["输入数值", "实配 (Pass)"], 
        key=f"mode_{dim}", 
        label_visibility="collapsed"
    )
    
    # 第3列: 动态输入框
    val = ""
    if mode == "输入数值":
        val = c3.text_input("数值", key=f"val_{dim}", label_visibility="collapsed", placeholder="请输入数值...")
    else:
        c3.text_input("实配", value="已实配 / OK", disabled=True, key=f"val_pass_{dim}", label_visibility="collapsed")
        val = "实配"
        
    # 第4列: 自动判定与显示
    ok_ng = judge_dimension(dim, mode, val)
    if ok_ng == "OK":
        c4.success("✅ OK")
    elif ok_ng == "NG":
        c4.error("❌ NG")
    elif ok_ng == "":
        c4.write("---") # 未输入状态
    else:
        c4.warning(f"⚠️ {ok_ng}")
        
    # 保存该行数据以备提交
    input_results[dim] = val if mode == "输入数值" else "实配/OK"

st.markdown("<br>", unsafe_allow_html=True)

# 3. 数据提交逻辑
if st.button("📤 提交数据到系统", type="primary", use_container_width=True):
    # 自动获取当前时分秒，与所选日期拼接
    current_time_str = datetime.now().strftime('%H:%M:%S')
    full_measure_datetime = f"{measure_date} {current_time_str}"
    
    # 准备要上传的数据行
    new_row = {
        "记录生成时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "测量时间": full_measure_datetime,
        "PartName": selected_part,
        **input_results
    }
    
    # 连接并更新 Google Sheets
    try:
        conn = st.connection("gsheets", type=GSheetsConnection)
        existing_data = conn.read(worksheet="Sheet1")
        updated_df = pd.concat([existing_data, pd.DataFrame([new_row])], ignore_index=True)
        conn.update(worksheet="Sheet1", data=updated_df)
        
        st.toast("数据已成功同步至云端表单！", icon="🎉")
        st.balloons()
    except Exception as e:
        st.error(f"提交失败，请检查连接或配置: {e}")
