import requests
from settings import OLLAMA_BASE_URL, OLLAMA_EMBED_MODEL, OLLAMA_EMBED_TIMEOUT

from rag_loader import load_runbooks, chunk_documents
# Ollama embedding endpoint and configured model.
EMBED_URL = f"{OLLAMA_BASE_URL}/api/embed"
EMBED_MODEL = OLLAMA_EMBED_MODEL

# Respect the caller deadline as well as the configured request timeout.
def embed_text(text, *, deadline=None):
    import time
    remaining = deadline - time.monotonic() if deadline is not None else OLLAMA_EMBED_TIMEOUT
    if remaining <= 0:
        raise requests.Timeout("Embedding budget exhausted")
    response = requests.post(
        EMBED_URL,
        json={
            "model": EMBED_MODEL,
            "input": text,
            "truncate": False
        },
        timeout=(min(5, remaining), min(OLLAMA_EMBED_TIMEOUT, remaining))
    )
    response.raise_for_status()
    return response.json()["embeddings"]

# Explicit embedding smoke test for the local runbooks.

if __name__ == "__main__":
    documents = load_runbooks()
    chunks = chunk_documents(documents)

    if not chunks:
        raise RuntimeError("No chunks found")
    
    
    texts = [chunk["text"] for chunk in chunks]
    vectors = embed_text(texts)
    
    
    print("chunks:", len(chunks))
    print("Embeddings:", len(vectors))
    print("Embedding dimension:", len(vectors[0]))
    print("First embedding vector:", vectors[0][:5])
