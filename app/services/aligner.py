from typing import List, Dict

def simple_align_text_audio(text: str, audio_duration_seconds: float) -> List[Dict]:
    """
    Разбивает текст на равные временные фрагменты по словам.
    Возвращает список: [{'start_sec':..,'end_sec':..,'start_offset':..,'end_offset':..}]
    """
    words = text.split()
    total_words = len(words)
    if total_words == 0 or audio_duration_seconds <= 0:
        return []
    sec_per_word = audio_duration_seconds / total_words
    offsets = []
    current_word_index = 0
    char_index = 0
    for i, w in enumerate(words):
        # nothing here, we will later accumulate
        pass
    # Build mapping by iterating words and building offsets by char count approximation
    char_positions = []
    running = 0
    for w in words:
        idx = text.find(w, running)
        if idx == -1:
            idx = running
        char_positions.append(idx)
        running = idx + len(w)
    result = []
    for i, idx in enumerate(char_positions):
        start_sec = i * sec_per_word
        end_sec = (i+1) * sec_per_word
        result.append({
            "start_sec": start_sec,
            "end_sec": end_sec,
            "start_offset": idx,
            "end_offset": idx + len(words[i])
        })
    return result
