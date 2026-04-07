import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timezone, timedelta
import re

# 设置页面配置
st.set_page_config(page_title="生产过程数据采集", layout="wide")

# 初始化状态变量
if "form_version" not in st.session_state:
    st.session_state.form_version = 0
if "submit_success" not in st.session_state:
    st.session_state.submit_success = False
if "last_report_csv" not in st.session_state:
    st.session_state.last_report_csv = None
if "last_report_filename" not in st.session_state:
    st.session_state.last_report_filename = ""

# 定义北京时间时区 (UTC+8)
BEIJING_TZ = timezone(timedelta(hours=8))

# --- 字典定义 ---
PRODUCTS = {
    # 第一款产品
    "61010910300-Shroud/910/t=2/DX/205/SQ/FL/DIFF/Powder coated/4x14.5/1010x1010": [
        "1070 (0/-3)", "1010 (±1)", "8xM8", "BC φ954 (±1)", "4x φ14.5 (±0.5)",
        "4x φ8.5 (±0.2)", "BC φ1140 (±1.5)", "φ1021.1 (±2)", "φ979 (±3)", 
        "22 (±2)", "2 (±0.2)", "205 (±3)", "30 (±5)", "R60", "R120"
    ],
    
    # 第二款产品
    "61010800303-Shroud/800/t=2/DX/190/SQ/FL/DIFF/Powder coated/4x14.5/910x910/Conduit": [
        "970 (0/-3)", "910 (±1)", "4x φ14.5 (±0.5)", "4x φ8.5 (±0.5)", "BC φ960.5 (±1)",
        "8xM8", "BC φ835 (±1)", "φ797 (±1.5)", "φ867 (±3)", "190 (±2)", 
        "17 (±3)", "R77", "R92", "30 (±1)", "50 (±1)", "100 (±1)", 
        "106 (±1)", "79 (±1)", "65 (±1)", "51 (±1)", "146 (±1)", 
        "32 (±1)", "3x φ6 (±0.5)"
    ]
}

# --- 核心智能逻辑：自动判定 OK/NG ---
def judge_dimension(dim_str, mode, val_str):
    if mode == "实配 (Pass)":
        return "OK"
    if not val_str or not val_str.strip():
        return ""
    
    try:
        val = float(val_str)
    except ValueError:
        return "格式错误"
        
    m_pm = re.search(r'([\d\.]+)[^\d]*\(\s*±\s*([\d\.]+)[^\d]*\)', dim_str)
    if m_pm:
        nom, tol = float(m_pm.group(1)), float(m_pm.group(2))
        return "OK" if abs(val - nom) <= tol else "NG"
        
    m_diff = re.search(r'([\d\.]+)[^\d]*\(\s*([+-]?[\d\.]+)\s*/\s*([+-]?[\d\.]+)\s*\)', dim_str)
    if m_diff:
        nom, t1, t2 = float(m_diff.group(1)), float(m_diff.group(2)), float(m_diff.group(3))
        upper = nom + max(t1, t2)
        lower = nom + min(t1, t2)
        return "OK" if lower <= val <= upper else "NG"
        
    return "需人工确认"

# ================= 界面构建 =================

st.title("🛠️ 生产过程数据采集")

# --- 拦截并显示成功提示 & 下载按钮 ---
if st.session_state.submit_success:
    st.success("🎉 数据已成功同步！表单已重置，可以开始下一件的记录。")
    st.balloons()
    st.session_state.submit_success = False  # 气球只放一次

# 如果有刚刚生成的报告，展示下载按钮（供用户选择下载或不下载）
if st.session_state.last_report_csv is not None:
    st.info("💡 刚才提交的数据已入库。您可点击下方按钮下载本次记录的竖向表格，方便本地查看或存档。")
    st.download_button(
        label="📥 下载刚才提交的记录单 (Excel/CSV)",
        data=st.session_state.last_report_csv,
        file_name=st.session_state.last_report_filename,
        mime="text/csv"
    )
    st.markdown("---")

# 1. 侧边栏：基础信息
with st.sidebar:
    st.header("📋 基础信息")
    selected_part = st.selectbox("选择图纸产品 (Partname)", list(PRODUCTS.keys()))
    
    st.markdown("---")
    st.header("⏱️ 测量时间")
    measure_date = st.date_input("选择测量日期", datetime.now(BEIJING_TZ).date())

