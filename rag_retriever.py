import math 

from rag_loader import load_runbooks, chunk_documents
from rag_embeddings import embed_text

# Cosine similarity returns zero for a zero-magnitude vector.

def cosine_similarity(vector_a, vector_b):
    if len(vector_a) != len(vector_b):
        raise ValueError("Vector dimensions do not match") 
    
    
    dot_product = sum(a * b for a, b in zip(vector_a, vector_b))
    
    magnitude_a = math.sqrt(sum(a * a for a in vector_a))
    magnitude_b = math.sqrt(sum(b * b for b in vector_b))
    
    
    if magnitude_a == 0 or magnitude_b == 0:
        return 0.0

    return dot_product / (magnitude_a * magnitude_b)

# Rank local runbook passages by cosine similarity to the query.

def retrieve_runbooks(query, top_k=3, *, deadline=None, max_chunks=None):
    documents = load_runbooks()
    chunks = chunk_documents(documents)
    if max_chunks is not None:
        chunks = chunks[:max_chunks]

    if not chunks:
        return []

    options = {"deadline": deadline} if deadline is not None else {}
    chunk_vectors = embed_text([chunk["text"] for chunk in chunks], **options)

    query_vector = embed_text([query], **options)[0]

    results = []

    for chunk, vector in zip(chunks, chunk_vectors):
        score = cosine_similarity(query_vector, vector)

        results.append({
            "source": chunk["source"],
            "text": chunk["text"],
            "score": score
        })

    results.sort(
        key=lambda result: result["score"],
        reverse=True
    )

    return results[:top_k]

# Explicit retrieval smoke test with synthetic queries.

if __name__ == "__main__":
    queries = [
        "Payment transactions are failing",
        "Users cannot log in because token validation fails",
        "Inventory stock updates are delayed by an event queue"
    ]

    for query in queries:
        print("\nQUERY:", query)

        matches = retrieve_runbooks(query, top_k=3)

        for match in matches:
            print(
                match["source"],
                "Similarity:",
                round(match["score"], 4)
            )
