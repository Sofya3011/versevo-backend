import os
import re
import math
import json
from collections import Counter, defaultdict
from typing import List, Dict, Tuple
from pathlib import Path

import nltk
nltk.download('punkt', quiet=True)
nltk.download('stopwords', quiet=True)
from nltk.tokenize import sent_tokenize, word_tokenize
from nltk.corpus import stopwords

import spacy
# multilingual NER
try:
    nlp = spacy.load("xx_ent_wiki_sm")
except Exception:
    # fallback to small blank model (less accurate)
    nlp = spacy.blank("xx")

from sklearn.feature_extraction.text import TfidfVectorizer, CountVectorizer
from sklearn.decomposition import LatentDirichletAllocation

import networkx as nx
import matplotlib.pyplot as plt
from wordcloud import WordCloud

from ..config import settings

# Optional: HF sentiment/summarization via inference API
import requests

HF_API = settings.HF_API_KEY

STOPWORDS_EN = set(stopwords.words('english'))
STOPWORDS_RU = set(stopwords.words('russian')) if 'russian' in stopwords.fileids() else set()

def _clean_text(text: str) -> str:
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def tokenize_sentences(text: str) -> List[str]:
    return sent_tokenize(text)

def tokenize_words(text: str, lang: str = 'en') -> List[str]:
    tokens = word_tokenize(text)
    # filter punctuation
    tokens = [t.lower() for t in tokens if re.search(r'\w', t)]
    if lang.startswith('ru'):
        return [t for t in tokens if t not in STOPWORDS_RU]
    return [t for t in tokens if t not in STOPWORDS_EN]

def extract_entities(text: str) -> List[Tuple[str, str]]:
    """
    Returns list of (entity_text, label) from spaCy NER
    """
    doc = nlp(text)
    ents = [(ent.text.strip(), ent.label_) for ent in doc.ents if ent.label_ in ("PER", "PERSON", "ORG", "LOC", "GPE")]
    return ents

def aggregate_persons(entities: List[Tuple[str,str]]) -> Dict[str,int]:
    # aggregate by normalized form (strip titles, initials)
    counter = Counter()
    for name, label in entities:
        if label in ("PER","PERSON"):
            nm = re.sub(r'[^A-Za-zА-Яа-яЁё\s\-]', '', name).strip()
            nm = ' '.join([p.capitalize() for p in nm.split()][:3])
            if nm:
                counter[nm] += 1
    return dict(counter.most_common())

def build_cooccurrence_graph(text: str, top_persons: List[str], window_sentences: int = 1) -> Tuple[Dict, List]:
    """
    Build a simple undirected co-occurrence graph.
    top_persons: list of person names (strings) to consider nodes.
    Returns nodes list and edges list (for JSON serialization).
    """
    sents = tokenize_sentences(text)
    # map sentence index to set of persons mentioned
    sent_persons = []
    for s in sents:
        found = set()
        for p in top_persons:
            # naive check
            if re.search(r'\b' + re.escape(p.split()[0]) + r'\b', s, flags=re.IGNORECASE):
                found.add(p)
        sent_persons.append(found)

    G = nx.Graph()
    for p in top_persons:
        G.add_node(p, size=1)

    for i, persons in enumerate(sent_persons):
        persons = list(persons)
        for a in range(len(persons)):
            for b in range(a+1, len(persons)):
                u, v = persons[a], persons[b]
                if G.has_edge(u,v):
                    G[u][v]['weight'] += 1
                else:
                    G.add_edge(u,v, weight=1)

    # normalize sizes by degree
    nodes = []
    for n, d in G.degree():
        nodes.append({"id": n, "label": n, "degree": d, "size": G.degree(n)})

    edges = []
    for u,v,data in G.edges(data=True):
        edges.append({"source": u, "target": v, "weight": int(data.get('weight',1))})

    return nodes, edges

