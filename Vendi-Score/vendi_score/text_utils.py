import itertools

import datasets
from nltk.tokenize import word_tokenize
from nltk.translate import bleu_score
import numpy as np
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.preprocessing import normalize
import torch
from transformers import AutoModel, AutoTokenizer

from vendi_score import data_utils, vendi
from vendi_score.data_utils import Example, Group

import numpy as np
import tiktoken

def get_tokenizer(model="roberta-base"):
    tokenizer = AutoTokenizer.from_pretrained("roberta-base", use_fast=True)

    def tokenize(s):
        return tokenizer.convert_ids_to_tokens(tokenizer(s).input_ids)

    return tokenize


def sklearn_tokenizer():
    return CountVectorizer().build_tokenizer()


def get_mnli():
    data = itertools.chain(
        datasets.load_dataset("multi_nli", split="validation_matched"),
        datasets.load_dataset("multi_nli", split="validation_mismatched"),
    )
    seen = set()
    examples = []
    for d in data:
        s = d["premise"]
        if s in seen:
            continue
        seen.add(s)
        examples.append(Example(x=s, labels={"y": d["genre"]}))
    return examples


def get_ngrams(
    sents,
    n=1,
    tokenizer=None,
    return_vectorizer=False,
    lowercase=False,
    **kwargs,
):
    if tokenizer is None:
        tokenizer = word_tokenize
    ngram_range = n if type(n) == tuple else (n, n)
    vectorizer = CountVectorizer(
        tokenizer=tokenizer,
        ngram_range=ngram_range,
        lowercase=lowercase,
        **kwargs,
    )
    X = vectorizer.fit_transform(sents)
    if return_vectorizer:
        return X, vectorizer
    return X


def add_ngrams_to_examples(
    examples, n=1, tokenizer=None, return_vectorizer=False, **kwargs
):
    X = get_ngrams([e.x for e in examples], n=n, tokenizer=tokenizer, **kwargs)
    for e, x in zip(examples, X):
        e.features[f"{n}-grams"] = x
    return examples


def get_embeddings(
    sents,
    model=None,
    tokenizer=None,
    batch_size=16,
    device="cpu",
    model_path="princeton-nlp/unsup-simcse-roberta-base",
):
    if device is None:
        device = (
            torch.device("cuda")
            if torch.cuda.is_available()
            else torch.device("cpu")
        )
    if type(device) == str:
        device = torch.device(device)
    if model is None:
        model = AutoModel.from_pretrained(model_path).eval().to(device)
        tokenizer = AutoTokenizer.from_pretrained(model_path, use_fast=True)
    embeddings = []
    for batch in data_utils.to_batches(sents, batch_size):
        inputs = tokenizer(
            batch,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=512,
        )
        inputs = {k: v.to(device) for k, v in inputs.items()}
        with torch.no_grad():
            output = model(**inputs)
            if hasattr(output, "pooler_output"):
                output = output.pooler_output
            else:
                output = output.last_hidden_state[:, 0]
        if type(output) == list:
            output = output[0]
        embeddings.append(output.squeeze().cpu().numpy())
    return np.concatenate(embeddings, 0)


def get_tiktoken_embeddings(
    sents,
    model_name="gpt-4o",
    pad_token_id=0
):
    # Initialize the tiktoken encoder
    encoder = tiktoken.encoding_for_model(model_name)
    
    # Encode all sentences
    encoded_sents = [encoder.encode(sent) for sent in sents]
    
    # Find the length of the longest sentence
    max_length = max(len(tokens) for tokens in encoded_sents)
    
    # Pad all sentences to the max length
    padded_sents = [
        tokens + [pad_token_id] * (max_length - len(tokens))
        for tokens in encoded_sents
    ]
    
    # Convert to numpy array
    embeddings = np.array(padded_sents)
    
    # Create a mask array
    mask = np.array([
        [1] * len(tokens) + [0] * (max_length - len(tokens))
        for tokens in encoded_sents
    ])
    
    return embeddings, mask



def add_embeddings_to_examples(
    examples,
    model=None,
    tokenizer=None,
    batch_size=16,
    device="cpu",
    model_name="princeton-nlp/unsup-simcse-roberta-base",
    feature_name="unsup_simcse",
):
    X = get_embeddings(
        [e.x for e in examples],
        model=model,
        tokenizer=tokenizer,
        batch_size=batch_size,
        device=device,
        model_name=model_name,
    )
    for e, x in zip(examples, X):
        e.features[feature_name] = x
    return examples


