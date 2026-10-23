import math 

from rag_loader import load_runbooks, chunk_documents
from rag_embeddings import embed_text

# function to compute the cosine similarity between two vectors. This will help in measuring the similarity between two pieces of text based on their embeddings, which can be useful for tasks such as information retrieval or clustering.

def cosine_similarity(vector_a, vector_b):
    if len(vector_a) != len(vector_b):
        raise ValueError("Vector dimensions do not match") 
    
    
    dot_product = sum(a * b for a, b in zip(vector_a, vector_b))  # Calculate the dot product of the two vectors
    
    magnitude_a = math.sqrt(sum(a * a for a in vector_a))
    magnitude_b = math.sqrt(sum(b * b for b in vector_b)) # Calculate the magnitudes of the two vectors
    
    
    if magnitude_a == 0 or magnitude_b == 0: # Handle the case where one or both vectors have zero magnitude to avoid division by zero
        return 0.0

    return dot_product / (magnitude_a * magnitude_b)

# function to retrieve the most relevant runbooks based on a given query. This will help in finding the most relevant information from the runbooks for a specific query, which can be useful for tasks such as troubleshooting or incident investigation.

def retrieve_runbooks(query, top_k=3):
    documents = load_runbooks()
    chunks = chunk_documents(documents)

    if not chunks:
        return []

    chunk_vectors = embed_text(
        [chunk["text"] for chunk in chunks]
    )

    query_vector = embed_text([query])[0] # Generate the embedding for the query to compare it with the embeddings of the runbook chunks

    results = []

    for chunk, vector in zip(chunks, chunk_vectors): # Calculate the cosine similarity between the query vector and each chunk vector to determine how relevant each chunk is to the query
        score = cosine_similarity(query_vector, vector)

        results.append({
            "source": chunk["source"],
            "text": chunk["text"],
            "score": score
        })

    results.sort( # Sort the results based on the similarity score in descending order to get the most relevant runbooks at the top
        key=lambda result: result["score"],
        reverse=True
    )

    return results[:top_k]

# main block to test the retrieval of runbooks based on a set of queries. This will help in verifying that the retrieval process is working correctly and that the most relevant runbooks are being returned for each query.

if __name__ == "__main__":
    queries = [   # List of sample queries to test the retrieval of runbooks based on different scenarios. Each query represents a potential issue that might be encountered in a production environment, and the retrieval function will attempt to find the most relevant runbooks for each query.
        "Payment transactions are failing",
        "Users cannot log in because token validation fails",
        "Inventory stock updates are delayed by an event queue"
    ]

    for query in queries: # Iterate through each query, retrieve the most relevant runbooks, and print the results to verify that the retrieval process is working correctly and that the most relevant runbooks are being returned for each query.
        print("\nQUERY:", query)

        matches = retrieve_runbooks(query, top_k=3) # Retrieve the top 3 most relevant runbooks for the current query based on cosine similarity between the query embedding and the embeddings of the runbook chunks

        for match in matches: # Print the source of the runbook and the similarity score for each of the top matches to provide insight into which runbooks are most relevant to the query and how closely they match based on their embeddings.
            print(
                match["source"],
                "Similarity:",
                round(match["score"], 4)
            )



"""How it works
1. Load all runbooks and divide them into chunks.
2. Convert the chunks into embeddings.
3. Convert the user's query into an embedding using the same model.
4. Calculate cosine similarity for each passage.
5. Return the highest-scoring passages."""