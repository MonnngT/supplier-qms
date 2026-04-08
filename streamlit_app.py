import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timezone, timedelta
import re

# 设置页面配置
st.set_page_config(page_title="生产过程数据采集系统", layout="wide")

# 初始化状态变量
if "form_version" not in st.session_state:
    st.session_state.form_version = 0
if "submit_success" not in st.session_state:
    st.session_state.submit_success = False
if "delete_success" not in st.session_state:
    st.session_state.delete_success = False

# 定义北京时间时区 (UTC+8)
BEIJING_TZ = timezone(timedelta(hours=8))

# --- 产品字典定义 ---
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
        "106 (±1)", "79 (±1)", "65 (±1)", "61 (±1)", "146 (±1)", 
        "32 (±1)", "2 (±0.2)", "3x φ6 (±0.5)"
    ]
}

# --- 自动判定逻辑 ---
def judge_dimension(dim_str, mode, val_str):
    if mode == "实配 (Pass)": return "OK"
    if not val_str or not val_str.strip(): return ""
    try:
        val = float(val_str)
    except ValueError: return "格式错误"
    m_pm = re.search(r'([\d\.]+)[^\d]*\(\s*±\s*([\d\.]+)[^\d]*\)', dim_str)
    if m_pm:
        nom, tol = float(m_pm.group(1)), float(m_pm.group(2))
        return "OK" if abs(val - nom) <= tol else "NG"
    m_diff = re.search(r'([\d\.]+)[^\d]*\(\s*([+-]?[\d\.]+)\s*/\s*([+-]?[\d\.]+)\s*\)', dim_str)
    if m_diff:
        nom, t1, t2 = float(m_diff.group(1)), float(m_diff.group(2)), float(m_diff.group(3))
        upper, lower = nom + max(t1, t2), nom + min(t1, t2)
        return "OK" if lower <= val <= upper else "NG"
    return "需人工确认"

# ================= 界面构建 =================

st.title("🛠️ 生产过程数据采集")

if st.session_state.submit_success:
    st.success("🎉 数据已成功同步至云端！")
    st.balloons()
    st.session_state.submit_success = False

if st.session_state.delete_success:
    st.toast("🗑️ 选中的记录已从云端永久删除！", icon="✅")
    st.session_state.delete_success = False

with st.sidebar:
    st.header("📋 基础信息")
    selected_part = st.selectbox("选择图纸产品", list(PRODUCTS.keys()))
    st.markdown("---")
    st.header("⏱️ 测量时间")
    measure_date = st.date_input("选择测量日期", datetime.now(BEIJING_TZ).date())

st.subheader(f"📝 尺寸测量记录单")
st.caption(f"当前产品: {selected_part}")

col1, col2, col3, col4 = st.columns([3, 2, 2, 1.5])
col1.markdown("**图纸尺寸**")
col2.markdown("**记录方式**")
col3.markdown("**实测值**")
col4.markdown("**判定 (OK/NG)**")
st.divider()

input_results, validation_results = {}, {}
dimensions = PRODUCTS[selected_part]

for dim in dimensions:
    c1, c2, c3, c4 = st.columns([3, 2, 2, 1.5])
    c1.write(f"**{dim}**")
    mode = c2.selectbox("模式", ["输入数值", "实配 (Pass)"], key=f"m_{dim}_{st.session_state.form_version}", label_visibility="collapsed")
    if mode == "输入数值":
        val = c3.text_input("数值", key=f"v_{dim}_{st.session_state.form_version}", label_visibility="collapsed", placeholder="输入...")
    else:
        c3.text_input("实配", value="已实配 / OK", disabled=True, key=f"d_{dim}_{st.session_state.form_version}", label_visibility="collapsed")
        val = "实配"
    ok_ng = judge_dimension(dim, mode, val)
    if ok_ng == "OK": c4.success("✅ OK")
    elif ok_ng == "NG": c4.error("❌ NG")
    else: c4.write("---")
    input_results[dim] = val if mode == "输入数值" else "实配/OK"
    validation_results[dim] = {"mode": mode, "val": val, "ok_ng": ok_ng}

st.markdown("<br>", unsafe_allow_html=True)