def single_ngram_diversity(sents, n, tokenizer=None, **kwargs):
    X = get_ngrams(sents, n=n, tokenizer=tokenizer, **kwargs)
    distinct = X.shape[-1]
    total = X.sum()
    # unique = (counts == 1).sum()
    # total = counts.shape[-1]
    return distinct / total


def ngram_diversity(sents, ns=[1, 2, 3, 4], tokenizer=None, **kwargs):
    return np.mean(
        [
            single_ngram_diversity(sents, n, tokenizer=tokenizer, **kwargs)
            for n in ns
        ]
    )


def bleu(hyps, refs, tokenizer=None):
    if type(hyps[0]) == str:
        if tokenizer is None:
            tokenizer = word_tokenize
        hyp_tokens = [tokenizer(s) for s in hyps]
        ref_tokens = [tokenizer(s) for s in refs]
    else:
        hyp_tokens = hyps
        ref_tokens = refs
    smoothing = bleu_score.SmoothingFunction().method1
    return np.mean(
        [
            bleu_score.sentence_bleu(refs, hyp, smoothing_function=smoothing)
            for hyp in hyps
        ]
    )


def self_bleu(sents, tokenizer):
    examples = [tokenizer(s) for s in sents]
    smoothing = bleu_score.SmoothingFunction().method1
    scores = []
    for i in range(len(examples)):
        hyp = examples[i]
        ref = examples[:i] + examples[i + 1 :]
        scores.append(
            bleu_score.sentence_bleu(ref, hyp, smoothing_function=smoothing)
        )
    return np.mean(scores)


def pairwise_bleu(sents, tokenizer):
    examples = [tokenizer(s) for s in sents]
    smoothing = bleu_score.SmoothingFunction().method1
    scores = []
    for i in range(len(examples)):
        lst = []
        for j in range(len(examples)):
            if j == i:
                continue
            hyp = examples[i]
            ref = [examples[j]]
            lst.append(
                bleu_score.sentence_bleu(ref, hyp, smoothing_function=smoothing)
            )
        scores.append(np.mean(lst))
    return np.mean(scores)


def ngram_vendi_score(sents, ns=[1, 2, 3, 4], tokenizer=None, **kwargs):
    Ks = []
    for n in ns:
        X = normalize(get_ngrams(sents, n=n, tokenizer=tokenizer))
        Ks.append((X @ X.T).A)
    K = np.stack(Ks, axis=0).mean(axis=0)
    return vendi.score_K(K)


def embedding_vendi_score(
    sents,
    model=None,
    tokenizer=None,
    batch_size=16,
    device="cpu",
    model_path="princeton-nlp/unsup-simcse-roberta-base",
):
    X = get_embeddings(
        sents,
        model=model,
        tokenizer=tokenizer,
        batch_size=batch_size,
        device=device,
        model_path=model_path,
    )
    n, d = X.shape
    if n < d:
        return vendi.score_X(X)
    return vendi.score_dual(X)


def calculate_nonzero_stats(X):
    """
    Calculate the average number of non-zero elements per row and its standard deviation.

    Parameters:
    X (np.array): A 2D numpy array with zero-padding applied.

    Returns:
    tuple: (average_non_zero, std_dev_non_zero)
    """
    # 計算每一筆數據的非零元素數量
    non_zero_counts = np.count_nonzero(X, axis=1)
    
    # 計算非零元素的平均值與標準差
    average_non_zero = np.mean(non_zero_counts)
    std_dev_non_zero = np.std(non_zero_counts)

    return average_non_zero, std_dev_non_zero

def tiktoken_vendi_score(sents, DatasetName):
    X, mask = get_tiktoken_embeddings(sents)

    n, d = X.shape

    average_non_zero, std_dev_non_zero = calculate_nonzero_stats(X)

    print(f"DatasetName: {DatasetName}. Average Non-Zero length: {average_non_zero:.02f}, STD: {std_dev_non_zero:.02f}")

    if n < d:
        return vendi.score_X(X)

    return vendi.score_dual_sparse(X)

