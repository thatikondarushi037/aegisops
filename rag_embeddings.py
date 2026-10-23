import requests

from rag_loader import load_runbooks, chunk_documents
# load the runbooks and chunk them into smaller pieces for processing and analysis. This will help in managing large documents and improve the efficiency of any subsequent operations, such as searching or analyzing the content.
EMBED_URL = "http://localhost:11434/api/embed"
EMBED_MODEL = "nomic-embed-text"

# function to generate embeddings for a given text using the specified embedding model. This will help in converting the text into a numerical representation that can be used for various machine learning tasks, such as similarity search or clustering.
def embed_text(text):
    response = requests.post(
        EMBED_URL,
        json={
            "model": EMBED_MODEL,
            "input": text,
            "truncate": False
        },
        timeout=30
    )
    response.raise_for_status()  # Check if the request was successful and raise an error if not
    return response.json()["embeddings"]

# main block to load the runbooks, chunk them, and generate embeddings for each chunk. This will help in verifying that the documents are loaded correctly, that the chunking process is working as expected, and that embeddings are generated successfully for each chunk.

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
    print("First embedding vector:", vectors[0][:5])  # Print first 5 elements of the first embedding vector