# 2. 主区域：数据采集表格
st.subheader(f"📝 尺寸测量记录单")
st.caption(f"当前产品: {selected_part}")

col1, col2, col3, col4 = st.columns([3, 2, 2, 1.5])
col1.markdown("**图纸尺寸**")
col2.markdown("**记录方式**")
col3.markdown("**实测值**")
col4.markdown("**判定 (OK/NG)**")
st.divider()

input_results = {}
validation_results = {}
dimensions = PRODUCTS[selected_part]

# 动态生成表格行
for dim in dimensions:
    c1, c2, c3, c4 = st.columns([3, 2, 2, 1.5])
    
    c1.write(f"**{dim}**")
    
    mode_key = f"mode_{dim}_{st.session_state.form_version}"
    val_key = f"val_{dim}_{st.session_state.form_version}"
    
    mode = c2.selectbox(
        "模式", ["输入数值", "实配 (Pass)"], 
        key=mode_key, 
        label_visibility="collapsed"
    )
    
    val = ""
    if mode == "输入数值":
        val = c3.text_input("数值", key=val_key, label_visibility="collapsed", placeholder="输入...")
    else:
        c3.text_input("实配", value="已实配 / OK", disabled=True, key=f"disabled_{dim}_{st.session_state.form_version}", label_visibility="collapsed")
        val = "实配"
        
    ok_ng = judge_dimension(dim, mode, val)
    if ok_ng == "OK":
        c4.success("✅ OK")
    elif ok_ng == "NG":
        c4.error("❌ NG")
    elif ok_ng == "":
        c4.write("---")
    else:
        c4.warning(f"⚠️ {ok_ng}")
        
    input_results[dim] = val if mode == "输入数值" else "实配/OK"
    validation_results[dim] = {"mode": mode, "val": val, "ok_ng": ok_ng}

st.markdown("<br>", unsafe_allow_html=True)

# 3. 数据提交逻辑
if st.button("📤 提交数据到系统", type="primary", use_container_width=True):
    empty_fields = [d for d, res in validation_results.items() if res["val"] == "" and res["mode"] == "输入数值"]
    
    if empty_fields:
        st.error(f"⚠️ 还有 {len(empty_fields)} 个尺寸未填写，请完成后再提交！")
    else:
        current_time_str = datetime.now(BEIJING_TZ).strftime('%H:%M:%S')
        full_measure_datetime = f"{measure_date} {current_time_str}"
        record_time = datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")
        
        # [步骤A] 准备横向数据（给谷歌表格）
        new_row = {
            "记录生成时间": record_time,
            "测量时间": full_measure_datetime,
            "PartName": selected_part,
            **input_results
        }
        
        # [步骤B] 准备竖向数据（给用户下载）
        report_data = []
        for dim in dimensions:
            res = validation_results[dim]
            report_data.append({
                "图纸尺寸": dim,
                "记录方式": res["mode"],
                "实测值": res["val"] if res["mode"] == "输入数值" else "已实配/OK",
                "判定结果": res["ok_ng"] if res["ok_ng"] != "" else "OK"
            })
        
        report_df = pd.DataFrame(report_data)
        
        # 构建带表头说明的CSV文本（加了utf-8-sig让Excel能直接打开且中文不乱码）
        header_text = f"产品物料号及名称:, {selected_part}\n测量时间:, {full_measure_datetime}\n\n"
        csv_text = header_text + report_df.to_csv(index=False)
        csv_bytes = csv_text.encode('utf-8-sig')
        
        # 存入 session_state 以便刷新后展示下载按钮
        st.session_state.last_report_csv = csv_bytes
        st.session_state.last_report_filename = f"检验记录_{record_time.replace(':', '').replace(' ', '_')}.csv"
        
        try:
            # 写入谷歌云端表格
            conn = st.connection("gsheets", type=GSheetsConnection)
            existing_data = conn.read(worksheet="Sheet1")
            updated_df = pd.concat([existing_data, pd.DataFrame([new_row])], ignore_index=True)
            conn.update(worksheet="Sheet1", data=updated_df)
            
            # 成功后刷新重置界面
            st.session_state.submit_success = True  
            st.session_state.form_version += 1      
            st.rerun()                              
            
        except Exception as e:
            st.error(f"提交失败: {e}")