if st.button("📤 提交数据到系统", type="primary", use_container_width=True):
    empty_fields = [d for d, res in validation_results.items() if res["val"] == "" and res["mode"] == "输入数值"]
    if empty_fields:
        st.error(f"⚠️ 还有 {len(empty_fields)} 个尺寸未填写！")
    else:
        full_measure_datetime = f"{measure_date} {datetime.now(BEIJING_TZ).strftime('%H:%M:%S')}"
        new_row = {"测量时间": full_measure_datetime, "PartName": selected_part, **input_results}
        try:
            conn = st.connection("gsheets", type=GSheetsConnection)
            existing_data = conn.read(worksheet="Sheet1", ttl="1s") 
            updated_df = pd.concat([existing_data, pd.DataFrame([new_row])], ignore_index=True)
            conn.update(worksheet="Sheet1", data=updated_df)
            st.cache_data.clear() 
            st.session_state.submit_success, st.session_state.form_version = True, st.session_state.form_version + 1
            st.rerun()                              
        except Exception as e:
            st.error(f"提交失败，请等待10秒后重试。")

# ================= 历史记录管理 (支持批量多选) =================
st.markdown("---")
st.subheader(f"🗄️ {selected_part.split('-')[0]} 历史追溯与管理")

try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    df_history = conn.read(worksheet="Sheet1", ttl="15s")
    df_history = df_history.dropna(subset=["测量时间", "PartName"], how="all")
    
    if not df_history.empty:
        df_current_part = df_history[df_history["PartName"] == selected_part]
        
        if not df_current_part.empty:
            st.markdown("👆 **请在下方表格最左侧勾选您需要操作的行记录（支持多选）**")
            
            # 数据倒序显示
            df_display = df_current_part.dropna(axis=1, how='all').iloc[::-1].reset_index(drop=True)
            
            # 【关键修改】：将 selection_mode 改为 "multi-row" 支持批量选中
            selection_event = st.dataframe(
                df_display,
                use_container_width=True,
                on_select="rerun",
                selection_mode="multi-row"
            )
            
            selected_rows = selection_event.selection.rows
            
            if selected_rows:
                # 获取所有被选中的行数据
                selected_data = df_display.iloc[selected_rows]
                # 提取所有被选中的时间戳列表
                selected_times = selected_data["测量时间"].tolist()
                
                st.info(f"✅ 当前已选中 **{len(selected_rows)}** 条记录。")
                
                # --- 准备批量下载数据 ---
                his_dims, his_report_data = PRODUCTS[selected_part], []
                
                # 循环遍历每一条被选中的数据
                for _, row_data in selected_data.iterrows():
                    sel_time = row_data["测量时间"]
                    for dim in his_dims:
                        val = str(row_data.get(dim, ""))
                        if val == "nan" or val.strip() == "": val = ""
                        mode, ok_ng = ("实配 (Pass)", "OK") if val == "实配/OK" else ("输入数值", judge_dimension(dim, "输入数值", val))
                        
                        # 批量下载的表格中加入了"测量时间"列，方便区分不同批次的数据
                        his_report_data.append({
                            "测量时间": sel_time, 
                            "图纸尺寸": dim, 
                            "记录方式": mode, 
                            "实测值": val, 
                            "判定结果": ok_ng if val else "未填"
                        })
                
                his_report_df = pd.DataFrame(his_report_data)
                his_header = f"产品物料号及名称:, {selected_part}\n批量导出条数:, {len(selected_rows)}条\n\n"
                his_csv_bytes = (his_header + his_report_df.to_csv(index=False)).encode('utf-8-sig')

                # --- 渲染批量操作按钮 ---
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    st.download_button(
                        label=f"⬇️ 批量下载选中的 {len(selected_rows)} 条记录 (Excel)",
                        data=his_csv_bytes,
                        file_name=f"批量记录_{datetime.now(BEIJING_TZ).strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
                with col_btn2:
                    if st.button(f"🗑️ 永久删除选中的 {len(selected_rows)} 条记录", type="primary", use_container_width=True):
                        df_latest = conn.read(worksheet="Sheet1", ttl="1s")
                        
                        # 【核心批量删除逻辑】：利用 .isin() 找出并剔除所有被选中的时间戳
                        df_cleaned = df_latest[~df_latest["测量时间"].isin(selected_times)]
                        
                        conn.update(worksheet="Sheet1", data=df_cleaned)
                        st.cache_data.clear() 
                        st.session_state.delete_success = True
                        st.rerun()
        else:
            st.info(f"当前产品 ({selected_part.split('-')[0]}) 暂无历史数据。")
    else:
        st.info("总数据库目前为空。")
except Exception as e:
    if "429" in str(e):
        st.warning("⏱️ Google 访问受限，请等待 15 秒后刷新页面即可恢复显示。")
    else:
        st.error(f"数据加载失败: {e}")
