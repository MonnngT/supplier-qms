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
if "delete_success" not in st.session_state:
    st.session_state.delete_success = False
if "last_report_csv" not in st.session_state:
    st.session_state.last_report_csv = None
if "last_report_filename" not in st.session_state:
    st.session_state.last_report_filename = ""

# 定义北京时间时区 (UTC+8)
BEIJING_TZ = timezone(timedelta(hours=8))

# --- 字典定义 ---
PRODUCTS = {
    "61010910300-Shroud/910/t=2/DX/205/SQ/FL/DIFF/Powder coated/4x14.5/1010x1010": [
        "1070 (0/-3)", "1010 (±1)", "8xM8", "BC φ954 (±1)", "4x φ14.5 (±0.5)",
        "4x φ8.5 (±0.2)", "BC φ1140 (±1.5)", "φ1021.1 (±2)", "φ979 (±3)", 
        "22 (±2)", "2 (±0.2)", "205 (±3)", "30 (±5)", "R60", "R120"
    ],
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

# --- 拦截并显示成功提示 & 删除提示 ---
if st.session_state.submit_success:
    st.success("🎉 数据已成功同步！表单已重置，可以开始下一件的记录。")
    st.balloons()
    st.session_state.submit_success = False

if st.session_state.delete_success:
    st.toast("🗑️ 该组数据已从云端永久删除！", icon="✅")
    st.session_state.delete_success = False

if st.session_state.last_report_csv is not None:
    st.info("💡 刚才提交的数据已入库。您可点击下方按钮直接下载本次的竖向表格。")
    st.download_button(
        label="📥 立即下载刚提交的记录单 (Excel)",
        data=st.session_state.last_report_csv,
        file_name=st.session_state.last_report_filename,
        mime="text/csv"
    )
    st.markdown("<br>", unsafe_allow_html=True)

# 1. 侧边栏：基础信息
with st.sidebar:
    st.header("📋 基础信息")
    selected_part = st.selectbox("选择图纸产品 (Partname)", list(PRODUCTS.keys()))
    
    st.markdown("---")
    st.header("⏱️ 测量时间")
    measure_date = st.date_input("选择测量日期", datetime.now(BEIJING_TZ).date())

# 2. 主区域：数据采集表格
st.subheader(f"📝 尺寸测量记录单")
st.caption(f"当前填写产品: {selected_part}")

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
    
    mode = c2.selectbox("模式", ["输入数值", "实配 (Pass)"], key=mode_key, label_visibility="collapsed")
    
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
        
        new_row = {
            "记录生成时间": record_time,
            "测量时间": full_measure_datetime,
            "PartName": selected_part,
            **input_results
        }
        
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
        header_text = f"产品物料号及名称:, {selected_part}\n测量时间:, {full_measure_datetime}\n\n"
        csv_text = header_text + report_df.to_csv(index=False)
        st.session_state.last_report_csv = csv_text.encode('utf-8-sig')
        st.session_state.last_report_filename = f"检验记录_{record_time.replace(':', '').replace(' ', '_')}.csv"
        
        try:
            conn = st.connection("gsheets", type=GSheetsConnection)
            # 【修复1：强制不使用缓存拉取数据】
            existing_data = conn.read(worksheet="Sheet1", ttl=0)
            updated_df = pd.concat([existing_data, pd.DataFrame([new_row])], ignore_index=True)
            conn.update(worksheet="Sheet1", data=updated_df)
            
            st.session_state.submit_success = True  
            st.session_state.form_version += 1      
            st.rerun()                              
        except Exception as e:
            st.error(f"提交失败: {e}")

# ================= 历史数据管理 (含删除功能) =================
st.markdown("---")
st.subheader("🗄️ 历史记录管理")

try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    # 【修复2：强制不使用缓存拉取历史数据】
    df_history = conn.read(worksheet="Sheet1", ttl=0)
    
    # 过滤掉空行
    df_history = df_history.dropna(subset=["记录生成时间", "PartName"], how="all")
    
    if not df_history.empty:
        # 1. 展示全局表格
        st.dataframe(df_history.iloc[::-1], use_container_width=True)
        
        st.markdown("#### 操作指定的历史记录")
        # 2. 下拉菜单：选择要操作的记录
        options = df_history["记录生成时间"].astype(str) + " | " + df_history["PartName"].astype(str)
        selected_history = st.selectbox("选择目标记录：", options.iloc[::-1])
        
        if selected_history:
            selected_time = selected_history.split(" | ")[0]
            row_data = df_history[df_history["记录生成时间"] == selected_time].iloc[0]
            
            his_part_name = row_data["PartName"]
            his_measure_time = row_data["测量时间"]
            
            # --- 准备下载数据 ---
            his_csv_bytes = None
            if his_part_name in PRODUCTS:
                his_dims = PRODUCTS[his_part_name]
                his_report_data = []
                
                for dim in his_dims:
                    val = str(row_data.get(dim, ""))
                    if val == "nan" or val.strip() == "":
                        val = ""
                        
                    if val == "实配/OK":
                        mode = "实配 (Pass)"
                        ok_ng = "OK"
                    else:
                        mode = "输入数值"
                        ok_ng = judge_dimension(dim, mode, val) if val else "未填"
                        
                    his_report_data.append({
                        "图纸尺寸": dim, "记录方式": mode, "实测值": val, "判定结果": ok_ng
                    })
                
                his_report_df = pd.DataFrame(his_report_data)
                his_header = f"产品物料号及名称:, {his_part_name}\n测量时间:, {his_measure_time}\n\n"
                his_csv_text = his_header + his_report_df.to_csv(index=False)
                his_csv_bytes = his_csv_text.encode('utf-8-sig')
                filename_time = str(selected_time).replace(':', '').replace(' ', '_').replace('-', '')

            # --- 渲染“下载”与“删除”按钮组 ---
            col_action1, col_action2 = st.columns(2)
            
            with col_action1:
                if his_csv_bytes:
                    st.download_button(
                        label="⬇️ 下载选中的竖向报告 (Excel)",
                        data=his_csv_bytes,
                        file_name=f"历史记录_{filename_time}.csv",
                        mime="text/csv",
                        key="download_history_btn",
                        use_container_width=True
                    )
                else:
                    st.warning("⚠️ 该产品已失效，无法生成竖向报告。")
                    
            with col_action2:
                # 删除按钮
                if st.button("🗑️ 从云端永久删除此记录", type="primary", use_container_width=True):
                    # 过滤掉选中的这行时间戳，把剩下的数据重新传给谷歌表格
                    df_cleaned = df_history[df_history["记录生成时间"] != selected_time]
                    
                    try:
                        conn.update(worksheet="Sheet1", data=df_cleaned)
                        st.session_state.delete_success = True
                        st.rerun()
                    except Exception as e:
                        st.error(f"删除失败请重试: {e}")

    else:
        st.info("暂无历史提交数据。")
except Exception as e:
    st.error(f"无法加载历史数据，请检查网络或谷歌表格连接: {e}")
