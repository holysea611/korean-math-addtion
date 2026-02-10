import streamlit as st
import re
import json
import pandas as pd

# ==========================================
# 1. 수식 조사 호응 교정 클래스 (LaTeX 대상)
# ==========================================
class JosaCorrector:
    def __init__(self):
        self.log = []
        self.batchim_dict = self._init_batchim_dict()
        self.unit_batchim_dict = self._init_unit_batchim_dict()
        self.particle_pairs = self._init_particle_pairs()
        
        # [수식 보호] 조사가 아닌 단어(동사/형용사 활용형) 보호 목록
        self.protected_words = [
            '이다', '입니다', '이므로', '이며', '이고', '이나', '이면서', '이지만', '이어서',
            '이때', '이어야', '가지',
            '이면', 
            '이상', '이하', '이내', '이외', '미만', '초과',
            '이은', '이을', '이어', '이으므로', '이어진', '이루어진', '이루는', '이동', '이용',
            '없는', '있는', '없고', '있고', '없이', '있어', '없어'
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
            'deg': False, 'degree': False,
            'N': True  # 뉴턴(N)은 받침 있음
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
        # 1. \left, \right 제거
        current = latex_str.replace(r'\left', '').replace(r'\right', '')
        
        prev_str = ""
        while prev_str != current:
            prev_str = current
            # 2. \frac{A}{B} -> A (한국어 읽기 순서: B분의 A -> 끝소리는 A)
            if '\\frac' in current:
                idx = current.find('\\frac')
                # 분자 찾기
                num_start = current.find('{', idx)
                num, end_num = self.get_balanced(current, num_start)
                # 분모 찾기
                den_start = current.find('{', end_num)
                _, end_den = self.get_balanced(current, den_start)
                
                if num is not None:
                    # 전체 \frac{...}{...}를 분자(num)로 대체
                    current = current[:idx] + num + current[end_den:]
                    continue
            
            # 3. \sqrt, \sqrt[...] 제거
            if '\\sqrt' in current:
                idx = current.find('\\sqrt')
                if idx + 5 < len(current) and current[idx+5] == '[':
                    close_bracket = current.find(']', idx)
                    if close_bracket != -1:
                        current = current[:idx+5] + current[close_bracket+1:]
                        continue
            
            # 4. 바깥쪽 중괄호 제거 ({...} -> ...)
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
        
        # 중괄호 내용 보호
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

        # 연산자로 분리하여 마지막 항 추출
        split_pattern = (r'=|\\approx|\\ne|>|<|\\ge|\\le|\\times|\\div|'
                         r'(?<!\^)\+|(?<!\^)-|\\cdot|'
                         r'\\cap|\\cup|\\setminus|\\subset|\\subseteq|\\in|\\ni')
        parts = re.split(split_pattern, masked_text)
        final_term = parts[-1] if parts else masked_text

        # 보호된 내용 복원
        while "@BRACE" in final_term:
            for i, content in enumerate(braces_content):
                placeholder = f"@BRACE{i}@"
                if placeholder in final_term:
                    final_term = final_term.replace(placeholder, "{" + content + "}")

        # 끝부분 정리 (역슬래시 등)
        final_term = final_term.rstrip('\\').strip()

        # 1. 도(degree) 처리
        if r'\degree' in final_term or r'^\circ' in final_term: return "도"
        
        # 2. 지수(^) 처리
        if "^" in final_term:
            if "C" in final_term: return "여집합"
            base_part = final_term.split('^')[0]
            # 단위 확인
            mathrm_match = re.search(r'\\mathrm\{([a-zA-Z]+)\}', base_part)
            if mathrm_match:
                unit_content = mathrm_match.group(1)
                if unit_content in ['m', 'cm', 'mm', 'km']: return "미터"
            return "제곱"

        # 3. 괄호로 끝나는 경우 (함수 등) -> 내부의 마지막 글자 확인
        if final_term.endswith(')'):
             m = re.search(r'([가-힣a-zA-Z0-9])\)+$', final_term)
             if m: return m.group(1)

        # 4. 단위(mathrm) 처리
        mathrm_match = re.search(r'\\mathrm\{([a-zA-Z]+)\}', final_term)
        if mathrm_match: return f"UNIT:{mathrm_match.group(1)}"

        # 5. 텍스트만 추출 (명령어 제거)
        # \ln, \log, \sin 등 명령어 및 특수문자 제거
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

        def replacer(match):
            # 정규식 그룹: (prefix, space, delimiter, formula, gap, particle)
            # gap: 수식 뒤의 공백, 줄바꿈(\\\\), 쿼드(\qquad), 콤마(\,) 등
            pre, s1, delim, formula, gap, particle = match.groups()
            
            # [중요] JSON 등에서 이스케이프된 역슬래시(\\)를 정규화(\)
            formula_clean = formula.replace('\\\\', '\\')
            
            p_match = re.search(r'[가-힣]+', particle)
            match_start = match.start()
            match_end = match.end()

            if not p_match:
                if '.' in particle:
                    new_particle = particle.replace('.', '')
                    human_readable = self.clean_latex_for_human(formula_clean)
                    context = self.get_context(target_text, match_start, match_end)
                    self.log.append({
                        "문맥": context,
                        "대상": human_readable,
                        "원문": particle,
                        "수정": new_particle,
                        "사유": "불필요한 마침표 제거"
                    })
                    # gap(s2)을 포함하여 반환
                    return f"{pre}{s1}{delim}{formula}{delim}{gap}{new_particle}"
                return match.group(0)

            p_start = p_match.start()
            original_p = p_match.group()
            remaining_particle = particle[p_start:]
            
            for word in self.protected_words:
                if remaining_particle.startswith(word): return match.group(0)
                
            target = self.find_target(formula_clean)
            correct_p = self.get_correct_p(target, original_p)
            
            if original_p != correct_p:
                human_readable = self.clean_latex_for_human(formula_clean)
                context = self.get_context(target_text, match_start, match_end)
                self.log.append({
                    "문맥": context,
                    "대상": human_readable,
                    "원문": original_p,
                    "수정": correct_p,
                    "사유": "받침 호응 오류"
                })

            # gap을 유지한 채로 조사만 교체
            return f"{pre}{s1}{delim}{formula}{delim}{gap}{particle[:p_start]}{correct_p}{particle[p_match.end():]}"

        # [수정] 수식($...$)과 한글 사이에 LaTeX 줄바꿈(\\\\), 공백 명령어(\qquad, \quad, \,) 등이 있어도 매칭되도록 개선
        # Group 5 (Gap): 공백(\s), 콤마(,), 또는 역슬래시(\)로 시작하는 명령어들(\\, \qquad 등)을 허용
        pattern = r'([^$]*?)(\s*)(\$+)([^\$]+)\3((?:[\s,]|\\(?:\\|qquad|quad|[,;!]))*)([가-힣\s\.\?\!]+)'
        
        fixed_text = re.sub(pattern, replacer, target_text, flags=re.DOTALL)
        return fixed_text, self.log

# ==========================================
# 2. 한글 맞춤법/오타/조사 교정 클래스
# ==========================================
class SpellingCorrector:
    def __init__(self):
        self.log = []
        self.typo_dict = {
            "자리수": "자릿수", "최대값": "최댓값", "최소값": "최솟값", "극대값": "극댓값", "극소값": "극솟값",
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
# 3. 메인 UI (Streamlit)
# ==========================================
st.set_page_config(page_title="수학 문제 통합 교정기", layout="wide")

st.title("✨ 수학 문제 통합 교정기")
st.markdown("""
**1. 수식 조사 호응:** LaTeX 수식 뒤의 조사를 교정합니다. (쉼표 뒤 '이면' 유지)  
**2. 한글 맞춤법:** '몇 개인가?' 처럼 의문형 어미를 조사로 오인하는 오류를 수정했습니다.
""")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("입력 (Input)")
    input_val = st.text_area("텍스트를 입력하세요:", height=600, 
                             placeholder="예: $a<b$, 이면... / 모두 몇 개인가?")

with col2:
    st.subheader("검수 리포트 (Report)")
    
    if input_val:
        josa_corrector = JosaCorrector()
        temp_text, josa_logs = josa_corrector.run(input_val)
        
        spell_corrector = SpellingCorrector()
        final_text, spell_logs = spell_corrector.run(temp_text)
        
        tab1, tab2 = st.tabs(["🔍 수식 조사 검수", "📝 한글/기호 검수"])
        
        with tab1:
            if josa_logs:
                st.error(f"수식 조사 오류: {len(josa_logs)}건")
                df_josa = pd.DataFrame(josa_logs)
                cols = ['문맥', '대상', '원문', '수정', '사유']
                st.dataframe(df_josa[cols], use_container_width=True, hide_index=True)
            else:
                st.success("수식 조사가 완벽합니다.")
                
        with tab2:
            if spell_logs:
                st.warning(f"한글/기호 오류: {len(spell_logs)}건")
                df_spell = pd.DataFrame(spell_logs)
                cols = ['문맥', '대상', '원문', '수정', '사유']
                st.dataframe(df_spell[cols], use_container_width=True, hide_index=True)
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