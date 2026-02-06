import streamlit as st
import re
import json
import pandas as pd

# ==========================================
# 1. 수식 오타/문법 검수 클래스 (MathFormulaInspector)
# ==========================================
class MathFormulaInspector:
    def __init__(self):
        self.log = []

    def get_context(self, text, start, end, window=15):
        s = max(0, start - window)
        e = min(len(text), end + window)
        context = text[s:e].replace('\n', ' ')
        return f"...{context}..."

    def check_parentheses(self, formula, offset, full_text):
        """괄호 짝 검사 (LaTeX의 \{, \}는 제외하고 구조적 괄호만 검사)"""
        temp_formula = formula.replace(r'\{', '..').replace(r'\}', '..')
        
        stack = []
        mapping = {')': '(', '}': '{', ']': '['}
        
        for i, char in enumerate(temp_formula):
            if char in mapping.values(): # 여는 괄호
                stack.append((char, i))
            elif char in mapping.keys(): # 닫는 괄호
                if not stack or stack[-1][0] != mapping[char]:
                    context = self.get_context(full_text, offset+i, offset+i+1)
                    self.log.append({
                        "유형": "괄호 오류",
                        "문맥": context,
                        "대상": f"${formula}$",
                        "내용": f"닫는 괄호 '{char}'의 짝이 맞지 않음"
                    })
                    if stack: stack.pop()
                else:
                    stack.pop()
        
        if stack:
            for char, i in stack:
                context = self.get_context(full_text, offset+i, offset+i+1)
                self.log.append({
                    "유형": "괄호 오류",
                    "문맥": context,
                    "대상": f"${formula}$",
                    "내용": f"여는 괄호 '{char}'가 닫히지 않음"
                })

    def check_bad_patterns(self, formula, offset, full_text):
        """금지된 패턴 검사"""
        # 1. 곱하기 기호 * 사용
        if re.search(r'\d\s*\*\s*\d', formula):
            self.log.append({
                "유형": "표기 오류",
                "문맥": self.get_context(full_text, offset, offset+len(formula)),
                "대상": f"${formula}$",
                "내용": "곱하기 기호 '*' 사용됨 ($\\times$ 권장)"
            })
        
        # 2. 부등호 <=, >= 사용
        if '<=' in formula or '>=' in formula:
             self.log.append({
                "유형": "표기 오류",
                "문맥": self.get_context(full_text, offset, offset+len(formula)),
                "대상": f"${formula}$",
                "내용": "부등호 '<=', '>=' 사용됨 ($\\le, \\ge$ 권장)"
            })
             
        # 3. \frac 인자 누락 의심
        if '\\frac' in formula and not re.search(r'\\frac\s*\{', formula):
             self.log.append({
                "유형": "문법 오류",
                "문맥": self.get_context(full_text, offset, offset+len(formula)),
                "대상": f"${formula}$",
                "내용": "\\frac 명령어 인자 누락 의심"
            })

    def check_arithmetic(self, text):
        """단순 정수 사칙연산 검증"""
        equation_pattern = re.compile(r'(?<![\.\d])(\d+[\s\+\-\*\/]+\d+\s*=\s*\d+)(?![\.\d])')
        matches = equation_pattern.finditer(text)
        
        for m in matches:
            eq_str = m.group(1)
            try:
                lhs, rhs = eq_str.split('=')
                if not re.match(r'^[\d\s\+\-\*\/]+$', lhs): continue
                
                calculated = eval(lhs)
                target = int(rhs)
                
                if calculated != target:
                    self.log.append({
                        "유형": "계산 오류",
                        "문맥": self.get_context(text, m.start(), m.end()),
                        "대상": eq_str,
                        "내용": f"계산 불일치 (좌변 결과: {calculated})"
                    })
            except:
                pass

    def run(self, text):
        self.log = []
        # 1. LaTeX 수식 내부 검사
        latex_pattern = re.compile(r'\$([^\$]+)\$')
        for m in latex_pattern.finditer(text):
            formula = m.group(1)
            start_idx = m.start()
            self.check_parentheses(formula, start_idx, text)
            self.check_bad_patterns(formula, start_idx, text)
            
        # 2. 산술 연산 검사
        self.check_arithmetic(text)
        return self.log

