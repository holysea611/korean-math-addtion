import streamlit as st
import re
import json
import pandas as pd

# ==========================================
# 1. 수식 조사 호응 교정 클래스
# ==========================================
class JosaCorrector:
    def __init__(self):
        self.log = []
        self.batchim_dict = self._init_batchim_dict()
        self.unit_batchim_dict = self._init_unit_batchim_dict()
        self.particle_pairs = self._init_particle_pairs()
        
        # 보호 단어 목록 (조사로 오인되지 않도록)
        self.protected_words = [
            '이다', '입니다', '이므로', '이며', '이고', '이나', '이면서', '이지만', '이어서',
            '이때', '이어야', '가지',
            '이상', '이하', '이내', '이외', '미만', '초과'
        ]

    def _init_batchim_dict(self):
        d = {
            '0': True, '1': True, '3': True, '6': True, '7': True, '8': True, '10': True,
            'l': True, 'm': True, 'n': True, 'r': True, 
            'L': True, 'M': True, 'N': True, 'R': True,
            '제곱': True, '여집합': True, '바': False
        }
        for c in "ㄱㄴㄷㄹㅁㅂㅅㅇㅈㅊㅋㅌㅍㅎ": d[c] = True
        for ch in '2459AaBbCcDdEeFfGgHhIiJjKkOoPpQqSsTtUuVvWwXxeYyZz':
            if ch not in d: d[ch] = False
        return d

    def _init_unit_batchim_dict(self):
        return {
            'm': False, 'cm': False, 'mm': False, 'km': False,
            'g': True, 'kg': True, 'mg': True,
            'l': False, 'L': False, 'mL': False,
            'A': False, 'V': False, 'W': False, 'Hz': False,
            'deg': False, 'degree': False
        }

    def _init_particle_pairs(self):
        return [
            ('이다', '이다'), ('입니다', '입니다'),
            ('이므로', '이므로'), ('이며', '이며'), ('이고', '이고'), ('이나', '이나'),
            ('이면서', '이면서'), ('이지만', '이지만'), ('이어서', '이어서'),
            ('이때', '이때'), ('이어야 하므로', '이어야 하므로'),
            ('가지', '가지'),
            ('이라서', '라서'), ('이라고', '라고'), ('이라', '라'), ('이면', '면'), 
            ('은', '는'), ('이', '가'), ('을', '를'), ('과', '와'), ('으로', '로'), ('을', '울')
        ]

    def get_balanced(self, text, start_idx):
        if start_idx == -1 or start_idx >= len(text): return None, start_idx
        count = 0
        for i in range(start_idx, len(text)):
            if text[i] == '{': count += 1
            elif text[i] == '}': count -= 1
            if count == 0: return text[start_idx+1:i], i + 1
        return None, start_idx

    def simplify_formula(self, latex_str):
        current = latex_str.replace(r'\left', '').replace(r'\right', '')
        prev_str = ""
        while prev_str != current:
            prev_str = current
            if '\\frac' in current:
                idx = current.find('\\frac')
                num, end_num = self.get_balanced(current, current.find('{', idx))
                _, end_den = self.get_balanced(current, current.find('{', end_num))
                if num is not None:
                    current = current[:idx] + num + current[end_den:]
                    continue
            if '\\sqrt' in current:
                idx = current.find('\\sqrt')
                if idx + 5 < len(current) and current[idx+5] == '[':
                    close_bracket = current.find(']', idx)
                    if close_bracket != -1:
                        current = current[:idx+5] + current[close_bracket+1:]
                        continue
            stripped = current.strip()
            if stripped.startswith('{') and stripped.endswith('}'):
                content, end = self.get_balanced(stripped, 0)
                if end == len(stripped):
                    current = content
                    continue
        return current

    def find_target(self, formula_str):
        simplified = self.simplify_formula(formula_str)
        clean = re.sub(r'\s+', '', simplified)
        masked_text = clean
        braces_content = []
        while True:
            start = masked_text.find('{')
            if start == -1: break
            content, end_idx = self.get_balanced(masked_text, start)
            if content is None: break
            placeholder = f"@BRACE{len(braces_content)}@"
            braces_content.append(content)
            masked_text = masked_text[:start] + placeholder + masked_text[end_idx:]

        split_pattern = (r'=|\\approx|\\ne|>|<|\\ge|\\le|\\times|\\div|'
                         r'(?<!\^)\+|(?<!\^)-|\\cdot|'
                         r'\\cap|\\cup|\\setminus|\\subset|\\subseteq|\\in|\\ni')
        parts = re.split(split_pattern, masked_text)
        final_term = parts[-1] if parts else masked_text

        while "@BRACE" in final_term:
            for i, content in enumerate(braces_content):
                placeholder = f"@BRACE{i}@"
                if placeholder in final_term:
                    final_term = final_term.replace(placeholder, "{" + content + "}")

        if r'\degree' in final_term or r'^\circ' in final_term: return "도"
        if "^" in final_term:
            if "C" in final_term: return "여집합"
            base_part = final_term.split('^')[0]
            mathrm_match = re.search(r'\\mathrm\{([a-zA-Z]+)\}', base_part)
            if mathrm_match:
                unit_content = mathrm_match.group(1)
                if unit_content in ['m', 'cm', 'mm', 'km']: return "미터"
            return "제곱"

        mathrm_match = re.search(r'\\mathrm\{([a-zA-Z]+)\}', final_term)
        if mathrm_match: return f"UNIT:{mathrm_match.group(1)}"

        if final_term.endswith(')'):
             m = re.search(r'([가-힣a-zA-Z0-9])\)+$', final_term)
             if m: return m.group(1)

        text_only = re.sub(r'\\[a-zA-Z]+|[{}]|[()\[\]]|[\.,]', '', final_term)
        text_only = text_only.replace('\\', '').strip() 
        return text_only[-1] if text_only else ""

    def get_correct_p(self, target, original_p):
        for word in self.protected_words:
            if original_p.startswith(word): return original_p

        if not target.startswith("UNIT:") and len(target) == 1 and re.match(r'[a-zA-Z0-9]', target):
            is_noun_mask = False
            if original_p.startswith('가면'):
                after_mask = original_p[2:]
                if after_mask and after_mask[0] in ['을', '이', '은', '과', '의', '로']: is_noun_mask = True
                if not is_noun_mask and original_p.startswith(('이면', '면', '가면')):
                    suffix = original_p[2:] if original_p.startswith('가면') else original_p[len('이면' if original_p.startswith('이면') else '면'):]
                    return '이면' + suffix

        has_batchim = False
        if target.startswith("UNIT:"):
            real_unit = target.split(":")[1]
            has_batchim = self.unit_batchim_dict.get(real_unit, False)
        elif target == "미터": has_batchim = False
        else:
            if target in self.batchim_dict: has_batchim = self.batchim_dict[target]
            elif len(target) == 1 and '가' <= target <= '힣': has_batchim = (ord(target) - 0xAC00) % 28 > 0
            elif len(target) > 1:
                last = target[-1]
                has_batchim = (ord(last) - 0xAC00) % 28 > 0 if '가' <= last <= '힣' else self.batchim_dict.get(last, False)
            else: has_batchim = self.batchim_dict.get(target, False)

        is_rieul = target in ['1', '7', '8', 'L', 'R', 'l', 'r', 'ㄹ']
        
        for has_b, no_b in self.particle_pairs:
            if original_p.startswith(has_b) or original_p.startswith(no_b):
                if has_b == '으로':
                    stem = '으로' if (has_batchim and not is_rieul) else '로'
                else:
                    stem = has_b if has_batchim else no_b
                return stem + original_p[len(has_b if original_p.startswith(has_b) else no_b):]
        return original_p

    def clean_latex_for_human(self, latex):
        text = re.sub(r'\\(left|right|mathrm|text|bf|it)', '', latex)
        text = text.replace('{', '').replace('}', '').replace('\\', '')
        return text.strip()

    def run(self, raw_input):
        self.log = [] 
        try:
            if isinstance(raw_input, dict): input_data = raw_input
            else: input_data = json.loads(raw_input)
            target_text = input_data.get("result", raw_input) if isinstance(input_data, dict) else str(raw_input)
        except:
            target_text = str(raw_input)

        def replacer(match):
            pre, s1, formula, s2, particle = match.groups()
            p_match = re.search(r'[가-힣]+', particle)
            
            if not p_match:
                if '.' in particle:
                    new_particle = particle.replace('.', '')
                    human_readable = self.clean_latex_for_human(formula)
                    self.log.append({
                        "대상": human_readable,
                        "원문": particle,
                        "수정": new_particle,
                        "사유": "불필요한 마침표 제거"
                    })
                    return f"{pre}{s1}${formula}${s2}{new_particle}"
                return match.group(0)

            p_start = p_match.start()
            original_p = p_match.group()
            remaining_particle = particle[p_start:]
            
            for word in self.protected_words:
                if remaining_particle.startswith(word): return match.group(0)
                
            target = self.find_target(formula)
            correct_p = self.get_correct_p(target, original_p)
            
            if original_p != correct_p:
                human_readable = self.clean_latex_for_human(formula)
                self.log.append({
                    "대상": human_readable,
                    "원문": original_p,
                    "수정": correct_p,
                    "사유": "받침 호응 오류"
                })

            return f"{pre}{s1}${formula}${s2}{particle[:p_start]}{correct_p}{particle[p_match.end():]}"

        pattern = r'([^$]*?)(\s*)\$([^\$]+)\$(\s*)([\s,]*[가-힣\s\.\?\!]+)'
        fixed_text = re.sub(pattern, replacer, target_text, flags=re.DOTALL)
        return fixed_text, self.log

