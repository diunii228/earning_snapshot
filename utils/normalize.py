import re
import copy
import re
import copy
import re
import copy
import re
import copy

def normalize_banking_kpis(extracted_json: dict) -> dict:
    if not isinstance(extracted_json, dict):
        return extracted_json
        
    normalized_data = copy.deepcopy(extracted_json)
    
    pct_keywords = ['ratio', 'growth', 'roa', 'roe', 'nim', 'cost', 'yield', 'car', 'npl', 'casa', 'cir', 'coverage']
    abs_keywords = ['pbt', 'assets', 'credit', 'deposit', 'equity', 'capital', 'income', 'profit', 'expenses', 'nii', 'pat', 'total', 'provision']
    
    for section_name, kpis in normalized_data.items():
        if not isinstance(kpis, dict): 
            continue
            
        keys_to_delete = [] 
        
        for kpi_name, kpi_data in kpis.items():
            if not isinstance(kpi_data, dict) or kpi_data.get('value') in [None, "-", "N/A", "null", ""]:
                keys_to_delete.append(kpi_name)
                continue
                
            raw_val = kpi_data['value']
            raw_unit = str(kpi_data.get('unit', '')).strip().lower()

            val = None
            if isinstance(raw_val, str):
                clean_val_str = raw_val.strip().replace(' ', '')
                if ',' in clean_val_str and '.' in clean_val_str:
                    if clean_val_str.rfind(',') > clean_val_str.rfind('.'):
                        clean_val_str = clean_val_str.replace('.', '').replace(',', '.')
                    else:
                        clean_val_str = clean_val_str.replace(',', '')
                elif ',' in clean_val_str:
                    parts = clean_val_str.split(',')
                    if len(parts) == 2 and len(parts[1]) == 3: 
                        clean_val_str = clean_val_str.replace(',', '')
                    else: 
                        clean_val_str = clean_val_str.replace(',', '.')
                elif '.' in clean_val_str:
                    parts = clean_val_str.split('.')
                    if len(parts) == 2 and len(parts[1]) == 3: 
                        clean_val_str = clean_val_str.replace('.', '')
                try:
                    val = float(clean_val_str)
                except ValueError:
                    keys_to_delete.append(kpi_name)
                    continue 
            else:
                try:
                    val = float(raw_val)
                except (ValueError, TypeError):
                    keys_to_delete.append(kpi_name)
                    continue

            u_lower = raw_unit.replace('vnđ', 'vnd').replace('đồng', 'vnd').replace('tỉ', 'tỷ').replace('ti ', 'tỷ')
            kpi_name_lower = kpi_name.lower()
            
            # =========================================================
            # ĐÃ SỬA: DÙNG EXACT MATCH CHO P/E VÀ P/B TRÁNH BẮT NHẦM PBT
            # =========================================================
            if kpi_name_lower in ['p_e_ratio', 'p_b_ratio', 'pe', 'pb']:
                if val > 100: 
                    keys_to_delete.append(kpi_name)
                    continue
                kpi_data['value'] = round(val, 2)
                kpi_data['unit'] = 'x'

            elif 'eps' in kpi_name_lower:
                kpi_data['value'] = int(val)
                kpi_data['unit'] = 'VND'

            elif any(term in kpi_name_lower for term in pct_keywords):
                if 'npl' in kpi_name_lower and val > 30 and 'coverage' not in kpi_name_lower:
                    keys_to_delete.append(kpi_name)
                    continue
                    
                if any(t in kpi_name_lower for t in ['roa', 'roe', 'nim']) and val > 100:
                    keys_to_delete.append(kpi_name)
                    continue

                if val < 1.0 and ("%" not in raw_unit) and val > 0:
                    val = val * 100
                kpi_data['value'] = round(val, 2)
                kpi_data['unit'] = '%'

            elif any(term in kpi_name_lower for term in abs_keywords):
                final_val = val
                
                if any(x in u_lower for x in ["triệu tỷ", "tr tỷ"]):
                    final_val = val * 1_000_000
                elif any(x in u_lower for x in ["nghìn tỷ", "ngàn tỷ", "nghin ty"]):
                    final_val = val * 1_000
                elif any(x in u_lower for x in ["tỷ", "ty"]):
                    final_val = val
                elif any(x in u_lower for x in ["triệu", "million", "tr"]):
                    final_val = val / 1_000
                elif any(x in u_lower for x in ["vnd", "đ", "dong"]) or u_lower == "":
                    if val > 100_000_000:
                        final_val = val / 1_000_000_000

                if final_val < 10 and not any(t in kpi_name_lower for t in ['eps']):
                    keys_to_delete.append(kpi_name)
                    continue

                kpi_data['value'] = round(final_val, 1)
                kpi_data['unit'] = 'billion VND' 
            
            else:
                if any(x in u_lower for x in ["lần", "times", "x"]):
                    kpi_data['value'] = round(val, 1)
                    kpi_data['unit'] = 'x'
                else:
                    kpi_data['value'] = val
                    kpi_data['unit'] = raw_unit
                    
        for k in keys_to_delete:
            del kpis[k]

    return normalized_data