# ==========================================
# 2. 수식 조사 호응 교정 클래스 (JosaCorrector)
# ==========================================
class JosaCorrector:
    def __init__(self):
        self.log = []
        self.batchim_dict = self._init_batchim_dict()
        self.unit_batchim_dict = self._init_unit_batchim_dict()
        self.particle_pairs = self._init_particle_pairs()
        
        self.protected_words = [
            '이다', '입니다', '며', '이고', '이나', '이면서', '이지만', '이어서',
            '이때', '이어야', '가지',
            '이면', '이므로', # '이므로' 보호 추가
            '이상', '이하', '이내', '이외', '미만', '초과',
            '이은', '이을', '이어', '이으므로', '이어진', '이루어진', '이루는', '이동', '이용',
            '없는', '있는', '없고', '있고', '없이', '있어', '없어'
        ]

    def _init_batchim_dict(self):
        # [업데이트] n, m, l, r 등 받침 있는 알파벳 추가
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
            ('이므로', '므로'),
            ('이다', '이다'), ('입니다', '입니다'),
            ('이며', '이며'), ('이고', '이고'), ('이나', '이나'),
            ('이면서', '이면서'), ('이지만', '이지만'), ('이어서', '이어서'),
            ('이때', '이때'), ('이어야 하므로', '이어야 하므로'),
            ('가지', '가지'),
            ('이라서', '라서'), ('이라고', '라고'), ('이라', '라'), ('이면', '면'), 
            ('은', '는'), ('이', '가'), ('을', '를'), ('과', '와'), ('으로', '로'), ('을', '울')
        ]

    def get_balanced_content(self, text):
        """중괄호 짝을 맞춰 내부 내용을 추출 (재귀 분석용)"""
        stack = 0
        first_open = text.find('{')
        if first_open == -1: return text, ""
        
        for i in range(first_open, len(text)):
            if text[i] == '{': stack += 1
            elif text[i] == '}':
                stack -= 1
                if stack == 0:
                    return text[first_open+1:i], text[i+1:]
        return text, ""

    def find_target(self, formula_str):
        """
        [로직 개선] 기존의 복잡한 문자열 치환 대신 재귀적 구조 분석 사용
        분수(\frac)의 경우 분자를 찾아 들어가고, 거듭제곱(^)을 인식함.
        """
        formula_str = formula_str.strip()
        
        # 1. 분수 처리: \frac{분자}{분모} -> 한국어는 "분모 분의 분자"로 읽으므로 '분자'가 타겟
        if '\\frac' in formula_str:
            last_frac = list(re.finditer(r'\\frac', formula_str))
            if last_frac:
                content = formula_str[last_frac[-1].end():].strip()
                numerator, _ = self.get_balanced_content(content)
                # 재귀 호출: 분자 안이 또 수식일 수 있으므로 다시 분석
                return self.find_target(numerator) 

        # 2. 거듭제곱 처리: ^... 로 끝나면 "제곱"
        if re.search(r'\^\{?[^{}]+\}?$', formula_str):
            if "C" in formula_str: return "여집합"
            return "제곱"

        # 3. 각도 처리
        if r'\degree' in formula_str or r'^\circ' in formula_str: return "도"

        # 4. 단위 처리 (\mathrm{...})
        mathrm_match = re.search(r'\\mathrm\{([a-zA-Z]+)\}', formula_str)
        if mathrm_match:
            unit = mathrm_match.group(1)
            if unit in ['m', 'cm', 'mm', 'km']: return "미터"
            return f"UNIT:{unit}"

        # 5. 일반 텍스트 추출 (LaTeX 명령어 제거)
        clean = re.sub(r'\\[a-zA-Z]+', '', formula_str)
        clean = re.sub(r'[\{\}\(\)\s\^\[\]]', '', clean)
        
        return clean[-1] if clean else ""

    def get_correct_p(self, target, original_p):
        for word in self.protected_words:
            if original_p.startswith(word): return original_p

        has_batchim = False
        if target.startswith("UNIT:"):
            real_unit = target.split(":")[1]
            has_batchim = self.unit_batchim_dict.get(real_unit, False)
        elif target == "미터": has_batchim = False
        elif target == "제곱": has_batchim = True
        elif target == "여집합": has_batchim = True
        elif target == "도": has_batchim = False
        else:
            if target in self.batchim_dict: has_batchim = self.batchim_dict[target]
            elif '가' <= target <= '힣': has_batchim = (ord(target) - 0xAC00) % 28 > 0
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

    def get_context(self, text, start, end, window=10):
        s = max(0, start - window)
        e = min(len(text), end + window)
        context = text[s:e].replace('\n', ' ')
        return f"...{context}..."

    def run(self, raw_input):
        self.log = [] 
        try:
            if isinstance(raw_input, dict): input_data = raw_input
            else: input_data = json.loads(raw_input)
            target_text = input_data.get("result", raw_input) if isinstance(input_data, dict) else str(raw_input)
        except:
            target_text = str(raw_input)

        # [핵심 수정] 정규표현식: 수식($...$)과 조사 사이의 줄바꿈(\\), 엔터(\n), 공백을 모두 허용
        pattern = r'\$([^\$]+)\$([\s\\n]*)([가-힣]+)'

        def replacer(match):
            formula = match.group(1)
            bridge = match.group(2) # 줄바꿈, 공백 등
            particle = match.group(3)
            
            match_start = match.start()
            match_end = match.end()

            # 보호 단어 1차 필터
            for word in self.protected_words:
                if particle.startswith(word): return match.group(0)
                
            target = self.find_target(formula)
            if not target: return match.group(0)

            correct_p = self.get_correct_p(target, particle)
            
            if particle != correct_p:
                human_readable = self.clean_latex_for_human(formula)
                context = self.get_context(target_text, match_start, match_end)
                self.log.append({
                    "문맥": context,
                    "대상": human_readable,
                    "원문": particle,
                    "수정": correct_p,
                    "사유": "받침 호응 오류"
                })
                return f"${formula}${bridge}{correct_p}"

            return match.group(0)

        fixed_text = re.sub(pattern, replacer, target_text, flags=re.DOTALL)
        return fixed_text, self.log

