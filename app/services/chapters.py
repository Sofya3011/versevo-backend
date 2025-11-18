import re
from nltk.tokenize import sent_tokenize
from typing import List, Dict

# Убедись, что скачаны punkt models: nltk.download('punkt') при установки/инициализации

def detect_chapters(text: str) -> List[Dict]:
    """
    Возвращает список {'title': str, 'start': int, 'end': int, 'content': str}
    Попытка найти заголовки Глава N или Chapter N, иначе делим на приблизительно равные блоки по 8000 символов.
    """
    # Найти заголовки "Глава X", "CHAPTER X", "Chapter X"
    pattern = re.compile(r'^\s*(Глава|Глава\s+\d+|CHAPTER|CHAPTER\s+\d+|Chapter\s+\d+|CHAPTER [IVXLC]+)\b.*', re.IGNORECASE | re.MULTILINE)
    matches = list(pattern.finditer(text))
    if matches:
        chapters = []
        for i, m in enumerate(matches):
            start = m.start()
            end = matches[i+1].start() if i+1 < len(matches) else len(text)
            title_line = text[m.start(): text.find("\n", m.start())].strip()
            content = text[start:end].strip()
            chapters.append({"title": title_line, "start": start, "end": end, "content": content})
        return chapters
    # fallback: split by chunks ~ 10k chars but on sentence boundary
    approx = 10000
    chapters = []
    pos = 0
    idx = 1
    while pos < len(text):
        end_pos = min(pos + approx, len(text))
        # try move end_pos forward to next sentence end
        snippet = text[pos:end_pos]
        sents = sent_tokenize(snippet)
        if len(sents) > 1:
            chunk = " ".join(sents)
        else:
            # take raw chunk
            chunk = snippet
        chapters.append({"title": f"Part {idx}", "start": pos, "end": pos + len(chunk), "content": chunk})
        pos += len(chunk)
        idx += 1
    return chapters