# ==========================================
# 2. 한글 맞춤법/오타 교정 클래스 (사전 기반)
# ==========================================
class SpellingCorrector:
    def __init__(self):
        self.log = []
        # 수학/일반 오타 사전 (필요시 여기에 계속 추가하면 됩니다)
        self.typo_dict = {
            # [수학 용어 - 사이시옷/표준어]
            "최대값": "최댓값",
            "최소값": "최솟값",
            "극대값": "극댓값",
            "극소값": "극솟값",
            "절대값": "절댓값",
            "근사값": "근삿값",
            "대표값": "대푯값",
            "함수값": "함숫값",
            "꼭지점": "꼭짓점",
            "촛점": "초점",
            "갯수": "개수",
            "나누기": "나눗셈", # 문맥에 따라 다르지만 보통 명사형은 나눗셈
            
            # [자주 틀리는 일반 맞춤법]
            "않되": "안 되",
            "않돼": "안 돼",
            "않된다": "안 된다",
            "문안": "무난",
            "금새": "금세",
            "역활": "역할",
            "제작년": "재작년",
            "어떻해": "어떡해",
            "몇일": "며칠",
            "들어나다": "드러나다",
            "가르키다": "가리키다", # 방향을 가리키다
            "맞추다": "맞히다", # 정답을 맞히다 (문맥 의존적이나 수학에선 맞히다가 많음)
            "십오": "15", # (선택사항) 한글 숫자를 아라비아로? 일단 예시
        }

    def run(self, text):
        self.log = []
        
        # LaTeX 수식($...$)을 제외하고 한글 텍스트만 분리해서 검사하기 위해 split
        # 짝수 인덱스: 일반 텍스트, 홀수 인덱스: 수식
        parts = re.split(r'(\$[^\$]+\$)', text)
        
        corrected_parts = []
        for i, part in enumerate(parts):
            # 수식 부분($...$)은 건드리지 않음
            if i % 2 == 1:
                corrected_parts.append(part)
                continue
            
            # 일반 텍스트 부분에서 오타 검사
            current_text = part
            for wrong, correct in self.typo_dict.items():
                if wrong in current_text:
                    # 단순 replace가 아니라 단어 경계를 고려하면 좋지만, 
                    # 한국어는 조사가 붙으므로 단순 포함 여부로 교체하되 로그 남김
                    # (정확도를 위해선 형태소 분석기가 필요하지만 여기선 사전매칭 방식 사용)
                    
                    # 오타가 발견될 때마다 교체
                    if wrong in current_text:
                        cnt = current_text.count(wrong)
                        current_text = current_text.replace(wrong, correct)
                        
                        # 로그 기록 (중복 방지)
                        self.log.append({
                            "대상": wrong,
                            "원문": wrong,
                            "수정": correct,
                            "사유": "맞춤법/표준어 오류"
                        })
            
            corrected_parts.append(current_text)
            
        return "".join(corrected_parts), self.log