# ==========================================
# 3. 한글 맞춤법/오타/조사 교정 클래스 (SpellingCorrector)
# ==========================================
class SpellingCorrector:
    def __init__(self):
        self.log = []
        self.typo_dict = {
            "자리수": "자릿수",
            "최대값": "최댓값", "최소값": "최솟값", "극대값": "극댓값", "극소값": "극솟값",
            "절대값": "절댓값", "근사값": "근삿값", "대표값": "대푯값", "함수값": "함숫값",
            "꼭지점": "꼭짓점", "촛점": "초점", "갯수": "개수", "나누기": "나눗셈",
            "않되": "안 되", "않돼": "안 돼", "않된다": "안 된다", "문안": "무난",
            "금새": "금세", "역활": "역할", "제작년": "재작년", "어떻해": "어떡해",
            "몇일": "며칠", "들어나다": "드러나다", "가르키다": "가리키다", "맞추다": "맞히다"
        }
        self.korean_particle_pairs = [
            ('은', '는'), ('이', '가'), ('을', '를'), ('과', '와'), ('으로', '로')
        ]
        
        self.exceptions = {
            '증가', '추가', '결과', '효과', '초과', '교과', '부과', '사과', '투과',
            '평가', '원가', '정가', '단가', '시가',
            '사이', '차이', '나이', '아이', '오이', '놀이',
            '경로', '진로', '선로', '항로',
            '없는', '있는', '갖는', '맞는', '맡는', '웃는', '씻는', '깎는', '볶는', '않는',
            '이은', '이을', '이어', '이어서', '깊은', '높은', '작은', '좁은',
            '인가', '는가', '은가', '던가', '나', '가' 
        }

    def has_batchim(self, char):
        if '가' <= char <= '힣':
            return (ord(char) - 0xAC00) % 28 > 0
        return False

    def is_rieul_batchim(self, char):
        if '가' <= char <= '힣':
            return (ord(char) - 0xAC00) % 28 == 8
        return False

    def get_context(self, text, start, end, window=10):
        s = max(0, start - window)
        e = min(len(text), end + window)
        context = text[s:e].replace('\n', ' ')
        return f"...{context}..."

    def run(self, text):
        self.log = []
        parts = re.split(r'(\$[^\$]+\$)', text)
        final_parts = []
        
        for i, part in enumerate(parts):
            if i % 2 == 1: 
                final_parts.append(part)
                continue
            
            current_text = part
            
            for wrong, correct in self.typo_dict.items():
                if wrong in current_text:
                    for m in re.finditer(re.escape(wrong), current_text):
                        context = self.get_context(current_text, m.start(), m.end())
                        self.log.append({
                            "문맥": context,
                            "대상": wrong,
                            "원문": wrong,
                            "수정": correct,
                            "사유": "맞춤법/표준어 오류"
                        })
                    current_text = current_text.replace(wrong, correct)
            
            pattern = r'([가-힣㉠-㉭])(은|는|이|가|을|를|과|와|으로|로)(?![가-힣])'
            
            def josa_replacer(match):
                full_word = match.group(0)
                if full_word in self.exceptions:
                    return full_word
                
                noun_char = match.group(1)
                josa = match.group(2)
                
                if '가' <= noun_char <= '힣':
                    has_bat = self.has_batchim(noun_char)
                    is_rieul = self.is_rieul_batchim(noun_char)
                else: 
                    has_bat = True
                    is_rieul = (noun_char == '㉣')

                correct_josa = josa
                for bat_o, bat_x in self.korean_particle_pairs:
                    if josa == bat_o or josa == bat_x:
                        if bat_o == '으로':
                            if not has_bat or is_rieul: correct_josa = '로'
                            else: correct_josa = '으로'
                        else:
                            correct_josa = bat_o if has_bat else bat_x
                        break
                
                if josa != correct_josa:
                    context = self.get_context(current_text, match.start(), match.end())
                    self.log.append({
                        "문맥": context,
                        "대상": full_word,
                        "원문": josa,
                        "수정": correct_josa,
                        "사유": "조사 호응 오류"
                    })
                    return f"{noun_char}{correct_josa}"
                return match.group(0)

            current_text = re.sub(pattern, josa_replacer, current_text)
            final_parts.append(current_text)
            
        return "".join(final_parts), self.log

