
from pathlib import Path

RUNBOOK_DIR = (
    Path(__file__).resolve().parent
    / "knowledge_base"
    / "runbooks"
)


def load_runbooks():
    documents = []

    for file_path in sorted(RUNBOOK_DIR.glob("*.md")):
        text = file_path.read_text(encoding="utf-8")

        documents.append({
            "source": file_path.name,
            "content": text
        })

    return documents

# Split runbooks into non-overlapping word chunks, preserving source names.
def chunk_documents(documents, chunk_size=300):
    chunks = []
    
    for document in documents:
        words = document["content"].split()
        
        
        
        for start in range(0, len(words), chunk_size):
            passage = " ".join(words[start:start + chunk_size])
            chunks.append({
                "source": document["source"],
                "text": passage
            })
            
    return chunks


# Explicit preview of loaded runbook chunks.

if __name__ == "__main__":
    documents = load_runbooks()
    chunks = chunk_documents(documents)
    
    print("Documents loaded:", len(documents))
    print("Chunks created:", len(chunks))
    
    
    for index, chunk in enumerate(chunks, start=1):
        print(f"\nChunk {index}")
        print("Source:", chunk["source"])
        print("Text:", chunk["text"])