# ==========================================
# 3. 메인 UI (Streamlit)
# ==========================================
st.set_page_config(page_title="수학 문제 통합 교정기", layout="wide")

st.title("✨ 수학 문제 통합 교정기")
st.markdown("""
**1. 수식 조사 호응:** LaTeX 수식 뒤의 조사(은/는, 이/가 등)를 교정합니다.  
**2. 한글 맞춤법:** 수학 용어(최댓값, 꼭짓점 등) 및 자주 틀리는 오타를 교정합니다.
""")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("입력 (Input)")
    input_val = st.text_area("텍스트를 입력하세요:", height=600, 
                             placeholder="예: $Q\\left(n\\right)$이라 하고, 최대값과 갯수를 구하시오.")

with col2:
    st.subheader("검수 리포트 (Report)")
    
    if input_val:
        # 1. 조사 교정 실행
        josa_corrector = JosaCorrector()
        temp_text, josa_logs = josa_corrector.run(input_val)
        
        # 2. 맞춤법 교정 실행 (조사 교정된 텍스트를 입력으로 사용)
        spell_corrector = SpellingCorrector()
        final_text, spell_logs = spell_corrector.run(temp_text)
        
        # --- 리포트 출력 ---
        
        # 탭으로 구분하여 보여주기
        tab1, tab2 = st.tabs(["🔍 조사 호응 검수", "📝 맞춤법/오타 검수"])
        
        with tab1:
            if josa_logs:
                st.error(f"조사 호응 오류: {len(josa_logs)}건")
                df_josa = pd.DataFrame(josa_logs)
                st.dataframe(df_josa, use_container_width=True, hide_index=True)
            else:
                st.success("조사 호응이 완벽합니다.")
                
        with tab2:
            if spell_logs:
                st.warning(f"맞춤법/오타 의심: {len(spell_logs)}건")
                df_spell = pd.DataFrame(spell_logs)
                st.dataframe(df_spell, use_container_width=True, hide_index=True)
            else:
                st.success("발견된 오타가 없습니다.")

        st.markdown("---")
        st.subheader("최종 결과물 (Result)")
        st.text_area("교정된 텍스트", value=final_text, height=300)
        
        st.download_button(
            label="💾 결과 파일 다운로드",
            data=final_text,
            file_name="corrected_result.txt",
            mime="text/plain"
        )
    else:
        st.info("왼쪽에 내용을 입력하면 자동으로 검사를 시작합니다.")