# ==========================================
# 4. 메인 UI (Streamlit)
# ==========================================
st.set_page_config(page_title="수학 문제 통합 교정기", layout="wide")

st.title("✨ 수학 문제 통합 교정기 (v2.1)")
st.markdown("수식 오류, 수식 조사, 한글 맞춤법을 통합적으로 검사합니다.")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("입력 (Input)")
    input_val = st.text_area("텍스트를 입력하세요:", height=600, 
                             placeholder="예: $n$ 므로 (조사 오류), 자리수 (맞춤법 오류)")

with col2:
    st.subheader("검수 리포트 (Report)")
    
    if input_val:
        # 1. 수식 오타 검수
        math_inspector = MathFormulaInspector()
        math_logs = math_inspector.run(input_val)
        
        # 2. 조사 교정 실행
        josa_corrector = JosaCorrector()
        temp_text, josa_logs = josa_corrector.run(input_val)
        
        # 3. 맞춤법 교정 실행
        spell_corrector = SpellingCorrector()
        final_text, spell_logs = spell_corrector.run(temp_text)
        
        # --- 3개의 탭으로 분리하여 보고 ---
        tab1, tab2, tab3 = st.tabs(["🧮 수식 오류 검수", "🔍 수식 조사 검수", "📝 한글/기호 검수"])
        
        # 탭 1: 수식 오류
        with tab1:
            if math_logs:
                st.error(f"수식/계산 오류 발견: {len(math_logs)}건")
                st.caption("수식의 괄호, 금지된 기호(*, <=), 단순 계산 오류를 확인합니다.")
                df_math = pd.DataFrame(math_logs)
                st.dataframe(df_math[['유형', '문맥', '대상', '내용']], use_container_width=True, hide_index=True)
            else:
                st.success("수식 문법 및 계산 오류가 발견되지 않았습니다.")

        # 탭 2: 수식 조사 검수
        with tab2:
            if josa_logs:
                st.warning(f"수식 조사 오류 발견: {len(josa_logs)}건")
                st.caption("LaTeX 수식 뒤에 오는 조사의 호응을 확인합니다.")
                df_josa = pd.DataFrame(josa_logs)
                st.dataframe(df_josa[['문맥', '대상', '원문', '수정', '사유']], use_container_width=True, hide_index=True)
            else:
                st.success("수식 조사가 완벽합니다.")

        # 탭 3: 한글/기호 검수
        with tab3:
            if spell_logs:
                st.warning(f"한글/기호 오류 발견: {len(spell_logs)}건")
                st.caption("일반 텍스트의 맞춤법 및 조사 호응을 확인합니다.")
                df_spell = pd.DataFrame(spell_logs)
                st.dataframe(df_spell[['문맥', '대상', '원문', '수정', '사유']], use_container_width=True, hide_index=True)
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