def top_keywords_tfidf(text: str, n: int = 20, lang: str = 'en') -> List[Tuple[str,float]]:
    vec = TfidfVectorizer(ngram_range=(1,2), max_df=0.85, min_df=1, stop_words='english' if not lang.startswith('ru') else None)
    X = vec.fit_transform([text])
    features = vec.get_feature_names_out()
    scores = X.toarray().sum(axis=0)
    idx = scores.argsort()[::-1][:n]
    return [(features[i], float(scores[i])) for i in idx]

def topical_lda(text: str, n_topics: int = 4, n_top_words: int = 8, lang: str = 'en') -> List[Dict]:
    # Preprocess
    vectorizer = CountVectorizer(max_df=0.95, min_df=2, stop_words='english' if not lang.startswith('ru') else None)
    dtm = vectorizer.fit_transform([text])
    if dtm.shape[1] < n_topics:
        n_topics = max(1, dtm.shape[1]//2)
    lda = LatentDirichletAllocation(n_components=n_topics, random_state=42)
    lda.fit(dtm)
    words = vectorizer.get_feature_names_out()
    topics = []
    for i, comp in enumerate(lda.components_):
        indices = comp.argsort()[::-1][:n_top_words]
        topic_words = [words[idx] for idx in indices]
        topics.append({"topic_id": i, "words": topic_words})
    return topics

def extract_summary(text: str, n_sentences: int = 5, lang: str = 'en') -> str:
    sents = tokenize_sentences(text)
    if len(sents) <= n_sentences:
        return text
    # score sentences by TF-IDF of words present
    vectorizer = TfidfVectorizer(stop_words='english' if not lang.startswith('ru') else None)
    X = vectorizer.fit_transform(sents)
    scores = X.sum(axis=1).A1
    ranked_idx = scores.argsort()[::-1][:n_sentences]
    ranked_idx_sorted = sorted(ranked_idx)
    summary = " ".join([sents[i] for i in ranked_idx_sorted])
    return summary

def sentiment_via_hf(text: str) -> Dict:
    """
    Call HF Inference sentiment model. Returns label + score.
    """
    if not HF_API:
        return {"label": "unknown", "score": 0.0}
    url = "https://api-inference.huggingface.co/models/siebert/sentiment-roberta-large-english"
    headers = {"Authorization": f"Bearer {HF_API}"}
    payload = {"inputs": text[:1000]}
    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    data = resp.json()
    # data might be list of dicts
    if isinstance(data, list) and data:
        return data[0]
    if isinstance(data, dict) and "label" in data:
        return data
    return {"label": "unknown", "score": 0.0}

def simple_sentiment_heuristic(text: str, lang: str='en') -> Dict:
    # very simple: count positive/negative words (small lexicon)
    positive = set(["good","great","happy","love","excellent","positive","wonderful","best","amazing"])
    negative = set(["bad","sad","hate","poor","terrible","awful","worse","worst","negative"])
    tokens = [t.lower() for t in re.findall(r"\w+", text)]
    pos = sum(1 for t in tokens if t in positive)
    neg = sum(1 for t in tokens if t in negative)
    score = (pos - neg) / max(1, (pos + neg))
    label = "neutral"
    if score > 0.1:
        label = "positive"
    elif score < -0.1:
        label = "negative"
    return {"label": label, "score": float(score)}

def generate_wordcloud(text: str, out_path: str, lang: str='en'):
    wc = WordCloud(width=800, height=400, background_color='white', collocations=False)
    wc.generate(text)
    wc.to_file(out_path)
    return out_path

def plot_top_words(freq_pairs: List[Tuple[str,int]], out_path: str):
    words = [w for w,_ in freq_pairs][:20]
    counts = [int(c) for _,c in freq_pairs][:20]
    plt.figure(figsize=(10,6))
    plt.barh(list(reversed(words)), list(reversed(counts)))
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()
    return out_path

def analyze_text(text: str, document_id: int = None, lang_hint: str = None) -> Dict:
    text = _clean_text(text)
    # language detection could be added
    lang = 'ru' if (lang_hint and lang_hint.startswith('ru')) else 'en'
    sentences = tokenize_sentences(text)
    words = tokenize_words(text, lang=lang)
    total_words = len(words)
    unique_words = len(set(words))
    total_sentences = len(sentences)
    reading_time_min = math.ceil(total_words / 180)  # 180 wpm

    # entities & persons
    ents = extract_entities(text)
    persons = aggregate_persons([e for e in ents if e[1] in ("PER","PERSON")])
    # persons sorted
    persons_sorted = sorted(persons.items(), key=lambda x: x[1], reverse=True)

    # keywords
    try:
        keywords = top_keywords_tfidf(text, n=30, lang=lang)
    except Exception:
        keywords = []

    # topics
    try:
        topics = topical_lda(text, n_topics=4, n_top_words=6, lang=lang)
    except Exception:
        topics = []

    # summary
    summary = extract_summary(text, n_sentences=5, lang=lang)

    # sentiment
    if HF_API:
        sentiment = sentiment_via_hf(text)
    else:
        sentiment = simple_sentiment_heuristic(text, lang=lang)

    # build co-occurrence graph for top persons
    top_persons = [p for p,_ in persons_sorted[:12]]
    graph_nodes, graph_edges = build_cooccurrence_graph(text, top_persons)

    # frequency pairs
    freq = Counter(words)
    top_freq = freq.most_common(30)

    # generate visualizations
    out_files = {}
    book_folder = Path(settings.BOOKS_FOLDER)
    book_folder.mkdir(parents=True, exist_ok=True)
    if document_id:
        prefix = f"analysis_{document_id}_"
    else:
        prefix = f"analysis_tmp_"
    try:
        wc_path = str(book_folder / (prefix + "wordcloud.png"))
        generate_wordcloud(" ".join(words), wc_path, lang=lang)
        out_files["wordcloud"] = f"/books/{Path(wc_path).name}"
    except Exception as e:
        out_files["wordcloud_error"] = str(e)

    try:
        bar_path = str(book_folder / (prefix + "topwords.png"))
        plot_top_words(top_freq, bar_path)
        out_files["topwords"] = f"/books/{Path(bar_path).name}"
    except Exception as e:
        out_files["topwords_error"] = str(e)

    # graph image
    try:
        graph_path = str(book_folder / (prefix + "graph.png"))
        # draw graph using networkx
        G = nx.Graph()
        for n in graph_nodes:
            G.add_node(n["id"], size=n.get("size",1))
        for e in graph_edges:
            G.add_edge(e["source"], e["target"], weight=e.get("weight",1))
        plt.figure(figsize=(10,10))
        pos = nx.spring_layout(G, seed=42)
        sizes = [300 + 100*G.degree(n) for n in G.nodes()]
        nx.draw_networkx_nodes(G, pos, node_size=sizes)
        nx.draw_networkx_labels(G, pos, font_size=10)
        edges = G.edges()
        weights = [G[u][v]['weight'] for u,v in edges]
        nx.draw_networkx_edges(G, pos, width=[max(0.5, w*0.5) for w in weights])
        plt.axis('off')
        plt.savefig(graph_path, dpi=150, bbox_inches='tight')
        plt.close()
        out_files["graph"] = f"/books/{Path(graph_path).name}"
    except Exception as e:
        out_files["graph_error"] = str(e)

    result = {
        "stats": {
            "words": total_words,
            "unique_words": unique_words,
            "sentences": total_sentences,
            "reading_time_min": reading_time_min
        },
        "persons": [{"name": n, "count": c} for n,c in persons_sorted],
        "top_keywords": [{"kw": k, "score": float(s)} for k,s in keywords],
        "topics": topics,
        "summary": summary,
        "sentiment": sentiment,
        "graph": {"nodes": graph_nodes, "edges": graph_edges},
        "top_frequency": [{"word": w, "count": int(c)} for w,c in top_freq],
        "visuals": out_files
    }
    return result